/* tiled_tools 前端 SPA
 *
 * 状态：
 *   state.actions    - 后端拉来的所有 action schema
 *   state.uploaded   - 最近一次上传的 {file_id, url, filename}
 *   state.steps      - pipeline，[{id, action, params}]，UI 直接驱动这个
 *   state.workflows  - 后端可加载的 workflow 列表
 *   state.currentWid - 当前选中的 workflow id（仅用于"删除当前"按钮）
 */

const $ = (sel) => document.querySelector(sel);

const state = {
  actions: [],
  actionMap: {},
  uploaded: null,
  batchUploaded: null,
  steps: [],

  workflows: [],
  currentWid: "",
  _uid: 0,
};

const newId = () => `s${++state._uid}`;

// ---------------- 启动 ----------------

async function init() {
  // 先绑定 UI 事件——即便后端没起来 / 网络错误，按钮也不至于完全失灵
  // （比如「📖 帮助」按钮就是纯前端可用的）。
  bindGlobalEvents();

  try {
    const res = await fetch("/api/actions");
    if (!res.ok) throw new Error(`/api/actions 返回 ${res.status}`);
    const data = await res.json();
    state.actions = data.actions;
    state.actionMap = Object.fromEntries(state.actions.map(a => [a.name, a]));
    renderActionLibrary();
    await refreshWorkflows();

    // 初始 demo
    if (state.actionMap.load && state.actionMap.topdown_to_iso && state.actionMap.save) {
      addStep("load");
      addStep("topdown_to_iso");
      addStep("save");
    }
  } catch (e) {
    console.error("[init] 加载失败:", e);
    const list = document.getElementById("action-list");
    if (list) list.innerHTML =
      `<li class="muted">加载 actions 失败：${escapeHtml(String(e))}<br/>` +
      `请确认 server 已启动（python -m tiled_tools serve）</li>`;
  }
}

// ---------------- 左侧 action 库 ----------------

function renderActionLibrary() {
  const ul = $("#action-list");
  const filter = ($("#action-search").value || "").toLowerCase();
  ul.innerHTML = "";
  for (const a of state.actions) {
    if (filter && !a.name.includes(filter) &&
        !(a.description || "").toLowerCase().includes(filter)) continue;
    const li = document.createElement("li");
    li.draggable = true;
    li.dataset.action = a.name;
    li.innerHTML = `
      <div class="a-name">${a.name}</div>
      <div class="a-desc">${escapeHtml(a.description || "")}</div>
    `;
    li.addEventListener("click", () => addStep(a.name));
    li.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/x-action", a.name);
      e.dataTransfer.effectAllowed = "copy";
    });
    ul.appendChild(li);
  }
}

// ---------------- pipeline 操作 ----------------

function addStep(actionName, paramsOverride = null) {
  const def = state.actionMap[actionName];
  if (!def) { alert(`未知 action: ${actionName}`); return; }
  const params = paramsOverride ?? defaultParams(def);
  state.steps.push({ id: newId(), action: actionName, params });
  renderPipeline();
}

function defaultParams(def) {
  const p = {};
  for (const f of def.params) {
    if ("default" in f) {
      p[f.name] = deepClone(f.default);
    } else if (f.required) {
      p[f.name] = f.type === "boolean" ? false :
                  (f.type === "integer" || f.type === "number") ? 0 : "";
    }
  }
  // for_each.steps 默认空数组
  if (def.name === "for_each") p.steps = p.steps || [];
  if (def.name === "load" && state.uploaded) p.path = state.uploaded.file_id;
  if (def.name === "save") p.path = p.path || "auto";
  return p;
}

function removeStep(id) {
  state.steps = state.steps.filter(s => s.id !== id);
  renderPipeline();
}

function moveStep(fromIdx, toIdx) {
  if (fromIdx === toIdx) return;
  const [item] = state.steps.splice(fromIdx, 1);
  state.steps.splice(toIdx, 0, item);
  renderPipeline();
}

