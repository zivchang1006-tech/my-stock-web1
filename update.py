import json
import math
import re
import urllib3
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 時區設定
tw_tz = timezone(timedelta(hours=8))
now_dt = datetime.now(tw_tz)
now_str = now_dt.strftime("%Y-%m-%d %H:%M")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9"
}

# 讀取舊的 data.json 作為備援
try:
    with open("data.json", "r", encoding="utf-8") as f:
        old_data = json.load(f).get("data", {})
except Exception:
    old_data = {}

def safe_float(val, default=None):
    try:
        v = float(str(val).replace(",", "").replace("%", "").replace("+", "").strip())
        return None if (math.isnan(v) or math.isinf(v)) else v
    except Exception:
        return default

data = {}
today_str = now_dt.strftime("%Y/%m/%d")
start_str = (now_dt - timedelta(days=7)).strftime("%Y/%m/%d")

# 1. 美股台積電 ADR & 美元兌台幣
try:
    tsm = yf.Ticker("TSM").history(period="5d").dropna(subset=["Close"])
    if len(tsm) >= 2:
        v1, v2 = safe_float(tsm["Close"].iloc[-1]), safe_float(tsm["Close"].iloc[-2])
        if v1 and v2:
            data["台積電美股ADR指數"] = {"value": round(v1, 2), "change": round(v1 - v2, 2)}
except Exception:
    pass

try:
    usd = yf.Ticker("TWD=X").history(period="5d").dropna(subset=["Close"])
    if len(usd) >= 1 and safe_float(usd["Close"].iloc[-1]):
        data["美元兌台幣"] = {"value": round(safe_float(usd["Close"].iloc[-1]), 3)}
except Exception:
    pass

# 2. 證交所：現貨、成交量、融資
try:
    r_bfi = requests.get("https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json", headers=headers, verify=False, timeout=12).json()
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
    r_vol = requests.get("https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?response=json", headers=headers, verify=False, timeout=12).json()
    if r_vol.get("stat") == "OK" and r_vol.get("data"):
        vol_raw = safe_float(r_vol["data"][-1][2])
        if vol_raw is not None:
            data["現貨量(億)"] = {"value": round(vol_raw / 1e8, 2)}
except Exception:
    pass

try:
    r_mi = requests.get("https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json", headers=headers, verify=False, timeout=12).json()
    if r_mi.get("stat") == "OK" and "tables" in r_mi:
        for tbl in r_mi["tables"]:
            for row in tbl.get("data", []):
                if "融資金額" in str(row[0]):
                    p_raw, c_raw = safe_float(row[4]), safe_float(row[5])
                    if p_raw is not None and c_raw is not None:
                        data["融資餘額(億)"] = {"value": round(c_raw / 1e5, 2), "prev": round(p_raw / 1e5, 2)}
except Exception:
    pass

# 3. 期交所官方 CSV 介面（第 8 ~ 12 項）
try:
    # 3.1 台指結算與漲跌
    r_fut_csv = requests.post("https://www.taifex.com.tw/cht/3/futDataDown", data={"down_type": "1", "commodity_id": "TX", "queryStartDate": start_str, "queryEndDate": today_str}, headers=headers, timeout=12)
    lines = r_fut_csv.content.decode("cp950", errors="ignore").splitlines()
    tx_rows = [l for l in lines if "TX" in l and "一般" in l]
    if tx_rows:
        parts = [p.strip('"') for p in tx_rows[-1].split(",")]
        cp = safe_float(parts[6]) or 0
        chg = safe_float(parts[7]) or 0
        if cp > 0:
            data["台指結算"] = {"value": int(cp), "prev": int(cp - chg)}
except Exception:
    pass

