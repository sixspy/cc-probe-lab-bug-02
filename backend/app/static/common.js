
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + " " + r.status);
  return r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });
  const t = await r.text();
  let data;
  try { data = JSON.parse(t); } catch { data = { 原文: t }; }
  if (!r.ok) throw new Error((data && (data.错误 || data.detail)) || t || String(r.status));
  return data;
}
function 行(html) {
  const tr = document.createElement("tr");
  tr.innerHTML = html;
  return tr;
}
function 徽章(文, 类) {
  const tone = 类 || 命运色(文);
  return `<span class="徽章 ${tone || ""}">${安全文本(文)}</span>`;
}
function 空态(文) { return `<p class="说明">${安全文本(文)}</p>`; }
function 安全文本(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}
function 命运色(f) {
  if (["已入栏", "在栏", "已汇总", "对齐"].includes(f)) return "ok";
  if (["已坏点", "撕裂"].includes(f)) return "warn";
  return "";
}
function 渲染水位(el, o) {
  if (!el) return;
  el.innerHTML = "";
  for (const [标, 键] of [["观测报文","观测报文"],["在栏","在栏"],["站点汇总","站点汇总"],["坏点","坏点"]]) {
    const d = document.createElement("div");
    d.className = "水卡";
    d.innerHTML = `<div class="数">${o[键] ?? 0}</div><div class="标">${标}</div>`;
    el.appendChild(d);
  }
}
function 渲染门槛(el, 规) {
  if (!el) return;
  const r = 规 || {};
  el.innerHTML = `
    <div class="门槛卡"><div class="k">当前栏</div><div class="v">${安全文本(r["当前栏号"] || "—")}</div></div>
    <div class="门槛卡"><div class="k">PM25 上限</div><div class="v">${安全文本(r["PM25上限"] || "—")}</div></div>
    <div class="门槛卡"><div class="k">PM25 下限</div><div class="v">${安全文本(r["PM25下限"] || "—")}</div></div>
    <div class="门槛卡"><div class="k">标定偏移</div><div class="v">${安全文本(r["标定偏移上限"] || "—")}</div></div>
  `;
}
function 渲染批次表(el, rows, cols) {
  if (!el) return;
  if (!rows || !rows.length) {
    el.innerHTML = `<tr><td colspan="${cols.length}">${空态("尚无批次。")}</td></tr>`;
    return;
  }
  el.innerHTML = "";
  for (const r of rows) {
    const cells = cols.map((c) => `<td>${安全文本(r[c])}</td>`).join("");
    el.appendChild(行(cells));
  }
}
function 装载摘要文(r) {
  if (!r) return "";
  return `入流 ${r["入流"]||0} · 入栏 ${r["入栏"]||0} · 坏点 ${r["坏点"]||0} · 驳回 ${r["驳回"]||0}`;
}
function 结栏摘要文(r) {
  if (!r) return "";
  return `栏 ${r["栏号"]||"?"} · 汇总 ${r["汇总数"]||0} · 缓冲消耗 ${r["缓冲消耗"]||0}`;
}
function 贯验摘要文(r) {
  if (!r) return "";
  return `${r["是否对齐"]?"对齐":"撕裂"} · 在栏 ${r["在栏"]} · 汇总报文 ${r["汇总报文"]} · 坏点 ${r["坏点"]}`;
}
function 填命运字典(el, dict) {
  if (!el || !dict) return;
  el.innerHTML = Object.entries(dict).map(([k, v]) =>
    `<div class="只读框 上距8"><b class="铜字">${安全文本(k)}</b> · ${安全文本(v)}</div>`
  ).join("");
}

// 贯验扫描范围与对齐灯联剔：五个页面共用同一份真实齐套灯数据，
// 任何一页都必须可见“扫描范围 / 未扫行数 / 读引用 / 灯色”，不允许只刷装饰芯片。
function 扫描灯文案(d) {
  if (!d) return "未知";
  if (d["齐套"] === true) return "绿 · 齐套";
  if (d["灯色"] === "amber" || d["争用"] === true) return "黄 · 争用双态";
  return "红 · 不齐套";
}
function 渲染扫描范围卡(root, d) {
  if (!root) return;
  const data = d || {};
  const set = (k, v) => {
    const el = root.querySelector(`[data-k="${k}"]`);
    if (el) el.textContent = v;
  };
  set("扫描范围", data["扫描范围"] || "全量");
  set("未扫行数", String(data["未扫行数"] ?? "—"));
  set("齐套灯", 扫描灯文案(data));
  set("读引用", data["读引用"] || data["active_read"] || "full_cursor");
  set("扫描指纹", data["指纹"] || "");
  const lamp = root.querySelector('[data-k="齐套灯"]');
  if (lamp) {
    lamp.style.color = data["齐套"] === true ? "#1a7f37"
      : (data["灯色"] === "amber" ? "#9a6700" : "#cf222e");
  }
  root.setAttribute("data-aligned", data["齐套"] === true ? "1" : "0");
  root.setAttribute("data-scope", String(data["扫描范围"] || "全量"));
}
async function 挂载扫描范围卡(rootOrId) {
  const root = typeof rootOrId === "string" ? document.getElementById(rootOrId) : rootOrId;
  if (!root) return;
  try {
    const d = await getJSON("/api/pageblind/齐套灯");
    渲染扫描范围卡(root, d);
    window.__pageblind_qitao = d;
    window.__pageblind_chip = d["芯片"] || window.__pageblind_chip;
    const marker = document.getElementById("data-pageblind");
    if (marker) {
      marker.setAttribute("data-chip", d["芯片"] || "");
      marker.setAttribute("data-aligned", d["齐套"] === true ? "1" : "0");
      marker.setAttribute("data-scope", String(d["扫描范围"] || "全量"));
    }
  } catch (e) {
    const lamp = root.querySelector('[data-k="齐套灯"]');
    if (lamp) { lamp.textContent = "红 · 取灯失败"; lamp.style.color = "#cf222e"; }
  }
}
window.探栏 = {
  getJSON, postJSON, 行, 徽章, 空态, 安全文本, 命运色,
  渲染水位, 渲染门槛, 渲染批次表,
  装载摘要文, 结栏摘要文, 贯验摘要文, 填命运字典,
  渲染扫描范围卡, 挂载扫描范围卡, 扫描灯文案,
};