function renderPipeline() {
  const ol = $("#pipeline");
  $("#step-count").textContent = `${state.steps.length} 步`;
  $("#pipeline-empty").style.display = state.steps.length ? "none" : "block";
  ol.innerHTML = "";

  state.steps.forEach((step, idx) => {
    const def = state.actionMap[step.action];
    if (!def) return;

    const li = document.createElement("li");
    li.className = "step";
    li.draggable = true;
    li.dataset.id = step.id;
    li.dataset.idx = idx;

    li.innerHTML = `
      <div class="step-header">
        <span class="idx">${idx + 1}</span>
        <span class="name">${step.action}</span>
        <span class="step-actions">
          <button data-act="up"   title="上移">↑</button>
          <button data-act="down" title="下移">↓</button>
          <button data-act="del"  title="删除">✕</button>
        </span>
      </div>
      <div class="step-body"></div>
    `;
    const body = li.querySelector(".step-body");
    for (const field of def.params) {
      body.appendChild(renderField(step, field));
    }

    li.querySelector('[data-act="up"]').onclick = () => moveStep(idx, Math.max(0, idx - 1));
    li.querySelector('[data-act="down"]').onclick = () => moveStep(idx, Math.min(state.steps.length - 1, idx + 1));
    li.querySelector('[data-act="del"]').onclick = () => removeStep(step.id);

    li.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/x-step-idx", String(idx));
      e.dataTransfer.effectAllowed = "move";
      li.classList.add("dragging");
    });
    li.addEventListener("dragend", () => li.classList.remove("dragging"));
    li.addEventListener("dragover", (e) => { e.preventDefault(); });
    li.addEventListener("drop", (e) => {
      e.preventDefault();
      const newAction = e.dataTransfer.getData("text/x-action");
      if (newAction) {
        addStep(newAction);
        moveStep(state.steps.length - 1, idx);
        return;
      }
      const fromIdx = Number(e.dataTransfer.getData("text/x-step-idx"));
      if (!Number.isNaN(fromIdx)) moveStep(fromIdx, idx);
    });

    ol.appendChild(li);
  });
}

// 渲染单个参数控件
function renderField(step, field) {
  // 特殊：subpipe widget = 嵌套子 pipeline 编辑器
  if (field.widget === "subpipe") {
    return renderSubpipeField(step, field);
  }

  const wrap = document.createElement("div");
  const isFull = field.type === "tuple" || field.type === "any" || field.widget === "filepath";
  wrap.className = "field" + (isFull ? " full" : "");

  const label = document.createElement("label");
  label.innerHTML = field.name +
    (field.required ? '<span class="req">*</span>' : '') +
    ` <span class="muted">(${field.type})</span>`;
  wrap.appendChild(label);

  const cur = step.params[field.name];
  let input;

  if (field.enum) {
    input = document.createElement("select");
    for (const opt of field.enum) {
      const o = document.createElement("option");
      o.value = opt; o.textContent = opt === "" ? "(自动)" : opt;
      if (String(cur ?? "") === String(opt)) o.selected = true;
      input.appendChild(o);
    }
    input.onchange = () => { step.params[field.name] = input.value; };
  } else if (field.type === "boolean") {
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = !!cur;
    input.onchange = () => { step.params[field.name] = input.checked; };
  } else if (field.type === "integer" || field.type === "number") {
    input = document.createElement("input");
    input.type = "number";
    if (field.step != null) input.step = field.step;
    if (field.min != null) input.min = field.min;
    if (field.max != null) input.max = field.max;
    if (field.type === "integer") input.step = input.step || 1;
    input.value = cur ?? "";
    input.onchange = () => {
      const v = input.value === "" ? null : Number(input.value);
      step.params[field.name] = v;
    };
  } else if (field.type === "tuple") {
    input = document.createElement("input");
    input.type = "text";
    input.placeholder = "如 0,0,0,0";
    input.value = Array.isArray(cur) ? cur.join(",") : (cur ?? "");
    input.onchange = () => {
      const parts = input.value.split(",").map(s => s.trim()).filter(s => s !== "");
      step.params[field.name] = parts.map(s => isNaN(+s) ? s : +s);
    };
  } else {
    input = document.createElement("input");
    input.type = "text";
    input.value = cur ?? "";
    input.onchange = () => { step.params[field.name] = input.value; };
    if (step.action === "load" && field.name === "path") {
      input.placeholder = "上传后自动填，或手填 file_id / 绝对路径";
    }
    if (step.action === "save" && field.name === "path") {
      input.placeholder = "auto = 自动分配；或写文件名 / 绝对路径";
    }
  }

  // filepath widget 字段：在右侧加 📎 上传按钮，点它直接上传并填入 file_id
  // 这解决了"workflow 有多个输入图（如 mask_blend_set.foreground/background）
  // 时顶栏上传按钮只能填一个 load.path"的问题。
  if (field.widget === "filepath") {
    const row = document.createElement("div");
    row.className = "filepath-row";
    row.appendChild(input);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn ghost filepath-upload";
    btn.title = "上传图片填入此字段";
    btn.textContent = "📎";

      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = "image/*,.json,.tmj,.tmx,.tsx";
      fileInput.hidden = true;

    btn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const f = fileInput.files?.[0];
      fileInput.value = "";
      if (!f) return;
      btn.textContent = "⏳";
      btn.disabled = true;
      try {
        const fd = new FormData();
        fd.append("file", f);
        const r = await fetch("/api/upload", { method: "POST", body: fd });
        if (!r.ok) throw new Error(`upload 返回 ${r.status}`);
        const data = await r.json();
        // 写回 state + 触发 UI
        input.value = data.file_id;
        step.params[field.name] = data.file_id;
        // 顺便：如果上传到的是 load.path，更新原图预览（沿用现有逻辑）
        if (step.action === "load" && field.name === "path") {
          state.uploaded = data;
          renderSourcePreview();
        }
      } catch (e) {
        alert(`上传失败: ${e.message || e}`);
      } finally {
        btn.textContent = "📎";
        btn.disabled = false;
      }
    });

    row.appendChild(btn);
    row.appendChild(fileInput);
    wrap.appendChild(row);
    return wrap;
  }

  wrap.appendChild(input);
  return wrap;
}

