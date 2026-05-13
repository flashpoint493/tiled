# -*- coding: utf-8 -*-
"""FastAPI 后端：把 tiled_tools 暴露成 HTTP 服务给前端用。

启动：
    python -m tiled_tools serve --port 8765
浏览器打开：
    http://localhost:8765/

路由：
    GET  /api/actions              列出所有 action 及其参数 schema
    POST /api/upload               上传图片，返回 {file_id, filename, url}
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
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .core.action import Context
from .core.pipeline import Pipeline, _substitute as _pipeline_substitute
from .core.registry import available_actions, get_action

# 注册表里的 Action 类
from .core.registry import _REGISTRY  # type: ignore[attr-defined]


# ---------- 路径约定 ----------
# server.py 在 scripts/tiled_tools/server.py
# scripts/                 = 项目根
#   ├── web/               = 前端静态资源
#   ├── .web_runtime/      = 运行期文件（uploads / outputs）
SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = SCRIPTS_ROOT / "web"
RUNTIME_DIR = SCRIPTS_ROOT / ".web_runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
OUTPUT_DIR = RUNTIME_DIR / "outputs"
# 用户编辑/保存的 workflow（前端写）
WORKFLOWS_DIR = SCRIPTS_ROOT / "workflows"
# 仓库自带的 YAML pipeline（手写、只读）
PIPELINES_DIR = SCRIPTS_ROOT / "pipelines"


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
    print(f"[server] tiled_tools loaded from: {SCRIPTS_ROOT}")
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
        suffix = Path(file.filename or "").suffix.lower() or ".png"
        if suffix not in (".png", ".webp", ".jpg", ".jpeg", ".bmp", ".tga"):
            raise HTTPException(400, f"不支持的图片格式: {suffix}")
        file_id = _new_id("up", suffix)
        dest = UPLOAD_DIR / file_id
        data = await file.read()
        dest.write_bytes(data)
        return {
            "file_id": file_id,
            "filename": file.filename,
            "url": f"/api/file/{file_id}",
            "size_bytes": len(data),
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
        # 0) 先做一遍变量替换：把 ${output:auto} 这类提前展开成 "auto"，
        #    否则下面 raw == "auto" 判断不到。
        try:
            steps_substituted = [
                {
                    "action": s.action,
                    "params": _pipeline_substitute(dict(s.params), req.variables or {}),
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

        # 4) 给每个产物补 url
        for o in produced_outputs:
            fid = o.get("file_id")
            if fid:
                o["url"] = f"/api/file/{fid}"

        return JSONResponse({
            "ok": ok,
            "elapsed_ms": elapsed_ms,
            "log": log_buf.getvalue(),
            "error": err,
            "outputs": produced_outputs,
        })

    # ---- 前端静态资源 ----

    # workflow 持久化路由
    _register_workflow_routes(app)

    if WEB_DIR.is_dir():
        # 把 /static/* 映射到 web/ ，再让 / 返回 index.html
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/", response_class=HTMLResponse)
        def index():
            idx = WEB_DIR / "index.html"
            if not idx.is_file():
                return HTMLResponse("<h1>web/index.html 不存在</h1>", status_code=500)
            return HTMLResponse(idx.read_text(encoding="utf-8"))

    return app


# ---------- 路径工具 ----------

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


def _materialize_output_path(raw: Any) -> Path:
    """save.path 解析：相对路径写到 OUTPUT_DIR，绝对路径原样使用。"""
    s = str(raw)
    p = Path(s).expanduser()
    if p.is_absolute():
        return p
    # 纯文件名/相对路径都落到 OUTPUT_DIR，避免污染工作区
    return OUTPUT_DIR / p.name


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
