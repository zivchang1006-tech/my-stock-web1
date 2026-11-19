import json
import math
import urllib3
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

tw_tz = timezone(timedelta(hours=8))
now_dt = datetime.now(tw_tz)
today_date_str = now_dt.strftime("%Y-%m-%d")
now_str = now_dt.strftime("%Y-%m-%d %H:%M")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9",
}

# 內建 2026-11-17 與 2026-11-18 歷史基準資料，方便建立跨日紀錄與隔日漲跌統計
SEED_HISTORY = [
    {
        "date": "2026-11-17",
        "update_time": "2026-11-17 16:30",
        "data": {
            "台指結算": {"value": 40011, "prev": 39890},
            "現貨量(億)": {"value": 10240.5},
            "融資餘額(億)": {"value": 5244.98, "prev": 5260.10},
            "美元兌台幣": {"value": 32.915},
            "外資現貨(億)": {"value": -412.30},
            "投信現貨(億)": {"value": 98.45},
            "自營商現貨(億)": {"value": -32.10},
            "外資台指期未平倉": {"value": -38000, "prev": -39500},
            "五大淨額(口)": {"value": -24120},
            "十大淨額(口)": {"value": -9850},
            "P/C未平倉比": {"value": "55.12%"},
            "外資選擇權未平倉淨額(萬)": {"value": 13800},
            "小台散戶多空比(%)": {"value": 0},
            "微台散戶多空比(%)": {"value": 0},
            "台積電美股ADR指數": {"value": 373.45, "change": 4.12},
        },
    },
    {
        "date": "2026-11-18",
        "update_time": "2026-11-18 15:43",
        "data": {
            "台指結算": {"value": 40025, "prev": 40011},
            "現貨量(億)": {"value": 10576.3},
            "融資餘額(億)": {"value": 5087.21, "prev": 5244.98},
            "美元兌台幣": {"value": 32.946},
            "外資現貨(億)": {"value": -765.64},
            "投信現貨(億)": {"value": 175.58},
            "自營商現貨(億)": {"value": 54.72},
            "外資台指期未平倉": {"value": -35400, "prev": -38000},
            "五大淨額(口)": {"value": -28959},
            "十大淨額(口)": {"value": -11200},
            "P/C未平倉比": {"value": "53.79%"},
            "外資選擇權未平倉淨額(萬)": {"value": 15200},
            "小台散戶多空比(%)": {"value": 0},
            "微台散戶多空比(%)": {"value": 0},
            "台積電美股ADR指數": {"value": 359.69, "change": -13.76},
        },
    },
]