// ---------------- for_each 子 pipeline 编辑器 ----------------

function renderSubpipeField(step, field) {
  const wrap = document.createElement("div");
  wrap.className = "field full";

  const label = document.createElement("label");
  label.innerHTML = field.name + ` <span class="muted">(子 pipeline)</span>`;
  wrap.appendChild(label);

  // step.params.steps 是数组 [{action, params}]
  const subs = step.params[field.name] = step.params[field.name] || [];

  const box = document.createElement("div");
  box.className = "subpipe";
  box.innerHTML = `
    <div class="subpipe-header">
      <span class="muted">每张 tile 都会按下面的步骤处理</span>
      <select class="add-sub">
        <option value="">+ 添加子步骤…</option>
      </select>
    </div>
    <div class="sub-list"></div>
  `;
  // 填 select
  const sel = box.querySelector(".add-sub");
  for (const a of state.actions) {
    // 子 pipeline 里不让放 load/save/save_all/for_each/split_3x3 这种"主流程"才合理的
    if (["load", "save", "save_all", "for_each", "split_3x3"].includes(a.name)) continue;
    const opt = document.createElement("option");
    opt.value = a.name; opt.textContent = a.name;
    sel.appendChild(opt);
  }
  sel.onchange = () => {
    const name = sel.value;
    if (!name) return;
    const def = state.actionMap[name];
    subs.push({ action: name, params: defaultParams(def) });
    sel.value = "";
    renderPipeline();
  };

  const list = box.querySelector(".sub-list");
  if (subs.length === 0) {
    const tip = document.createElement("div");
    tip.className = "subpipe-empty";
    tip.textContent = "选一个 action 加进来。例如 topdown_to_iso、scale。";
    list.appendChild(tip);
  } else {
    subs.forEach((sub, sidx) => {
      list.appendChild(renderSubstep(subs, sidx, step));
    });
  }

  wrap.appendChild(box);
  return wrap;
}

function renderSubstep(subs, sidx, parentStep) {
  const sub = subs[sidx];
  const def = state.actionMap[sub.action];
  const div = document.createElement("div");
  div.className = "substep";

  div.innerHTML = `
    <div class="substep-head">
      <span class="muted">${sidx + 1}.</span>
      <span class="name">${sub.action}</span>
      <button data-act="up"   title="上移">↑</button>
      <button data-act="down" title="下移">↓</button>
      <button data-act="del"  title="删除">✕</button>
    </div>
    <div class="substep-body"></div>
  `;
  const body = div.querySelector(".substep-body");
  if (def) {
    for (const f of def.params) {
      // 子步骤里不再嵌 subpipe，避免无限递归
      if (f.widget === "subpipe") continue;
      body.appendChild(renderField(sub, f));
    }
  } else {
    body.textContent = `未知 action: ${sub.action}`;
  }

  div.querySelector('[data-act="up"]').onclick = () => {
    if (sidx === 0) return;
    [subs[sidx - 1], subs[sidx]] = [subs[sidx], subs[sidx - 1]];
    renderPipeline();
  };
  div.querySelector('[data-act="down"]').onclick = () => {
    if (sidx >= subs.length - 1) return;
    [subs[sidx + 1], subs[sidx]] = [subs[sidx], subs[sidx + 1]];
    renderPipeline();
  };
  div.querySelector('[data-act="del"]').onclick = () => {
    subs.splice(sidx, 1);
    renderPipeline();
  };

  return div;
}

// ---------------- 上传 / 运行 / 导入导出 ----------------

