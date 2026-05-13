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
  steps: [],
  workflows: [],
  currentWid: "",
  _uid: 0,
};

const newId = () => `s${++state._uid}`;

// ---------------- 启动 ----------------

async function init() {
  const res = await fetch("/api/actions");
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

  bindGlobalEvents();
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
  $("#src-preview").innerHTML = `<img src="${data.url}" alt="src" />`;
  $("#src-meta").textContent = `${data.filename} (${(data.size_bytes / 1024).toFixed(1)} KB)`;
  for (const s of state.steps) {
    if (s.action === "load") s.params.path = data.file_id;
  }
  renderPipeline();
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
  $("#out-count").textContent = outs.length ? `(${outs.length} 张)` : "";

  if (outs.length === 0) {
    $("#out-preview").innerHTML = `<span class="muted">无产物</span>`;
    $("#out-meta").textContent = `${data.elapsed_ms}ms`;
  } else if (outs.length === 1) {
    const last = outs[0];
    const url = `${last.url}?t=${Date.now()}`;
    $("#out-preview").innerHTML = `<img src="${url}" alt="out" />`;
    $("#out-meta").textContent = `${last.file_id || last.path}  (${data.elapsed_ms}ms)`;
  } else {
    const cols = (outs.length === 9) ? 3 : (outs.length <= 4 ? 2 : 3);
    const cells = outs.map(o => {
      const url = `${o.url}?t=${Date.now()}`;
      const label = escapeHtml(o.name || o.label || "");
      return `<div class="out-cell">
        <a href="${o.url}" target="_blank" download><img src="${url}" alt="${label}" /></a>
        ${label ? `<span class="label">${label}</span>` : ""}
      </div>`;
    }).join("");
    $("#out-preview").innerHTML = `<div class="out-grid cols-${cols}">${cells}</div>`;
    $("#out-meta").textContent = `${outs.length} 张产物，点击下载  (${data.elapsed_ms}ms)`;
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

  if (def !== undefined) return def;
  const guess = guessByContext(name, actionName, key);
  if (guess !== undefined) return guess;
  return "";
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

  const ol = $("#pipeline");
  ol.addEventListener("dragover", (e) => e.preventDefault());
  ol.addEventListener("drop", (e) => {
    e.preventDefault();
    const a = e.dataTransfer.getData("text/x-action");
    if (a) addStep(a);
  });

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "Enter") { e.preventDefault(); handleRun(); }
  });
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