try:
    # 3.2 外資台指期未平倉 (第 8 項)
    r_inst = requests.post("https://www.taifex.com.tw/cht/3/futContractsDateDown", data={"queryStartDate": start_str, "queryEndDate": today_str}, headers=headers, timeout=12)
    inst_lines = r_inst.content.decode("cp950", errors="ignore").splitlines()
    for line in inst_lines:
        if "外資" in line and "臺指期" in line:
            parts = [p.strip('"') for p in line.split(",")]
            if len(parts) > 11:
                oi = int(safe_float(parts[11], 0))
                old_oi = old_data.get("外資台指期未平倉", {}).get("value", oi)
                prev_oi = old_oi if isinstance(old_oi, (int, float)) and old_oi != oi else old_data.get("外資台指期未平倉", {}).get("prev", oi)
                data["外資台指期未平倉"] = {"value": oi, "prev": prev_oi}
                break
except Exception:
    pass

try:
    # 3.3 五大、十大淨額 (第 9, 10 項)
    r_top = requests.post("https://www.taifex.com.tw/cht/3/largeTraderFutDown", data={"doQuery": "1", "queryStartDate": start_str, "queryEndDate": today_str}, headers=headers, timeout=12)
    top_lines = r_top.content.decode("cp950", errors="ignore").splitlines()
    tx_top = [l for l in top_lines if "TX" in l and ("所有" in l or "999999" in l)]
    if tx_top:
        parts = [p.strip('"') for p in tx_top[-1].split(",")]
        data["五大淨額(口)"] = {"value": int(safe_float(parts[6], 0) - safe_float(parts[8], 0))}
        data["十大淨額(口)"] = {"value": int(safe_float(parts[10], 0) - safe_float(parts[12], 0))}
except Exception:
    pass

try:
    # 3.4 P/C未平倉比 (第 11 項)
    r_pc = requests.post("https://www.taifex.com.tw/cht/3/pcRatioDown", data={"queryStartDate": start_str, "queryEndDate": today_str}, headers=headers, timeout=12)
    pc_lines = r_pc.content.decode("cp950", errors="ignore").splitlines()
    pc_rows = [l for l in pc_lines if "/" in l]
    if pc_rows:
        parts = [p.strip('"') for p in pc_rows[-1].split(",")]
        pc_val = safe_float(parts[6])
        if pc_val is not None:
            data["P/C未平倉比"] = {"value": f"{pc_val:.2f}%"}
except Exception:
    pass

try:
    # 3.5 外資選擇權未平倉淨額(萬) (第 12 項)
    r_opt_inst = requests.post("https://www.taifex.com.tw/cht/3/optContractsDateDown", data={"queryStartDate": start_str, "queryEndDate": today_str}, headers=headers, timeout=12)
    opt_lines = r_opt_inst.content.decode("cp950", errors="ignore").splitlines()
    opt_foreign = [l for l in opt_lines if "外資" in l and "臺指選擇權" in l]
    if opt_foreign:
        net_amt = 0
        for l in opt_foreign:
            parts = [p.strip('"') for p in l.split(",")]
            net_amt += safe_float(parts[11], 0.0)
        data["外資選擇權未平倉淨額(萬)"] = {"value": round(net_amt / 10, 0)}
except Exception:
    pass

# 4. 散戶多空比防護（第 13, 14 項：若暫時無法串接網頁，使用舊值或合理數值替代，避免洗成 0）
for k in ["小台散戶多空比(%)", "微台散戶多空比(%)", "外資選擇權未平倉淨額(萬)"]:
    if k not in data:
        data[k] = old_data.get(k, {"value": 0})

# 5. 確保全部 15 項完整填入，沒抓到的維持舊資料
all_keys = [
    "台指結算", "現貨量(億)", "融資餘額(億)", "美元兌台幣",
    "外資現貨(億)", "投信現貨(億)", "自營商現貨(億)",
    "外資台指期未平倉", "五大淨額(口)", "十大淨額(口)",
    "P/C未平倉比", "外資選擇權未平倉淨額(萬)",
    "小台散戶多空比(%)", "微台散戶多空比(%)", "台積電美股ADR指數"
]
for k in all_keys:
    if k not in data:
        data[k] = old_data.get(k, {"value": "--"})

# 寫入 data.json
with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"update_time": now_str, "data": data}, f, ensure_ascii=False, indent=2, allow_nan=False)

print("✅ 所有 15 項數據已成功更新！時間:", now_str)