async function handleUpload(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: fd });
  if (!res.ok) { alert("上传失败"); return; }
  const data = await res.json();
  state.uploaded = data;
  state.batchUploaded = null;
  renderSourcePreview();
  for (const s of state.steps) {
    if (s.action === "load") s.params.path = data.file_id;
  }
  renderPipeline();
}

async function handleBatchUpload(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  if (!state.actionMap.load_dir || !state.actionMap.pack_sheet || !state.actionMap.build_tsx_sheet) {
    alert("缺少 load_dir / pack_sheet / build_tsx_sheet action，请重启 server 确认 action 已注册");
    return;
  }

  const log = $("#log");
  log.classList.remove("error");
  log.textContent = `批量上传 ${files.length} 张图片…`;

  const fd = new FormData();
  for (const f of files) fd.append("files", f);

  let data;
  try {
    const res = await fetch("/api/upload-batch", { method: "POST", body: fd });
    if (!res.ok) throw new Error(`upload-batch 返回 ${res.status}`);
    data = await res.json();
  } catch (e) {
    log.classList.add("error");
    log.textContent = `批量上传失败: ${e.message || e}`;
    return;
  }

  state.uploaded = null;
  state.batchUploaded = data;
  renderBatchSourcePreview();
  buildBatchTilesheetPipeline(data);
  log.textContent = `已批量导入 ${data.count} 张图片，正在组成 tilesheet…`;
  await handleRun();
}

// 把上传成功后的预览刷新抽出来，供顶栏上传 + filepath 字段 📎 上传共用
function renderSourcePreview() {
  const data = state.uploaded;
  if (!data) return;
  $("#src-preview").innerHTML = `<img src="${data.url}" alt="src" />`;
  $("#src-meta").textContent = `${data.filename} (${(data.size_bytes / 1024).toFixed(1)} KB)`;
}

function renderBatchSourcePreview() {
  const data = state.batchUploaded;
  if (!data) return;
  const files = data.files || [];
  const cells = files.slice(0, 12).map(f => `
    <div class="src-cell">
      <img src="${f.url}?t=${Date.now()}" alt="${escapeHtml(f.filename)}" />
    </div>
  `).join("");
  $("#src-preview").innerHTML = `<div class="src-grid">${cells}</div>`;
  $("#src-meta").textContent = `${files.length} 张图片 → ${data.dir_id}（已自动生成 tilesheet pipeline）`;
}

function buildBatchTilesheetPipeline(data) {
  const makeStep = (action, params) => {
    const def = state.actionMap[action];
    return { id: newId(), action, params: { ...defaultParams(def), ...params } };
  };

  state.steps = [];
  state._uid = 0;
  state.currentWid = "";
  state.steps.push(
    makeStep("load_dir", { path: data.dir_id, pattern: "*", sort: true, limit: 0 }),
    makeStep("pack_sheet", { path: "auto", columns: null, spacing: 0, margin: 0, pad_anchor: "center" }),
    makeStep("build_tsx_sheet", { path: "auto", name: "batch_tilesheet", tile_names: true }),
  );
  renderPipeline();
}

function isImageOutput(o) {
  const s = String(o.file_id || o.path || o.url || "");
  return /\.(png|webp|jpe?g|bmp|gif)$/i.test(s);
}

