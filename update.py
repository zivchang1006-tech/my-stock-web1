<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="theme-color" content="#070b14" />
  <title>台股每日盤後籌碼戰情室</title>
  <style>
    :root {
      --bg: #070b14;
      --panel: #0e1626;
      --panel-2: #131e33;
      --border: rgba(148, 163, 184, 0.16);
      --text: #e5edf7;
      --muted: #8fa1bc;
      --red: #ff4d67;
      --red-bg: rgba(255, 77, 103, 0.14);
      --green: #16c784;
      --green-bg: rgba(22, 199, 132, 0.14);
      --gray: #64748b;
      --gray-bg: rgba(100, 116, 139, 0.16);
      --accent: #38bdf8;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      padding: 16px;
      background: radial-gradient(circle at top, #0f1b33 0%, var(--bg) 55%);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif;
      font-size: 13px;
      line-height: 1.45;
    }

    .container { max-width: 1520px; margin: 0 auto; }
    .topbar {
      display: flex; flex-wrap: wrap; justify-content: space-between;
      align-items: center; gap: 12px; margin-bottom: 12px;
    }
    .eyebrow {
      font-size: 11px; letter-spacing: 0.08em; color: var(--muted);
      display: flex; align-items: center; gap: 6px;
    }
    .dot-live {
      width: 7px; height: 7px; border-radius: 50%;
      background: var(--red); display: inline-block;
    }
    h1 { margin: 2px 0 0; font-size: 20px; font-weight: 700; }
    .controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
    .pill-box {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 10px; padding: 6px 12px; display: flex;
      align-items: center; gap: 8px; font-size: 12px;
    }
    select, button {
      background: var(--panel-2); color: var(--text);
      border: 1px solid var(--border); border-radius: 8px;
      padding: 6px 10px; font-size: 12px; cursor: pointer;
    }
    button:hover, select:hover { border-color: var(--accent); }
    button:disabled { opacity: .55; cursor: wait; }

    .legend {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 12px; padding: 10px 14px; display: flex;
      flex-wrap: wrap; justify-content: space-between; align-items: center;
      gap: 10px; margin-bottom: 14px; font-size: 12px; color: var(--muted);
    }
    .legend-items { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }
    .badge-dot {
      width: 9px; height: 9px; border-radius: 50%;
      display: inline-block; margin-right: 5px;
    }
    .grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 10px; margin-bottom: 16px;
    }
    .card {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 12px; padding: 12px; min-height: 96px;
      display: flex; flex-direction: column; justify-content: space-between;
    }
    .card-top {
      display: flex; justify-content: space-between; align-items: center;
      gap: 6px; margin-bottom: 6px;
    }
    .tag {
      font-size: 10px; color: var(--muted); background: var(--panel-2);
      padding: 2px 6px; border-radius: 6px; white-space: nowrap;
    }
    .signal-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
    .sig-red { background: var(--red); box-shadow: 0 0 8px rgba(255, 77, 103, 0.5); }
    .sig-green { background: var(--green); box-shadow: 0 0 8px rgba(22, 199, 132, 0.45); }
    .sig-gray { background: var(--gray); }
    .metric-name { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
    .metric-val { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
    .val-red { color: var(--red); }
    .val-green { color: var(--green); }
    .val-neutral { color: var(--text); }
    .metric-sub {
      font-size: 11px; color: var(--muted); margin-top: 4px;
      font-variant-numeric: tabular-nums;
    }
    .data-warning {
      margin: 0 0 12px; padding: 9px 12px; border-radius: 9px;
      border: 1px solid var(--border); background: var(--panel);
      color: var(--muted); font-size: 12px; overflow-wrap: anywhere;
    }
    .data-warning.error {
      border-color: rgba(255, 77, 103, .35);
      color: #ff9aaa; background: rgba(255, 77, 103, .07);
    }
    .data-warning:empty { display: none; }

    .table-panel {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 12px; padding: 12px 14px;
    }
    .table-header {
      display: flex; flex-wrap: wrap; justify-content: space-between;
      align-items: center; gap: 8px; margin-bottom: 10px;
    }
    .table-title { font-size: 14px; font-weight: 700; }
    .table-wrap { width: 100%; overflow-x: auto; }
    table {
      width: 100%; border-collapse: collapse; font-size: 12px; white-space: nowrap;
    }
    th, td {
      padding: 8px 8px; border-bottom: 1px solid var(--border);
      text-align: right; font-variant-numeric: tabular-nums;
    }
    th:first-child, td:first-child {
      text-align: left; position: sticky; left: 0;
      background: var(--panel); z-index: 1;
    }
    th:last-child, td:last-child { text-align: left; }
    th { color: var(--muted); font-weight: 600; background: var(--panel-2); }
    tr:hover td { background: rgba(56, 189, 248, 0.05); }
    .trend-pill {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 2px 8px; border-radius: 999px;
      background: var(--panel-2); font-weight: 600; font-size: 11px;
    }
    .op-badge {
      display: inline-block; padding: 2px 8px; border-radius: 6px;
      font-size: 11px; font-weight: 600;
    }
    .op-bull { background: var(--red-bg); color: var(--red); }
    .op-bear { background: var(--green-bg); color: var(--green); }
    .op-wait { background: var(--gray-bg); color: #cbd5e1; }
    .empty-state { text-align: center; padding: 22px; color: var(--muted); }

    @media (max-width: 640px) {
      body { padding: 10px; }
      h1 { font-size: 18px; }
      .pill-box { padding: 6px 8px; }
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="topbar">
      <div>
        <div class="eyebrow">
          <span class="dot-live"></span>
          TWSE / TAIFEX DAILY CHIP ANALYTICS
        </div>
        <h1>台股每日盤後籌碼戰情室</h1>
      </div>

      <div class="controls">
        <div class="pill-box">
          <span>歷史紀錄：</span>
          <select id="dateSelect">
            <option value="__LATEST__">最新盤後數據</option>
          </select>
        </div>
        <div class="pill-box">
          <span>更新時間：</span>
          <strong id="updateTime">讀取中...</strong>
        </div>
        <button id="refreshBtn" type="button" title="重新載入">↻</button>
      </div>
    </div>

    <div class="legend">
      <div class="legend-items">
        <span><i class="badge-dot" style="background:var(--red)"></i>紅燈（偏多訊號）</span>
        <span><i class="badge-dot" style="background:var(--green)"></i>綠燈（偏空訊號）</span>
        <span><i class="badge-dot" style="background:var(--gray)"></i>灰燈（中性參考）</span>
      </div>
      <div>依歷史紅綠燈比例統計隔日台指漲跌作為操作參考</div>
    </div>

    <div id="dataWarning" class="data-warning" role="status" aria-live="polite"></div>
    <div id="cardsGrid" class="grid"></div>

    <div class="table-panel">
      <div class="table-header">
        <div class="table-title">每日籌碼統計歷史總表</div>
        <div id="sampleSummary" class="metric-sub"></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>日期</th>
              <th>台指結算</th>
              <th>現貨量(億)</th>
              <th>融資餘額(億)</th>
              <th>美元台幣</th>
              <th>外資現貨</th>
              <th>投信現貨</th>
              <th>自營商</th>
              <th>外資期未平倉</th>
              <th>五大淨額</th>
              <th>十大淨額</th>
              <th>P/C比</th>
              <th>外資選(萬)</th>
              <th>小台散戶</th>
              <th>微台散戶</th>
              <th>台積ADR</th>
              <th>趨勢判定</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody id="historyBody">
            <tr>
              <td colspan="18" class="empty-state">正在載入歷史統計資料...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const METRIC_META = [
      { key: "台指結算", tag: "01·期貨指數", fmt: "int" },
      { key: "現貨量(億)", tag: "02·大盤量能", fmt: "f1" },
      { key: "融資餘額(億)", tag: "03·散戶信用", fmt: "f2" },
      { key: "美元兌台幣", tag: "04·匯率動向", fmt: "f3" },
      { key: "外資現貨(億)", tag: "05·三大法人", fmt: "f2" },
      { key: "投信現貨(億)", tag: "06·三大法人", fmt: "f2" },
      { key: "自營商現貨(億)", tag: "07·三大法人", fmt: "f2" },
      { key: "外資台指期未平倉", tag: "08·期貨籌碼", fmt: "int" },
      { key: "五大淨額(口)", tag: "09·大額交易人", fmt: "int" },
      { key: "十大淨額(口)", tag: "10·大額交易人", fmt: "int" },
      { key: "P/C未平倉比", tag: "11·選擇權指標", fmt: "pct" },
      { key: "外資選擇權未平倉淨額(萬)", tag: "12·選擇權指標", fmt: "int" },
      { key: "小台散戶多空比(%)", tag: "13·散戶指標", fmt: "f2" },
      { key: "微台散戶多空比(%)", tag: "14·散戶指標", fmt: "f2" },
      { key: "台積電美股ADR指數", tag: "15·美股連動", fmt: "f2" },
    ];

    function escapeHTML(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      })[char]);
    }

    function toNum(value) {
      if (value === null || value === undefined || value === "" || value === "--") return null;
      const n = parseFloat(String(value).replace(/,/g, "").replace(/[%％]/g, "").trim());
      return Number.isFinite(n) ? n : null;
    }

    function fmtVal(entry, mode) {
      if (!entry || entry.value === null || entry.value === undefined || entry.value === "" || entry.value === "--") {
        return "--";
      }
      if (mode === "pct") {
        const n = toNum(entry.value);
        return n === null ? "--" : `${n.toFixed(2)}%`;
      }
      const n = toNum(entry.value);
      if (n === null) return escapeHTML(entry.value);
      if (mode === "int") return Math.round(n).toLocaleString("en-US");
      if (mode === "f1") return n.toFixed(1);
      if (mode === "f2") return n.toFixed(2);
      if (mode === "f3") return n.toFixed(3);
      return escapeHTML(entry.value);
    }

    // 單一指標燈號判定：1 = 紅燈(偏多), -1 = 綠燈(偏空), 0 = 灰燈(中性)
    function getSignal(key, entry) {
      if (!entry) return 0;
      const value = toNum(entry.value);
      const prev = toNum(entry.prev);
      const change = toNum(entry.change);

      if (key === "台指結算") {
        if (value !== null && prev !== null) return value > prev ? 1 : (value < prev ? -1 : 0);
        return 0;
      }
      if (key === "融資餘額(億)") {
        if (value !== null && prev !== null) return value < prev ? 1 : (value > prev ? -1 : 0);
        return 0;
      }
      if (key === "美元兌台幣") {
        if (value !== null && prev !== null) return value < prev ? 1 : (value > prev ? -1 : 0);
        return 0;
      }
      if (["外資現貨(億)", "投信現貨(億)", "自營商現貨(億)", "外資台指期未平倉", "五大淨額(口)", "十大淨額(口)", "外資選擇權未平倉淨額(萬)"].includes(key)) {
        if (value === null || value === 0) return 0;
        return value > 0 ? 1 : -1;
      }
      if (key === "P/C未平倉比") {
        if (value === null) return 0;
        if (value >= 105) return 1;
        if (value <= 90) return -1;
        return 0;
      }
      if (["小台散戶多空比(%)", "微台散戶多空比(%)"].includes(key)) {
        // 散戶過度偏多視為反指標(綠燈)，散戶偏空視為反指標(紅燈)
        if (value === null) return 0;
        if (value <= -15) return 1;
        if (value >= 15) return -1;
        return 0;
      }
      if (key === "台積電美股ADR指數") {
        if (change !== null) return change > 0 ? 1 : (change < 0 ? -1 : 0);
        return 0;
      }
      return 0;
    }

    function calcRedGreen(record) {
      const data = (record && record.data) || {};
      let red = 0;
      let green = 0;
      for (const metric of METRIC_META) {
        const signal = getSignal(metric.key, data[metric.key]);
        if (signal === 1) red += 1;
        else if (signal === -1) green += 1;
      }
      const activeTotal = red + green;
      const redRatio = activeTotal > 0 ? red / activeTotal : 0.5;
      return { red, green, activeTotal, redRatio };
    }

    function buildOperationStats(records) {
      const sorted = [...records].sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
      const samples = [];

      for (let i = 0; i < sorted.length - 1; i++) {
        const currentClose = toNum(sorted[i]?.data?.["台指結算"]?.value);
        const nextClose = toNum(sorted[i + 1]?.data?.["台指結算"]?.value);
        if (currentClose !== null && currentClose > 0 && nextClose !== null && nextClose > 0) {
          const pctChange = ((nextClose - currentClose) / currentClose) * 100;
          const pointsChange = nextClose - currentClose;
          const signalStats = calcRedGreen(sorted[i]);
          samples.push({ redRatio: signalStats.redRatio, pctChange, pointsChange });
        }
      }

      return function evaluateOperation(record) {
        const signalStats = calcRedGreen(record);
        const matched = samples.filter((sample) => Math.abs(sample.redRatio - signalStats.redRatio) <= 0.15);

        if (matched.length > 0) {
          const avgPct = matched.reduce((sum, sample) => sum + sample.pctChange, 0) / matched.length;
          const avgPts = matched.reduce((sum, sample) => sum + sample.pointsChange, 0) / matched.length;
          const signPct = avgPct >= 0 ? "+" : "";
          const signPts = avgPts >= 0 ? "+" : "";
          let action = "觀望整理";
          let cls = "op-wait";
          if (avgPct >= 0.35) { action = "偏多操作"; cls = "op-bull"; }
          else if (avgPct <= -0.35) { action = "偏空防守"; cls = "op-bear"; }
          return {
            label: `${action}（估 ${signPct}${avgPct.toFixed(2)}% / ${signPts}${Math.round(avgPts)}點）`,
            cls,
            note: `相近燈號樣本 ${matched.length} 筆`
          };
        }

        const ratioPct = Math.round(signalStats.redRatio * 100);
        if (signalStats.red > signalStats.green + 1) {
          return { label: `紅燈佔 ${ratioPct}%・偏多參考`, cls: "op-bull", note: `累積 ${samples.length} 筆隔日樣本` };
        }
        if (signalStats.green > signalStats.red + 1) {
          return { label: `紅燈佔 ${ratioPct}%・偏空參考`, cls: "op-bear", note: `累積 ${samples.length} 筆隔日樣本` };
        }
        return { label: `紅燈佔 ${ratioPct}%・中性觀望`, cls: "op-wait", note: `累積 ${samples.length} 筆隔日樣本` };
      };
    }

    function renderCards(record) {
      const grid = document.getElementById("cardsGrid");
      const data = (record && record.data) || {};
      grid.innerHTML = METRIC_META.map((metric) => {
        const entry = data[metric.key] || { value: "--" };
        const signal = getSignal(metric.key, entry);
        const dotClass = signal === 1 ? "sig-red" : (signal === -1 ? "sig-green" : "sig-gray");
        const valueClass = signal === 1 ? "val-red" : (signal === -1 ? "val-green" : "val-neutral");
        const displayValue = fmtVal(entry, metric.fmt);

        let subText = "";
        const value = toNum(entry.value);
        const prev = toNum(entry.prev);
        const change = toNum(entry.change);
        if (metric.key === "台指結算" && value !== null && prev !== null) {
          const diff = Math.round(value - prev);
          subText = `較前日: ${diff >= 0 ? "+" : ""}${diff.toLocaleString("en-US")}`;
        } else if (metric.key === "融資餘額(億)" && value !== null && prev !== null) {
          const diff = value - prev;
          subText = `較前日: ${diff >= 0 ? "+" : ""}${diff.toFixed(2)}`;
        } else if (metric.key === "外資台指期未平倉" && value !== null && prev !== null) {
          const diff = Math.round(value - prev);
          subText = `較前日: ${diff >= 0 ? "+" : ""}${diff.toLocaleString("en-US")}`;
        } else if (metric.key === "台積電美股ADR指數" && change !== null) {
          subText = `漲跌: ${change >= 0 ? "+" : ""}${change.toFixed(2)}`;
        }

        return `
          <div class="card">
            <div class="card-top">
              <span class="tag">${escapeHTML(metric.tag)}</span>
              <span class="signal-dot ${dotClass}"></span>
            </div>
            <div>
              <div class="metric-name">${escapeHTML(metric.key)}</div>
              <div class="metric-val ${valueClass}">${displayValue}</div>
              ${subText ? `<div class="metric-sub">${escapeHTML(subText)}</div>` : ""}
            </div>
          </div>
        `;
      }).join("");
    }

    function renderHistoryTable(records) {
      const tbody = document.getElementById("historyBody");
      const summary = document.getElementById("sampleSummary");

      if (!records || records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="18" class="empty-state">目前尚無籌碼歷史資料</td></tr>`;
        summary.textContent = "";
        return;
      }

      const evaluateOperation = buildOperationStats(records);
      const descRecords = [...records].sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
      const ascRecords = [...records].sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
      let validPairs = 0;
      for (let i = 0; i < ascRecords.length - 1; i++) {
        const current = toNum(ascRecords[i]?.data?.["台指結算"]?.value);
        const next = toNum(ascRecords[i + 1]?.data?.["台指結算"]?.value);
        if (current !== null && current > 0 && next !== null && next > 0) validPairs += 1;
      }
      summary.textContent = `已累積 ${records.length} 個交易日｜可比對隔日漲跌樣本 ${validPairs} 筆`;

      const cell = (data, key, mode) => `<td>${fmtVal(data[key], mode)}</td>`;
      tbody.innerHTML = descRecords.map((record) => {
        const data = record.data || {};
        const signalStats = calcRedGreen(record);
        const operation = evaluateOperation(record);
        return `
          <tr>
            <td><strong>${escapeHTML(record.date || "--")}</strong></td>
            ${cell(data, "台指結算", "int")}
            ${cell(data, "現貨量(億)", "f1")}
            ${cell(data, "融資餘額(億)", "f2")}
            ${cell(data, "美元兌台幣", "f3")}
            ${cell(data, "外資現貨(億)", "f2")}
            ${cell(data, "投信現貨(億)", "f2")}
            ${cell(data, "自營商現貨(億)", "f2")}
            ${cell(data, "外資台指期未平倉", "int")}
            ${cell(data, "五大淨額(口)", "int")}
            ${cell(data, "十大淨額(口)", "int")}
            ${cell(data, "P/C未平倉比", "pct")}
            ${cell(data, "外資選擇權未平倉淨額(萬)", "int")}
            ${cell(data, "小台散戶多空比(%)", "f2")}
            ${cell(data, "微台散戶多空比(%)", "f2")}
            ${cell(data, "台積電美股ADR指數", "f2")}
            <td>
              <span class="trend-pill">
                <span style="color:var(--red)">紅 ${signalStats.red}</span>
                <span>/</span>
                <span style="color:var(--green)">綠 ${signalStats.green}</span>
              </span>
            </td>
            <td><span class="op-badge ${operation.cls}" title="${escapeHTML(operation.note)}">${escapeHTML(operation.label)}</span></td>
          </tr>
        `;
      }).join("");
    }

    // 後端新版 history.json 是日期為 key 的物件；這裡同時支援舊版陣列格式。
    function normalizeHistoryPayload(payload) {
      const records = [];
      if (Array.isArray(payload)) {
        for (const item of payload) {
          if (item && typeof item === "object" && item.data && item.date) records.push(item);
        }
      } else if (payload && typeof payload === "object") {
        for (const [dateKey, item] of Object.entries(payload)) {
          if (!item || typeof item !== "object" || !item.data) continue;
          records.push({
            ...item,
            date: item.date || dateKey,
            update_time: item.update_time || ""
          });
        }
      }
      const byDate = new Map();
      for (const record of records) byDate.set(String(record.date), record);
      return Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
    }

    let allRecords = [];

    let lastLoadWarning = "";

    function showSelectedWarnings(record, loadWarning = "") {
      const warningEl = document.getElementById("dataWarning");
      const errors = Array.isArray(record?.errors) ? record.errors : [];
      const messages = [];
      if (loadWarning) messages.push(loadWarning);
      if (errors.length) {
        messages.push(`此日期有 ${errors.length} 項資料抓取未成功：${errors.join("；")}`);
      }
      if (!record && !loadWarning) {
        messages.push("尚未取得任何歷史資料，請確認 data.json 與 history.json 已部署到網站根目錄。");
      }
      warningEl.textContent = messages.join("\n");
      warningEl.classList.toggle("error", messages.length > 0);
    }

    function applySelectedView(loadWarning = lastLoadWarning) {
      const select = document.getElementById("dateSelect");
      const selected = select.value;
      const sortedDesc = [...allRecords].sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
      const target = selected === "__LATEST__"
        ? sortedDesc[0]
        : (sortedDesc.find((record) => record.date === selected) || sortedDesc[0]);

      document.getElementById("updateTime").textContent = (target && target.update_time) || "無資料";
      renderCards(target);
      renderHistoryTable(allRecords);
      showSelectedWarnings(target, loadWarning);
    }

    async function fetchJSON(path, timestamp) {
      const response = await fetch(`${path}?t=${timestamp}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`${path} 讀取失敗（HTTP ${response.status}）`);
      return response.json();
    }

    async function loadAllData() {
      const refreshButton = document.getElementById("refreshBtn");
      const previousLabel = refreshButton.textContent;
      refreshButton.disabled = true;
      refreshButton.textContent = "…";
      const timestamp = Date.now();
      let historyRecords = [];
      let latestRecord = null;
      const loadErrors = [];

      try {
        const historyPayload = await fetchJSON("./history.json", timestamp);
        historyRecords = normalizeHistoryPayload(historyPayload);
      } catch (error) {
        loadErrors.push(error.message || "歷史資料讀取失敗");
      }

      try {
        const latestPayload = await fetchJSON("./data.json", timestamp);
        if (latestPayload && latestPayload.data && typeof latestPayload.data === "object") {
          const inferredDate = latestPayload.date || String(latestPayload.update_time || "").slice(0, 10);
          latestRecord = {
            ...latestPayload,
            date: inferredDate || "最新",
            update_time: latestPayload.update_time || "",
            data: latestPayload.data
          };
        } else {
          loadErrors.push("data.json 格式不符合預期，找不到 data 欄位");
        }
      } catch (error) {
        loadErrors.push(error.message || "最新資料讀取失敗");
      }

      const recordMap = new Map();
      for (const record of historyRecords) recordMap.set(String(record.date), record);
      if (latestRecord && latestRecord.date) recordMap.set(String(latestRecord.date), latestRecord);
      allRecords = Array.from(recordMap.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));

      const select = document.getElementById("dateSelect");
      const previousSelection = select.value;
      const descendingDates = [...allRecords]
        .map((record) => String(record.date || ""))
        .filter(Boolean)
        .sort((a, b) => b.localeCompare(a));

      select.innerHTML = `<option value="__LATEST__">最新盤後數據</option>` +
        descendingDates.map((date) => `<option value="${escapeHTML(date)}">${escapeHTML(date)}</option>`).join("");

      if (previousSelection === "__LATEST__" || descendingDates.includes(previousSelection)) {
        select.value = previousSelection || "__LATEST__";
      } else {
        select.value = "__LATEST__";
      }

      lastLoadWarning = loadErrors.length ? `資料載入提醒：${loadErrors.join("；")}` : "";
      applySelectedView(lastLoadWarning);
      refreshButton.disabled = false;
      refreshButton.textContent = previousLabel;
    }

    document.getElementById("dateSelect").addEventListener("change", () => applySelectedView(lastLoadWarning));
    document.getElementById("refreshBtn").addEventListener("click", loadAllData);
    loadAllData();
  </script>
</body>
</html>
