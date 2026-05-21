# -*- coding: utf-8 -*-
"""FastAPI 后端：把 tiled_tools 暴露成 HTTP 服务给前端用。

启动：
    python -m tiled_tools serve --port 8765
浏览器打开：
    http://localhost:8765/

路由：
    GET  /api/actions              列出所有 action 及其参数 schema
    POST /api/upload               上传图片，返回 {file_id, filename, url}
    POST /api/upload-batch         批量上传图片到一个运行期目录，返回 {dir_id, files}
    POST /api/run                  body: {pipeline: [...], variables: {...}}

                                   执行 pipeline，返回 {ok, log, outputs}
    GET  /api/file/{file_id}       下载/预览（uploads 与 outputs 都走这里）
    GET  /                         前端 SPA
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import traceback
import uuid
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .core.action import Context
from .core.pipeline import (
    Pipeline,
    _substitute as _pipeline_substitute,
    _coerce_default as _coerce_str,
)
from .core.registry import available_actions, get_action

# 注册表里的 Action 类
from .core.registry import _REGISTRY  # type: ignore[attr-defined]


# ---------- 路径约定 ----------
# 包内只放可分发的只读资源；用户数据和运行期产物写到当前工作目录。
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_DIR = Path.cwd().resolve()
WEB_DIR = PACKAGE_ROOT / "web"
RUNTIME_DIR = PROJECT_DIR / ".tiled_tools_runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
OUTPUT_DIR = RUNTIME_DIR / "outputs"
# 用户编辑/保存的 workflow（前端写）
WORKFLOWS_DIR = PROJECT_DIR / "workflows"
# 包内自带的 YAML pipeline（手写、只读）
PIPELINES_DIR = PACKAGE_ROOT / "pipelines"
# 教程 markdown，前端「📖 帮助」按钮渲染
DOCS_DIR = PACKAGE_ROOT / "docs"


def _ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)


# ---------- workflow id 校验 ----------
# id 用于落盘文件名，只允许 [a-z0-9_-]，前端可填中文 name 但 id 单独给。
import re as _re

_VALID_ID = _re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _check_workflow_id(wid: str) -> None:
    if not _VALID_ID.match(wid):
        raise HTTPException(400, f"非法 workflow id: {wid!r}（只允许字母数字/_/-）")


# ---------- 文件 id 与路径互转 ----------
# file_id 形如 "up_<uuid>.png" 或 "out_<uuid>.png"，扁平好管理。

def _new_id(prefix: str, suffix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}{suffix}"


def _resolve_file_id(file_id: str) -> Path:
    """根据 file_id 找到磁盘路径。

    支持两种形式：
      "up_xxx.png"                  -> uploads 下
      "out_xxx.png"                 -> outputs 下
      "set_xxxx/grass_NW.png"       -> outputs 下的子目录（save_all 产物）
      "batch_xxxx/001_tile.png"     -> uploads 下的批量上传子目录


    防穿越：必须落在 RUNTIME_DIR 下，且不允许 ".." 段。
    """
    if "\\" in file_id or ".." in file_id.split("/"):
        raise HTTPException(400, "非法 file_id")
    # 直接拼到 outputs / uploads 下试探
    candidates = [OUTPUT_DIR / file_id, UPLOAD_DIR / file_id]
    for cand in candidates:
        try:
            real = cand.resolve()
        except Exception:
            continue
        # 必须落在 RUNTIME_DIR 内
        try:
            real.relative_to(RUNTIME_DIR.resolve())
        except ValueError:
            continue
        if real.is_file():
            return real
    raise HTTPException(404, f"找不到文件: {file_id}")


def _unique_zip_name(name: str, used: set[str]) -> str:
    base = Path(name).name or "file"
    if base not in used:
        used.add(base)
        return base
    stem = Path(base).stem or "file"
    suffix = Path(base).suffix
    i = 2
    while True:
        candidate = f"{stem}_{i}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        i += 1


def _create_outputs_zip(outputs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """把本次运行产生的可解析 file_id 打包成 zip，并返回下载元数据。"""
    files: List[tuple[Path, str]] = []
    used_names: set[str] = set()
    for item in outputs:
        fid = item.get("file_id")
        if not fid:
            continue
        try:
            p = _resolve_file_id(str(fid))
        except HTTPException:
            continue
        arcname = _unique_zip_name(p.name, used_names)
        files.append((p, arcname))

    if len(files) <= 1:
        return None

    zip_id = _new_id("out", ".zip")
    zip_path = OUTPUT_DIR / zip_id
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p, arcname in files:
            zf.write(p, arcname=arcname)

    return {
        "file_id": zip_id,
        "url": f"/api/file/{zip_id}",
        "label": "download_all",
        "name": "全部产物.zip",
        "count": len(files),
        "size_bytes": zip_path.stat().st_size,
    }


# ---------- API models ----------

class StepModel(BaseModel):
    action: str
    params: Dict[str, Any] = {}


class RunRequest(BaseModel):
    pipeline: List[StepModel]
    variables: Dict[str, Any] = {}


# ---------- 应用 ----------

def create_app() -> FastAPI:
    _ensure_dirs()
    app = FastAPI(title="tiled_tools web", version="0.1")

    # 启动日志：让人一眼看到当前进程加载的是哪份代码、哪些 action。
    # 改完代码不重启 uvicorn 是最常见的"修了 bug 还在报错"陷阱。
    print(f"[server] tiled_tools package: {PACKAGE_ROOT}")
    print(f"[server] project dir: {PROJECT_DIR}")
    print(f"[server] runtime dir: {RUNTIME_DIR}")
    print(f"[server] registered actions: {available_actions()}")

    # 本地工具，开 CORS 方便前端单独起 dev 服务时也能调
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- 业务路由 ----

    @app.get("/api/actions")
    def list_actions():
        items = []
        for name in available_actions():
            cls = _REGISTRY[name]
            items.append(cls.describe())
        return {"actions": items}

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)):
        # 推断后缀，默认 .png
        suffix = _check_image_suffix(file.filename)
        file_id = _new_id("up", suffix)
        dest = UPLOAD_DIR / file_id
        # 防御：进程跑着时如果有人删了运行时目录，下次上传会 FileNotFoundError。
        # 这里再保险一次，开销可忽略。
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = await file.read()
        dest.write_bytes(data)
        return {
            "file_id": file_id,
            "filename": file.filename,
            "url": f"/api/file/{file_id}",
            "size_bytes": len(data),
        }

    @app.post("/api/upload-batch")
    async def upload_batch(files: List[UploadFile] = File(...)):
        """批量上传图片到 uploads/batch_xxxx/，供 load_dir + pack_sheet 使用。"""
        if not files:
            raise HTTPException(400, "没有上传文件")
        dir_id = f"batch_{uuid.uuid4().hex[:8]}"
        dest_dir = UPLOAD_DIR / dir_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        items = []
        for i, file in enumerate(files, start=1):
            suffix = _check_image_suffix(file.filename)
            original = Path(file.filename or f"image_{i:03d}{suffix}").name
            stem = _safe_upload_stem(Path(original).stem, fallback=f"image_{i:03d}")
            fname = f"{i:03d}_{stem}{suffix}"
            dest = dest_dir / fname
            data = await file.read()
            dest.write_bytes(data)
            fid = f"{dir_id}/{fname}"
            items.append({
                "file_id": fid,
                "filename": original,
                "url": f"/api/file/{fid}",
                "size_bytes": len(data),
            })

        return {
            "dir_id": dir_id,
            "count": len(items),
            "files": items,
        }

    @app.get("/api/file/{file_id:path}")

    def get_file(file_id: str):
        p = _resolve_file_id(file_id)
        return FileResponse(p)

    @app.post("/api/run")
    def run_pipeline(req: RunRequest):
        """执行 pipeline。

        约定：
        - load.path 既支持 file_id 也支持磁盘绝对路径。
        - save.path = "auto" / 缺省：自动分配 out_<uuid>.png。
        - save_all.dir = "auto" / 缺省：在 OUTPUT_DIR 下分配独立子目录，
          每张产物再映射成 file_id 列在 outputs 里。
        - 字符串里的 ${var:default} 占位符在预处理前先解析一遍，让上面这些
          "auto / 文件路径" 的判断能稳定工作。
        """
        # 进程运行期间用户可能手动删了运行时目录，每次跑都重新确保目录在
        _ensure_dirs()

        # 0) 先做一遍变量替换：把 ${output:auto} 这类提前展开成 "auto"，
        #    否则下面 raw == "auto" 判断不到。
        try:
            steps_substituted = [
                {
                    "action": s.action,
                    "params": _coerce_params(
                        _pipeline_substitute(dict(s.params), req.variables or {})
                    ),
                }
                for s in req.pipeline
            ]
        except KeyError as e:
            return JSONResponse({
                "ok": False,
                "elapsed_ms": 0,
                "log": "",
                "error": f"{type(e).__name__}: {e}",
                "outputs": [],
            })

        # 1) 把 pipeline 里的 path/dir 做一遍 file_id → 实际路径的解析
        steps_dict: List[Dict[str, Any]] = []
        produced_outputs: List[Dict[str, Any]] = []
        save_all_dirs: List[Path] = []          # 待执行后扫描的 save_all 目录
        sheet_dir: Optional[Path] = None        # pack_sheet 这次用的目录
        sheet_png_path: Optional[Path] = None   # pack_sheet 产物路径
        tsx_path: Optional[Path] = None         # build_tsx_sheet 产物路径

        for step in steps_substituted:
            action_name = step["action"]
            params = dict(step["params"])

            if action_name == "load":
                params["path"] = _materialize_input_path(params.get("path"))

            elif action_name == "load_dir":
                # path 参数允许指向 uploads / outputs 下的运行期子目录（如 batch_xxxx / set_xxxx），
                # 也允许绝对路径直接放行。
                params["path"] = _materialize_dir_path(params.get("path"))

            elif action_name == "mask_blend_set":

                # foreground / background 也是输入路径，做 file_id 解析。
                for k in ("foreground", "background"):
                    if k in params and params[k]:
                        params[k] = _materialize_input_path(params[k])

            elif action_name == "save":
                raw = params.get("path")
                if not raw or raw == "auto":
                    out_id = _new_id("out", ".png")
                    out_path = OUTPUT_DIR / out_id
                    params["path"] = str(out_path)
                    produced_outputs.append({"file_id": out_id, "label": "save"})
                else:
                    out_path = _materialize_output_path(raw)
                    params["path"] = str(out_path)
                    produced_outputs.append({
                        "file_id": out_path.name if out_path.parent == OUTPUT_DIR else "",
                        "label": "save",
                        "path": str(out_path),
                    })

            elif action_name == "save_all":
                raw = params.get("dir")
                if not raw or raw == "auto":
                    # 用 uuid 子目录，让多次 save_all 不互相覆盖
                    sub = OUTPUT_DIR / f"set_{uuid.uuid4().hex[:8]}"
                    sub.mkdir(parents=True, exist_ok=True)
                    params["dir"] = str(sub)
                    save_all_dirs.append(sub)
                else:
                    p = Path(raw).expanduser()
                    if not p.is_absolute():
                        p = (OUTPUT_DIR / p.name).resolve()
                    p.mkdir(parents=True, exist_ok=True)
                    params["dir"] = str(p)
                    save_all_dirs.append(p)

            elif action_name == "pack_sheet":
                # sheet 和后续 tsx 必须同目录，这样 tsx 里的 <image source>
                # 就是纯文件名。为本次 /api/run 分配一个子目录。
                raw = params.get("path")
                if sheet_dir is None:
                    sheet_dir = OUTPUT_DIR / f"sheet_{uuid.uuid4().hex[:8]}"
                    sheet_dir.mkdir(parents=True, exist_ok=True)
                if not raw or raw == "auto":
                    fname = "sheet.png"
                else:
                    fname = Path(raw).name or "sheet.png"
                    if not fname.lower().endswith((".png", ".webp")):
                        fname += ".png"
                sheet_png_path = sheet_dir / fname
                params["path"] = str(sheet_png_path)
                produced_outputs.append({
                    "file_id": f"{sheet_dir.name}/{fname}",
                    "label": "pack_sheet",
                    "name": "sheet",
                })

            elif action_name == "build_tsx_sheet":
                # tsx 默认与 sheet 同名同目录。sheet_dir 必须已经由 pack_sheet 设好。
                raw = params.get("path")
                if sheet_dir is None:
                    # 用户手搓的 pipeline 可能直接来 build_tsx_sheet（不合法，交给 action 自身报错）
                    pass
                else:
                    if not raw or raw == "auto":
                        base = (sheet_png_path.stem if sheet_png_path else "sheet")
                        fname = f"{base}.tsx"
                    else:
                        fname = Path(raw).name or "sheet.tsx"
                        if not fname.lower().endswith(".tsx"):
                            fname += ".tsx"
                    tsx_path = sheet_dir / fname
                    params["path"] = str(tsx_path)
                    produced_outputs.append({
                        "file_id": f"{sheet_dir.name}/{fname}",
                        "label": "build_tsx_sheet",
                        "name": "tsx",
                    })

            elif action_name == "brush_remap_tsx":
                # source / brush 都是输入图片；tsx / mapping_json 是同目录产物。
                for k in ("source", "brush"):
                    if k in params and params[k]:
                        params[k] = _materialize_input_path(params[k])

                raw_tsx = params.get("tsx")
                raw_json = params.get("mapping_json")
                out_dir = OUTPUT_DIR / f"brush_remap_{uuid.uuid4().hex[:8]}"
                out_dir.mkdir(parents=True, exist_ok=True)
                base = _safe_upload_stem(str(params.get("name") or "brush_remap"), "brush_remap")

                if not raw_tsx or raw_tsx == "auto":
                    tsx_fname = f"{base}.tsx"
                    tsx_out = out_dir / tsx_fname
                else:
                    tsx_fname = Path(raw_tsx).name or f"{base}.tsx"
                    if not tsx_fname.lower().endswith(".tsx"):
                        tsx_fname += ".tsx"
                    tsx_out = out_dir / tsx_fname
                params["tsx"] = str(tsx_out)
                produced_outputs.append({
                    "file_id": f"{out_dir.name}/{tsx_out.name}",
                    "label": "brush_remap_tsx",
                    "name": "tsx",
                })

                if not raw_json or raw_json == "auto":
                    json_fname = f"{Path(tsx_out.name).stem}.remap.json"
                    json_out = out_dir / json_fname
                else:
                    json_fname = Path(raw_json).name or f"{Path(tsx_out.name).stem}.remap.json"
                    if not json_fname.lower().endswith(".json"):
                        json_fname += ".json"
                    json_out = out_dir / json_fname
                params["mapping_json"] = str(json_out)
                produced_outputs.append({
                    "file_id": f"{out_dir.name}/{json_out.name}",
                    "label": "brush_remap_tsx",
                    "name": "remap_json",
                })

                if params.get("copy_brush_image", True):
                    brush_name = Path(str(params.get("brush") or "brush.png")).name
                    produced_outputs.append({
                        "file_id": f"{out_dir.name}/{brush_name}",
                        "label": "brush_remap_tsx",
                        "name": "brush_image",
                    })

            elif action_name == "remap_tmj_gids":
                for k in ("map_path", "mapping_json"):
                    if k in params and params[k]:
                        params[k] = _materialize_input_path(params[k])

                raw = params.get("output")
                map_suffix = Path(str(params.get("map_path") or "")).suffix.lower()
                out_suffix = ".tmx" if map_suffix == ".tmx" else ".tmj"
                out_id = _new_id("out", out_suffix)
                if not raw or raw == "auto":
                    out_path = OUTPUT_DIR / out_id
                else:
                    out_path = _materialize_output_path(raw)
                    if out_path.suffix.lower() not in (".tmj", ".json", ".tmx"):
                        out_path = out_path.with_suffix(out_suffix)
                params["output"] = str(out_path)
                produced_outputs.append({
                    "file_id": out_path.name if out_path.parent == OUTPUT_DIR else "",
                    "label": "remap_tmj_gids",
                    "name": "runtime_map",
                    "path": str(out_path),
                })

            steps_dict.append({"action": action_name, "params": params})

        # 2) 执行，并捕获 stdout（变量已在第 0 步替换过，这里 variables 传空）
        pipeline = Pipeline.from_dict({"name": "web", "steps": steps_dict})
        log_buf = io.StringIO()
        t0 = time.perf_counter()
        try:
            with redirect_stdout(log_buf):
                pipeline.run(variables={}, verbose=True)
            ok = True
            err = None
        except Exception as e:
            ok = False
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        # 3) save_all 的产物：扫描每个目录里的图片，给每张分配 file_id
        #    file_id 形如 "set_<8>/grass_NW.png"，斜杠安全（_resolve_file_id 兼容）
        for sub in save_all_dirs:
            if not sub.is_dir():
                continue
            for p in sorted(sub.iterdir()):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in (".png", ".webp", ".jpg", ".jpeg", ".bmp"):
                    continue
                rel = f"{sub.name}/{p.name}"
                produced_outputs.append({
                    "file_id": rel,
                    "label": "save_all",
                    "name": p.stem,
                })

        # 4) 给每个产物补 url，并额外生成本次运行的 zip 下载包
        for o in produced_outputs:
            fid = o.get("file_id")
            if fid:
                o["url"] = f"/api/file/{fid}"

        archive = _create_outputs_zip(produced_outputs) if ok else None

        return JSONResponse({
            "ok": ok,
            "elapsed_ms": elapsed_ms,
            "log": log_buf.getvalue(),
            "error": err,
            "outputs": produced_outputs,
            "archive": archive,
        })

    # ---- 前端静态资源 ----

    # workflow 持久化路由
    _register_workflow_routes(app)
    _register_docs_routes(app)

    if WEB_DIR.is_dir():
        # /static/* 映射到 web/。这里手写一个轻量路由而不用 StaticFiles，
        # 是为了能给所有静态资源加 Cache-Control: no-cache —— 否则前端
        # 改完代码用户必须 Ctrl+F5 才能看到，是个真实踩过的坑。
        from fastapi.responses import FileResponse, Response

        _STATIC_NO_CACHE = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }

        @app.get("/static/{rel:path}")
        def serve_static(rel: str):
            if ".." in rel.split("/"):
                raise HTTPException(400, "非法路径")
            p = (WEB_DIR / rel).resolve()
            try:
                p.relative_to(WEB_DIR.resolve())
            except ValueError:
                raise HTTPException(400, "非法路径")
            if not p.is_file():
                raise HTTPException(404, f"找不到: {rel}")
            return FileResponse(p, headers=_STATIC_NO_CACHE)

        @app.get("/", response_class=HTMLResponse)
        def index():
            idx = WEB_DIR / "index.html"
            if not idx.is_file():
                return HTMLResponse("<h1>web/index.html 不存在</h1>", status_code=500)
            return HTMLResponse(idx.read_text(encoding="utf-8"),
                                headers=_STATIC_NO_CACHE)

    return app


# ---------- 路径工具 ----------

_UPLOAD_SUFFIXES = (".png", ".webp", ".jpg", ".jpeg", ".bmp", ".tga", ".json", ".tmj", ".tsx")
_IMAGE_SUFFIXES = (".png", ".webp", ".jpg", ".jpeg", ".bmp", ".tga")


def _check_image_suffix(filename: Optional[str]) -> str:
    suffix = Path(filename or "").suffix.lower() or ".png"
    if suffix not in _UPLOAD_SUFFIXES:
        raise HTTPException(400, f"不支持的文件格式: {suffix}")
    return suffix


def _safe_upload_stem(stem: str, fallback: str = "image") -> str:
    safe = _re.sub(r"[^a-zA-Z0-9_.-]+", "_", stem).strip("._-")
    return safe[:80] or fallback


def _materialize_input_path(raw: Any) -> str:

    """load.path 解析：file_id → uploads 路径；其他视为磁盘路径。"""
    if raw is None:
        raise HTTPException(400, "load 缺少 path")
    s = str(raw)
    # 优先看 uploads
    p_up = UPLOAD_DIR / s
    if p_up.is_file():
        return str(p_up)
    # 也允许从 outputs 加载（链式 pipeline）
    p_out = OUTPUT_DIR / s
    if p_out.is_file():
        return str(p_out)
    # 否则按磁盘路径
    p = Path(s).expanduser()
    return str(p)


def _materialize_dir_path(raw: Any) -> str:
    """目录参数解析：batch_xxxx / set_xxxx → 运行期目录；绝对路径原样使用。"""
    if raw is None:
        raise HTTPException(400, "load_dir 缺少 path")
    s = str(raw)
    p = Path(s).expanduser()
    if p.is_absolute():
        return str(p)
    if "\\" in s or ".." in s.split("/"):
        raise HTTPException(400, "非法目录 id")

    for base in (UPLOAD_DIR, OUTPUT_DIR):
        cand = (base / s).resolve()
        try:
            cand.relative_to(RUNTIME_DIR.resolve())
        except ValueError:
            continue
        if cand.is_dir():
            return str(cand)
    # 找不到运行期目录时，按普通相对路径交给 action 自己报错（CLI / 本地调试友好）
    return str(p)


def _materialize_output_path(raw: Any) -> Path:
    """save.path 解析：相对路径写到 OUTPUT_DIR，绝对路径原样使用。"""
    s = str(raw)
    p = Path(s).expanduser()
    if p.is_absolute():
        return p
    # 纯文件名/相对路径都落到 OUTPUT_DIR，避免污染工作区
    return OUTPUT_DIR / p.name


# ---------- 参数智能类型转换 ----------

# 前端 resolvePlaceholders 把 ${target:96} 展开成字符串 "96" 后提交，
# 服务端要在送进 action 前转回 int，否则 PIL/numpy 会 TypeError。
# 后端的 _coerce_default 只在 _resolve_var 里跑，对"前端已展开后的字面量
# 字符串"覆盖不到，所以这里再做一道兜底。
#
# 跳过的字段名：那些**明确就是字符串语义**的字段（即便用户填 "123"
# 也是想要文件名"123"），不能误转成 int。
_STRING_SEMANTIC_KEYS = {
    "path", "dir", "pattern", "name", "source", "anchor", "mode",
    "preset", "terrain_spec", "grid_orientation", "wang_transform",
    "resample", "method", "format", "prefix",

    "foreground", "background",  # mask_blend_set 的输入路径
    "action",                    # for_each 嵌套 step 的 action 名
}


def _coerce_value(v: Any, key: Optional[str] = None) -> Any:
    """对 value 递归做"字符串数字 → int/float"转换。"""
    if isinstance(v, dict):
        return {k: _coerce_value(vv, k) for k, vv in v.items()}
    if isinstance(v, list):
        return [_coerce_value(x, key) for x in v]
    if isinstance(v, str):
        if key in _STRING_SEMANTIC_KEYS:
            return v
        return _coerce_str(v)
    return v


def _coerce_params(params: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _coerce_value(vv, k) for k, vv in params.items()}


# ---------- workflow 路由 ----------

class WorkflowSaveRequest(BaseModel):
    id: str                                # 文件名（不含 .json）
    name: Optional[str] = None             # 展示名，默认 = id
    description: Optional[str] = ""
    steps: List[Dict[str, Any]]            # pipeline 步骤


def _read_workflow_json(p: Path) -> Dict[str, Any]:
    data = json.loads(p.read_text(encoding="utf-8"))
    return {
        "id": p.stem,
        "name": data.get("name") or p.stem,
        "description": data.get("description", ""),
        "steps": data.get("steps") or [],
        "source": "user",
        "path": str(p),
    }


def _read_pipeline_yaml(p: Path) -> Dict[str, Any]:
    """把仓库自带的 YAML pipeline 也包成同样的结构，供前端只读加载。"""
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {
        "id": f"yaml:{p.stem}",          # 加前缀避免和用户 id 撞
        "name": data.get("name") or p.stem,
        "description": data.get("description", ""),
        "steps": data.get("steps") or [],
        "source": "builtin",
        "path": str(p),
    }


def _register_workflow_routes(app: FastAPI) -> None:

    @app.get("/api/workflows")
    def list_workflows():
        items: List[Dict[str, Any]] = []
        # 用户存的 JSON
        if WORKFLOWS_DIR.is_dir():
            for p in sorted(WORKFLOWS_DIR.glob("*.json")):
                try:
                    items.append(_read_workflow_json(p))
                except Exception as e:
                    print(f"[workflows] 跳过损坏的 {p.name}: {e}")
        # 自带的 YAML pipeline（只读）
        if PIPELINES_DIR.is_dir():
            for p in sorted(PIPELINES_DIR.glob("*.yaml")):
                try:
                    item = _read_pipeline_yaml(p)
                    if item:
                        items.append(item)
                except Exception as e:
                    print(f"[workflows] 跳过损坏的 {p.name}: {e}")
        return {"workflows": items}

    @app.get("/api/workflows/{wid:path}")
    def get_workflow(wid: str):
        # YAML 只读项
        if wid.startswith("yaml:"):
            stem = wid[len("yaml:"):]
            if not _VALID_ID.match(stem):
                raise HTTPException(400, "非法 id")
            p = PIPELINES_DIR / f"{stem}.yaml"
            if not p.is_file():
                raise HTTPException(404, "找不到 workflow")
            return _read_pipeline_yaml(p)
        # 用户 JSON
        _check_workflow_id(wid)
        p = WORKFLOWS_DIR / f"{wid}.json"
        if not p.is_file():
            raise HTTPException(404, "找不到 workflow")
        return _read_workflow_json(p)

    @app.post("/api/workflows")
    def save_workflow(req: WorkflowSaveRequest):
        _check_workflow_id(req.id)
        p = WORKFLOWS_DIR / f"{req.id}.json"
        payload = {
            "name": req.name or req.id,
            "description": req.description or "",
            "steps": req.steps,
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return {"ok": True, "id": req.id, "path": str(p)}

    @app.delete("/api/workflows/{wid}")
    def delete_workflow(wid: str):
        _check_workflow_id(wid)
        p = WORKFLOWS_DIR / f"{wid}.json"
        if not p.is_file():
            raise HTTPException(404, "找不到 workflow")
        p.unlink()
        return {"ok": True, "id": wid}


# ---------- 教程 markdown 路由 ----------

# 教程 id 只允许字母数字下划线（与 _check_workflow_id 区分开，不收 `-`，
# 因为我们的教程文件用下划线命名约定：01_quick_start.md）
_VALID_DOC_ID = _re.compile(r"^[a-zA-Z0-9_]{1,64}$")


def _doc_title(content: str, fallback: str) -> str:
    """从 markdown 第一行 `# Title` 提取标题；没有就用 fallback。"""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line:  # 第一行不是标题就停，避免误读
            break
    return fallback


def _register_docs_routes(app: FastAPI) -> None:

    @app.get("/api/docs")
    def list_docs():
        items: List[Dict[str, Any]] = []
        if DOCS_DIR.is_dir():
            for p in sorted(DOCS_DIR.glob("*.md")):
                try:
                    content = p.read_text(encoding="utf-8")
                except Exception as e:
                    print(f"[docs] 跳过 {p.name}: {e}")
                    continue
                title = _doc_title(content, p.stem)
                items.append({
                    "id": p.stem,
                    "title": title,
                    "filename": p.name,
                })
        return {"docs": items}

    @app.get("/api/docs/{doc_id}")
    def get_doc(doc_id: str):
        if not _VALID_DOC_ID.match(doc_id):
            raise HTTPException(400, f"非法 doc id: {doc_id!r}")
        p = DOCS_DIR / f"{doc_id}.md"
        if not p.is_file():
            raise HTTPException(404, f"找不到教程: {doc_id}")
        content = p.read_text(encoding="utf-8")
        return {
            "id": doc_id,
            "title": _doc_title(content, doc_id),
            "filename": p.name,
            "content": content,   # raw markdown，前端自己渲染
        }

    @app.get("/docs-assets/{rel:path}")
    def get_doc_asset(rel: str):
        """Serve images and downloadable artifacts referenced by bundled docs."""
        if "\\" in rel or ".." in rel.split("/"):
            raise HTTPException(400, "非法路径")
        p = (DOCS_DIR / rel).resolve()
        try:
            p.relative_to(DOCS_DIR.resolve())
        except ValueError:
            raise HTTPException(400, "非法路径")
        if not p.is_file():
            raise HTTPException(404, f"找不到文档资源: {rel}")
        return FileResponse(p)


def main(host: str = "127.0.0.1", port: int = 8765, reload: bool = False) -> None:
    try:
        import uvicorn  # type: ignore
    except ImportError:
        print("缺少依赖，请先：pip install fastapi uvicorn python-multipart", file=sys.stderr)
        raise SystemExit(1)

    if reload:
        # 热重载：监听整个 tiled_tools 包，一改就自动重启 worker
        watch_dir = str(Path(__file__).resolve().parent)
        uvicorn.run(
            "tiled_tools.server:create_app",
            host=host, port=port,
            reload=True, factory=True,
            reload_dirs=[watch_dir],
        )
    else:
        uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