async function handleRun() {

  const log = $("#log");
  log.classList.remove("error");
  log.textContent = "运行中…";
  $("#out-preview").innerHTML = `<span class="muted">运行中…</span>`;
  $("#out-meta").textContent = "";

  const body = {
    pipeline: state.steps.map(s => ({ action: s.action, params: s.params })),
    variables: {},
  };
  let res, data;
  try {
    res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    data = await res.json();
  } catch (e) {
    log.classList.add("error");
    log.textContent = `请求失败: ${e}`;
    return;
  }

  log.textContent = (data.log || "") + (data.error ? `\n\n[ERROR]\n${data.error}` : "");
  if (!data.ok) {
    log.classList.add("error");
    $("#out-preview").innerHTML = `<span class="muted">失败</span>`;
    $("#out-count").textContent = "";
    return;
  }

  const outs = (data.outputs || []).filter(o => o.url);
  const archive = data.archive && data.archive.url ? data.archive : null;
  $("#out-count").textContent = outs.length ? `(${outs.length} 张)` : "";

  if (outs.length === 0) {
    $("#out-preview").innerHTML = `<span class="muted">无产物</span>`;
    $("#out-meta").textContent = `${data.elapsed_ms}ms`;
  } else if (outs.length === 1) {
    const last = outs[0];
    const label = escapeHtml(last.name || last.label || last.file_id || last.path || "out");
    if (isImageOutput(last)) {
      const url = `${last.url}?t=${Date.now()}`;
      $("#out-preview").innerHTML = `<img src="${url}" alt="out" />`;
    } else {
      $("#out-preview").innerHTML = `<a class="file-card" href="${last.url}" target="_blank" download>${label}</a>`;
    }
    $("#out-meta").textContent = `${last.file_id || last.path}  (${data.elapsed_ms}ms)`;
  } else {
    const cols = (outs.length === 9) ? 3 : (outs.length <= 4 ? 2 : 3);
    const cells = outs.map(o => {
      const label = escapeHtml(o.name || o.label || o.file_id || "");
      if (isImageOutput(o)) {
        const url = `${o.url}?t=${Date.now()}`;
        return `<div class="out-cell">
          <a href="${o.url}" target="_blank" download><img src="${url}" alt="${label}" /></a>
          ${label ? `<span class="label">${label}</span>` : ""}
        </div>`;
      }
      return `<div class="out-cell file-out">
        <a href="${o.url}" target="_blank" download>${label || "file"}</a>
      </div>`;
    }).join("");
    const archiveBar = archive
      ? `<div class="out-toolbar"><a class="btn primary out-download-all" href="${archive.url}" download>⬇ 下载全部 .zip</a></div>`
      : "";
    $("#out-preview").innerHTML = `${archiveBar}<div class="out-grid cols-${cols}">${cells}</div>`;
    $("#out-meta").textContent = archive
      ? `${outs.length} 个产物，可一键下载全部或逐个点击下载  (${data.elapsed_ms}ms)`
      : `${outs.length} 个产物，点击下载  (${data.elapsed_ms}ms)`;
  }
}


function handleExport() {
  const data = {
    name: "exported",
    steps: state.steps.map(s => ({ action: s.action, params: s.params })),
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "pipeline.json";
  a.click();
}

async function handleImport(file) {
  const text = await file.text();
  let data;
  try { data = JSON.parse(text); }
  catch { alert("不是合法 JSON"); return; }
  if (!Array.isArray(data.steps)) { alert("缺少 steps 字段"); return; }
  loadStepsArray(data.steps);
}

// ---------------- workflow ----------------

async function refreshWorkflows() {
  const sel = $("#workflow-select");
  const prev = sel.value;
  try {
    const res = await fetch("/api/workflows");
    const data = await res.json();
    state.workflows = data.workflows || [];
  } catch {
    state.workflows = [];
  }
  // 渲染
  sel.innerHTML = `<option value="">— 选择 workflow —</option>`;
  const userItems = state.workflows.filter(w => w.source === "user");
  const builtinItems = state.workflows.filter(w => w.source === "builtin");
  if (userItems.length) {
    const g = document.createElement("optgroup");
    g.label = "已保存";
    for (const w of userItems) {
      const o = document.createElement("option");
      o.value = w.id; o.textContent = w.name;
      g.appendChild(o);
    }
    sel.appendChild(g);
  }
  if (builtinItems.length) {
    const g = document.createElement("optgroup");
    g.label = "内置（只读）";
    for (const w of builtinItems) {
      const o = document.createElement("option");
      o.value = w.id; o.textContent = w.name;
      g.appendChild(o);
    }
    sel.appendChild(g);
  }
  sel.value = prev || "";
}

async function handleLoadWorkflow(wid) {
  state.currentWid = wid;
  if (!wid) return;
  const res = await fetch(`/api/workflows/${encodeURIComponent(wid)}`);
  if (!res.ok) { alert("加载失败"); return; }
  const data = await res.json();
  loadStepsArray(data.steps || []);
}

function loadStepsArray(steps) {
  state.steps = [];
  state._uid = 0;
  for (const s of steps) {
    const def = state.actionMap[s.action];
    if (!def) {
      console.warn("未知 action，跳过:", s.action);
      continue;
    }
    // 展开 ${...} 占位符（CLI YAML 习惯），让 web 用户拿到能直接跑的值
    const resolvedParams = resolvePlaceholders(s.params || {}, s.action);
    // 把 default 与已有 params 合并，保证表单不会缺字段
    const merged = { ...defaultParams(def), ...resolvedParams };
    addStep(s.action, merged);
  }
  // 上传过的话，自动把 load 的 path 替换成最新 file_id
  if (state.uploaded) {
    for (const s of state.steps) {
      if (s.action === "load") s.params.path = state.uploaded.file_id;
    }
    renderPipeline();
  }
}

// ${var} / ${var:default} 占位符的前端展开
//   - 已知占位符按 action 语义给"web 端能跑通"的值
//   - 带 :default 的优先用默认值
//   - 不认识的留 null（前端表单显示空，提醒用户填）
const _PLACEHOLDER_RE = /^\s*\$\{([a-zA-Z_][a-zA-Z0-9_]*)(?::-?([^}]*))?\}\s*$/;