def load_json_safe(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

old_latest = load_json_safe("data.json", {})
old_data = old_latest.get("data", {}) if isinstance(old_latest, dict) else {}
history_list = load_json_safe("history.json", [])
if not isinstance(history_list, list):
    history_list = []

def safe_float(val, default=None):
    try:
        if val is None:
            return default
        s = str(val).replace(",", "").replace("%", "").replace("+", "").strip()
        if s == "" or s.lower() in ("null", "none", "--", "-"):
            return default
        v = float(s)
        return default if (math.isnan(v) or math.isinf(v)) else v
    except Exception:
        return default

data = {}
q_end = now_dt.strftime("%Y/%m/%d")
q_start = (now_dt - timedelta(days=7)).strftime("%Y/%m/%d")

# 1. 台積電 ADR & 美元兌台幣
try:
    tsm = yf.Ticker("TSM").history(period="5d").dropna(subset=["Close"])
    if len(tsm) >= 2:
        v1 = safe_float(tsm["Close"].iloc[-1])
        v2 = safe_float(tsm["Close"].iloc[-2])
        if v1 is not None and v2 is not None:
            data["台積電美股ADR指數"] = {"value": round(v1, 2), "change": round(v1 - v2, 2)}
except Exception:
    pass

try:
    usd = yf.Ticker("TWD=X").history(period="5d").dropna(subset=["Close"])
    if len(usd) >= 1:
        u1 = safe_float(usd["Close"].iloc[-1])
        if u1 is not None:
            data["美元兌台幣"] = {"value": round(u1, 3)}
except Exception:
    pass

# 2. 證交所：三大法人現貨、成交量、融資餘額
try:
    r_bfi = requests.get(
        "https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json",
        headers=headers, verify=False, timeout=12
    ).json()
    if r_bfi.get("stat") == "OK":
        for row in r_bfi.get("data", []):
            name = str(row[0]).strip()
            diff_raw = safe_float(row[3])
            if diff_raw is not None:
                diff = round(diff_raw / 1e8, 2)
                if name == "自營商(自行買賣)":
                    data["自營商現貨(億)"] = {"value": diff}
                elif "投信" in name:
                    data["投信現貨(億)"] = {"value": diff}
                elif "外資及陸資" in name:
                    data["外資現貨(億)"] = {"value": diff}
except Exception:
    pass

try:
    r_vol = requests.get(
        "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?response=json",
        headers=headers, verify=False, timeout=12
    ).json()
    if r_vol.get("stat") == "OK" and r_vol.get("data"):
        vol_raw = safe_float(r_vol["data"][-1][2])
        if vol_raw is not None:
            data["現貨量(億)"] = {"value": round(vol_raw / 1e8, 2)}
except Exception:
    pass

try:
    r_mi = requests.get(
        "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json",
        headers=headers, verify=False, timeout=12
    ).json()
    if r_mi.get("stat") == "OK" and "tables" in r_mi:
        for tbl in r_mi["tables"]:
            for row in tbl.get("data", []):
                if "融資金額" in str(row[0]):
                    p_raw = safe_float(row[4])
                    c_raw = safe_float(row[5])
                    if p_raw is not None and c_raw is not None:
                        data["融資餘額(億)"] = {
                            "value": round(c_raw / 1e5, 2),
                            "prev": round(p_raw / 1e5, 2),
                        }
except Exception:
    pass

# 3. 期交所：台指結算、外資期貨未平倉、五大十大、P/C比、外資選擇權未平倉
try:
    r_fut = requests.post(
        "https://www.taifex.com.tw/cht/3/futDataDown",
        data={"down_type": "1", "commodity_id": "TX", "queryStartDate": q_start, "queryEndDate": q_end},
        headers=headers, verify=False, timeout=12,
    )
    lines = r_fut.content.decode("cp950", errors="ignore").splitlines()
    tx_rows = [l for l in lines if ",TX," in l and "一般" in l]
    if tx_rows:
        parts = [p.strip('"').strip() for p in tx_rows[-1].split(",")]
        if len(parts) >= 8:
            cp = safe_float(parts[6])
            chg = safe_float(parts[7], 0.0)
            if cp is not None and cp > 0:
                data["台指結算"] = {"value": int(round(cp)), "prev": int(round(cp - chg))}
except Exception:
    pass

try:
    r_inst = requests.post(
        "https://www.taifex.com.tw/cht/3/futContractsDateDown",
        data={"queryStartDate": q_start, "queryEndDate": q_end},
        headers=headers, verify=False, timeout=12,
    )
    inst_lines = r_inst.content.decode("cp950", errors="ignore").splitlines()
    for line in reversed(inst_lines):
        if "外資" in line and "臺指期" in line:
            parts = [p.strip('"').strip() for p in line.split(",")]
            if len(parts) > 11:
                oi_val = safe_float(parts[11])
                if oi_val is not None:
                    oi = int(round(oi_val))
                    old_oi = safe_float(old_data.get("外資台指期未平倉", {}).get("value"))
                    prev_oi = int(round(old_oi)) if (old_oi is not None and int(round(old_oi)) != oi) else int(round(safe_float(old_data.get("外資台指期未平倉", {}).get("prev"), oi)))
                    data["外資台指期未平倉"] = {"value": oi, "prev": prev_oi}
                    break
except Exception:
    pass

try:
    r_top = requests.post(
        "https://www.taifex.com.tw/cht/3/largeTraderFutDown",
        data={"doQuery": "1", "queryStartDate": q_start, "queryEndDate": q_end},
        headers=headers, verify=False, timeout=12,
    )
    top_lines = r_top.content.decode("cp950", errors="ignore").splitlines()
    tx_top = [l for l in top_lines if ",TX," in l and ("所有" in l or "999999" in l)]
    if tx_top:
        parts = [p.strip('"').strip() for p in tx_top[-1].split(",")]
        if len(parts) >= 9:
            b5, s5 = safe_float(parts[6]), safe_float(parts[8])
            if None not in (b5, s5):
                data["五大淨額(口)"] = {"value": int(round(b5 - s5))}
        if len(parts) >= 13:
            b10, s10 = safe_float(parts[10]), safe_float(parts[12])
            if None not in (b10, s10):
                data["十大淨額(口)"] = {"value": int(round(b10 - s10))}
except Exception:
    pass

try:
    r_pc = requests.post(
        "https://www.taifex.com.tw/cht/3/pcRatioDown",
        data={"queryStartDate": q_start, "queryEndDate": q_end},
        headers=headers, verify=False, timeout=12,
    )
    pc_lines = r_pc.content.decode("cp950", errors="ignore").splitlines()
    pc_rows = [l for l in pc_lines if "/" in l]
    if pc_rows:
        parts = [p.strip('"').strip() for p in pc_rows[-1].split(",")]
        if len(parts) > 6:
            pc_val = safe_float(parts[6])
            if pc_val is not None:
                data["P/C未平倉比"] = {"value": f"{pc_val:.2f}%"}
except Exception:
    pass

try:
    r_opt = requests.post(
        "https://www.taifex.com.tw/cht/3/optContractsDateDown",
        data={"queryStartDate": q_start, "queryEndDate": q_end},
        headers=headers, verify=False, timeout=12,
    )
    opt_lines = r_opt.content.decode("cp950", errors="ignore").splitlines()
    opt_foreign = [l for l in opt_lines if "外資" in l and "臺指選擇權" in l]
    if opt_foreign:
        net_amt = 0.0
        has_val = False
        for l in opt_foreign:
            parts = [p.strip('"').strip() for p in l.split(",")]
            if len(parts) > 11:
                v = safe_float(parts[11])
                if v is not None:
                    net_amt += v
                    has_val = True
        if has_val:
            data["外資選擇權未平倉淨額(萬)"] = {"value": int(round(net_amt / 10))}
except Exception:
    pass

# 4. 確保 15 項指標完整，缺漏或無效時保留舊資料
all_keys = [
    "台指結算", "現貨量(億)", "融資餘額(億)", "美元兌台幣",
    "外資現貨(億)", "投信現貨(億)", "自營商現貨(億)",
    "外資台指期未平倉", "五大淨額(口)", "十大淨額(口)",
    "P/C未平倉比", "外資選擇權未平倉淨額(萬)",
    "小台散戶多空比(%)", "微台散戶多空比(%)", "台積電美股ADR指數",
]

for k in all_keys:
    cur_val = data.get(k, {}).get("value") if isinstance(data.get(k), dict) else None
    if cur_val is None or str(cur_val).strip() in ("", "null", "None", "--"):
        prev_entry = old_data.get(k)
        if isinstance(prev_entry, dict) and prev_entry.get("value") is not None and str(prev_entry.get("value")).strip() not in ("", "null", "None", "--"):
            data[k] = prev_entry
        else:
            data[k] = {"value": 0 if ("比" in k or "淨額" in k or "未平倉" in k) else "--"}

# 5. 更新最新 data.json 與每日歷史 history.json（含 2026-11-17、2026-11-18 紀錄）
latest_payload = {
    "date": today_date_str,
    "update_time": now_str,
    "data": data,
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(latest_payload, f, ensure_ascii=False, indent=2, allow_nan=False)

history_map = {}
for seed in SEED_HISTORY:
    history_map[seed["date"]] = seed

for item in history_list:
    if isinstance(item, dict) and item.get("date"):
        history_map[item["date"]] = item

history_map[today_date_str] = latest_payload
merged_history = [history_map[d] for d in sorted(history_map.keys())]

with open("history.json", "w", encoding="utf-8") as f:
    json.dump(merged_history, f, ensure_ascii=False, indent=2, allow_nan=False)

print(f"✅ 更新完成！時間：{now_str}，歷史天數：{len(merged_history)} 天")