function resolvePlaceholders(params, actionName) {
  const out = {};
  for (const [k, v] of Object.entries(params)) {
    out[k] = resolveOne(v, actionName, k);
  }
  return out;
}

function resolveOne(val, actionName, key) {
  if (Array.isArray(val)) {
    // 数组里每项可能是 substep ({action, params})
    return val.map(item => {
      if (item && typeof item === "object" && item.action && item.params) {
        return {
          action: item.action,
          params: resolvePlaceholders(item.params, item.action),
        };
      }
      return resolveOne(item, actionName, key);
    });
  }
  if (val && typeof val === "object") return val;
  if (typeof val !== "string") return val;
  const m = val.match(_PLACEHOLDER_RE);
  if (!m) return val;

  const name = m[1];
  const def = m[2];

  if (def !== undefined) return coerceDefault(def);
  const guess = guessByContext(name, actionName, key);
  if (guess !== undefined) return guess;
  return "";
}

// 镜像后端 pipeline.py 的 _coerce_default —— 把 YAML/CLI 里的字符串默认值
// 智能转为合适类型：${target:96} 默认 "96" 应该当 int 96，否则后续传给
// PIL.Image.new((side, side)) 会 TypeError。
function coerceDefault(s) {
  if (s === "") return "";
  const low = s.toLowerCase();
  if (low === "true" || low === "yes") return true;
  if (low === "false" || low === "no") return false;
  if (low === "null" || low === "none" || low === "~") return null;
  // int
  if (/^-?\d+$/.test(s)) {
    const n = parseInt(s, 10);
    if (Number.isFinite(n)) return n;
  }
  // float
  if (/^-?\d+\.\d+$/.test(s) || /^-?\.\d+$/.test(s) || /^-?\d+\.$/.test(s)) {
    const f = parseFloat(s);
    if (Number.isFinite(f)) return f;
  }
  return s;  // 非数字字符串原样保留（如 "auto"）
}

function guessByContext(varName, actionName, paramKey) {
  // input 类：上传的 file_id（如果有）
  if (varName === "input" || varName === "src") {
    return state.uploaded ? state.uploaded.file_id : "";
  }
  // output 类：save.path 用 auto；save_all.dir 也用 auto
  if (varName === "output" || varName === "out") {
    return actionName === "save" ? "auto" : "";
  }
  if (varName === "output_dir" || varName === "out_dir") {
    return "auto";
  }
  // prefix 留空，save_all 会用源文件名
  if (varName === "prefix") return "";
  return undefined;
}

async function handleSaveWorkflow() {
  if (state.steps.length === 0) { alert("当前 pipeline 为空"); return; }
  const id = prompt("workflow id（字母数字/下划线/横线，用作文件名）", state.currentWid || "");
  if (!id) return;
  if (!/^[a-zA-Z0-9_-]{1,64}$/.test(id)) {
    alert("非法 id：只允许字母数字/下划线/横线，最多 64 字符");
    return;
  }
  const name = prompt("workflow 显示名（可中文）", id) || id;
  const description = prompt("简短描述（可留空）", "") || "";
  const body = {
    id, name, description,
    steps: state.steps.map(s => ({ action: s.action, params: s.params })),
  };
  const res = await fetch("/api/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) { alert("保存失败"); return; }
  state.currentWid = id;
  await refreshWorkflows();
  $("#workflow-select").value = id;
}

async function handleDeleteWorkflow() {
  const wid = $("#workflow-select").value;
  if (!wid) { alert("先选一个 workflow"); return; }
  if (wid.startsWith("yaml:")) { alert("内置 YAML workflow 是只读的"); return; }
  if (!confirm(`删除 workflow "${wid}"？`)) return;
  const res = await fetch(`/api/workflows/${encodeURIComponent(wid)}`, { method: "DELETE" });
  if (!res.ok) { alert("删除失败"); return; }
  state.currentWid = "";
  await refreshWorkflows();
}

// ---------------- 事件绑定 ----------------

function bindGlobalEvents() {
  $("#action-search").addEventListener("input", renderActionLibrary);

  $("#upload-input").addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (f) handleUpload(f);
    e.target.value = "";
  });

  $("#batch-upload-input").addEventListener("change", (e) => {
    const files = e.target.files;
    if (files?.length) handleBatchUpload(files);
    e.target.value = "";
  });

  $("#run-btn").addEventListener("click", handleRun);

  $("#export-btn").addEventListener("click", handleExport);
  $("#import-input").addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (f) handleImport(f);
    e.target.value = "";
  });
  $("#clear-btn").addEventListener("click", () => {
    if (state.steps.length && !confirm("清空当前 pipeline？")) return;
    state.steps = []; renderPipeline();
  });

  $("#workflow-select").addEventListener("change", (e) => handleLoadWorkflow(e.target.value));
  $("#save-workflow-btn").addEventListener("click", handleSaveWorkflow);
  $("#delete-workflow-btn").addEventListener("click", handleDeleteWorkflow);

  // 帮助弹层
  const helpBtn = document.getElementById("help-btn");
  if (helpBtn) {
    helpBtn.addEventListener("click", openHelp);
    console.log("[init] help button bound");
  } else {
    console.warn("[init] 找不到 #help-btn —— index.html 可能是旧版，硬刷一下 (Ctrl+Shift+R)");
  }
  document.querySelectorAll("#help-modal [data-close]").forEach(el => {
    el.addEventListener("click", closeHelp);
  });

  const ol = $("#pipeline");
  ol.addEventListener("dragover", (e) => e.preventDefault());
  ol.addEventListener("drop", (e) => {
    e.preventDefault();
    const a = e.dataTransfer.getData("text/x-action");
    if (a) addStep(a);
  });

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "Enter") { e.preventDefault(); handleRun(); }
    // ? 打开帮助（非输入框里），Esc 关闭
    if (e.key === "Escape" && !$("#help-modal").hasAttribute("hidden")) {
      e.preventDefault(); closeHelp();
    }
    if (e.key === "?" && !["INPUT","TEXTAREA","SELECT"].includes(e.target.tagName)) {
      e.preventDefault(); openHelp();
    }
  });
}

// ---- 帮助弹层 ----

let _docsCache = null;

async function openHelp() {
  console.log("[help] open");
  const modal = $("#help-modal");
  if (!modal) {
    alert("帮助弹层 DOM 缺失：刷新一下（Ctrl+Shift+R）让 index.html 重载。");
    return;
  }
  modal.hidden = false;
  if (!_docsCache) {
    try {
      const r = await fetch("/api/docs");
      if (!r.ok) throw new Error(`/api/docs 返回 ${r.status}`);
      const d = await r.json();
      _docsCache = d.docs || [];
      console.log(`[help] 加载到 ${_docsCache.length} 篇教程`);
    } catch (e) {
      console.error("[help] 加载失败:", e);
      $("#doc-content").innerHTML =
        `<p style="color:#ef9999">加载教程列表失败: ${escapeHtml(String(e))}</p>`;
      _docsCache = [];
    }
    renderDocList();
    if (_docsCache.length) loadDoc(_docsCache[0].id);
  }
}

function closeHelp() { $("#help-modal").hidden = true; }

function renderDocList() {
  const ul = $("#doc-list");
  if (!_docsCache.length) {
    ul.innerHTML = `<li class="muted">暂无教程（scripts/docs/*.md）</li>`;
    return;
  }
  ul.innerHTML = _docsCache.map(d =>
    `<li data-id="${escapeHtml(d.id)}">${escapeHtml(d.title)}</li>`
  ).join("");
  ul.querySelectorAll("li[data-id]").forEach(li => {
    li.addEventListener("click", () => loadDoc(li.dataset.id));
  });
}

async function loadDoc(id) {
  $("#doc-list").querySelectorAll("li").forEach(li => {
    li.classList.toggle("active", li.dataset.id === id);
  });
  const box = $("#doc-content");
  box.innerHTML = `<p class="muted">加载中…</p>`;
  try {
    const r = await fetch(`/api/docs/${encodeURIComponent(id)}`);
    if (!r.ok) throw new Error(r.statusText);
    const d = await r.json();
    box.innerHTML = renderMarkdown(d.content);
    box.scrollTop = 0;
  } catch (e) {
    box.innerHTML = `<p style="color:#ef9999">加载失败: ${escapeHtml(String(e))}</p>`;
  }
}

// 极简 markdown 渲染器（仅支持本项目 docs 用到的语法子集）
// 故意不引第三方库——保持前端零构建零依赖。
// 支持：# ## ### | ``` ``` 代码块 | `inline` | **bold** *italic* |
// - / * / 1. 列表 | > 引用 | --- 分隔线 | | table | | [link](url) |
function renderMarkdown(src) {
  // Windows 环境下 markdown 文件常是 CRLF，去掉 \r 让行尾正则稳定
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let i = 0;

  // 预处理：把代码块先切出来占位，避免后续 inline 处理乱入
  const codeBlocks = [];
  const joined = lines.join("\n").replace(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g,
    (_, lang, body) => {
      const idx = codeBlocks.length;
      codeBlocks.push({ lang, body });
      return `\u0001CODE${idx}\u0001`;
    });
  const safeLines = joined.split("\n");

  while (i < safeLines.length) {
    const line = safeLines[i];

    // 代码块占位
    const cm = line.match(/^\u0001CODE(\d+)\u0001$/);
    if (cm) {
      const cb = codeBlocks[+cm[1]];
      out.push(`<pre><code>${escapeHtml(cb.body)}</code></pre>`);
      i++; continue;
    }

    // 标题
    const h = line.match(/^(#{1,6})\s+(.+)$/);
    if (h) {
      const lv = h[1].length;
      out.push(`<h${lv}>${renderInline(h[2])}</h${lv}>`);
      i++; continue;
    }

    // 水平分割
    if (/^---+\s*$/.test(line)) { out.push("<hr/>"); i++; continue; }

    // 表格（至少两行：| a | b |  和  | --- | --- |）
    if (/^\s*\|/.test(line) && i + 1 < safeLines.length && /^\s*\|[\s\-:|]+\|\s*$/.test(safeLines[i+1])) {
      const rows = [];
      while (i < safeLines.length && /^\s*\|/.test(safeLines[i])) {
        rows.push(safeLines[i]); i++;
      }
      const header = splitTableRow(rows[0]);
      const body = rows.slice(2).map(splitTableRow);
      out.push("<table><thead><tr>" +
        header.map(c => `<th>${renderInline(c)}</th>`).join("") +
        "</tr></thead><tbody>" +
        body.map(r => "<tr>" + r.map(c => `<td>${renderInline(c)}</td>`).join("") + "</tr>").join("") +
        "</tbody></table>");
      continue;
    }

    // 引用块
    if (/^>\s?/.test(line)) {
      const buf = [];
      while (i < safeLines.length && /^>\s?/.test(safeLines[i])) {
        buf.push(safeLines[i].replace(/^>\s?/, ""));
        i++;
      }
      out.push("<blockquote>" + renderInline(buf.join(" ")) + "</blockquote>");
      continue;
    }

    // 无序列表
    if (/^\s*[-*+]\s+/.test(line)) {
      const buf = [];
      while (i < safeLines.length && /^\s*[-*+]\s+/.test(safeLines[i])) {
        buf.push(safeLines[i].replace(/^\s*[-*+]\s+/, ""));
        i++;
      }
      out.push("<ul>" + buf.map(x => `<li>${renderInline(x)}</li>`).join("") + "</ul>");
      continue;
    }

    // 有序列表
    if (/^\s*\d+\.\s+/.test(line)) {
      const buf = [];
      while (i < safeLines.length && /^\s*\d+\.\s+/.test(safeLines[i])) {
        buf.push(safeLines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      out.push("<ol>" + buf.map(x => `<li>${renderInline(x)}</li>`).join("") + "</ol>");
      continue;
    }

    // 空行 → 段落分隔
    if (!line.trim()) { i++; continue; }

    // 普通段落（连续非空行合并）
    const buf = [line];
    i++;
    while (i < safeLines.length && safeLines[i].trim() &&
           !/^(#{1,6}\s|[-*+]\s|\d+\.\s|>|```|---+\s*$|\s*\|)/.test(safeLines[i]) &&
           !/^\u0001CODE\d+\u0001$/.test(safeLines[i])) {
      buf.push(safeLines[i]); i++;
    }
    out.push("<p>" + renderInline(buf.join(" ")) + "</p>");
  }

  return out.join("\n");
}

function splitTableRow(row) {
  return row.trim().replace(/^\||\|$/g, "").split("|").map(s => s.trim());
}

function renderInline(s) {
  // 先 escape，再把 markdown 特征用占位符保护，处理完再注入 tag
  s = escapeHtml(s);
  // `code`
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  // **bold**
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // *italic*（需避开已处理的 **）
  s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    // ![alt](url)
  s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g,
    (_, alt, u) => `<img class="doc-img" src="${u}" alt="${alt}" loading="lazy" />`);
  // [text](url)
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g,
    (_, t, u) => `<a href="${u}" target="_blank" rel="noopener">${t}</a>`);
  return s;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function deepClone(x) {
  if (x === null || typeof x !== "object") return x;
  if (Array.isArray(x)) return x.map(deepClone);
  const r = {}; for (const k in x) r[k] = deepClone(x[k]); return r;
}

init();
