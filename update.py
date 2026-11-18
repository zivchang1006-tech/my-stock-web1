import json
import math
import re
import urllib3
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

tw_tz = timezone(timedelta(hours=8))
now_dt = datetime.now(tw_tz)
now_str = now_dt.strftime("%Y-%m-%d %H:%M")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9"
}

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

# 1. 美股台積電 ADR & 美元兌台幣 (Yahoo Finance)
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

# 2. 證交所三大法人與融資官方 API
try:
    r_bfi = requests.get("https://openapi.twse.com.tw/v1/fund/T86", headers=headers, verify=False, timeout=12).json()
    for row in r_bfi:
        name = str(row.get("Name", "")).strip()
        diff_raw = safe_float(row.get("Difference"))
        if diff_raw is not None:
            diff = round(diff_raw / 1e8, 2)
            if "自營商" in name and "買賣超" in name:
                data["自營商現貨(億)"] = {"value": diff}
            elif "投信" in name:
                data["投信現貨(億)"] = {"value": diff}
            elif "外資及陸資" in name:
                data["外資現貨(億)"] = {"value": diff}
except Exception:
    pass

# 3. 期交所官方 OpenAPI 取得 P/C 比與期權未平倉
try:
    r_pc = requests.get("https://openapi.taifex.com.tw/v1/PutCallRatio", headers=headers, verify=False, timeout=12).json()
    if r_pc and len(r_pc) > 0:
        latest_pc = r_pc[-1]
        pc_val = safe_float(latest_pc.get("PutCallRatio"))
        if pc_val is not None:
            data["P/C未平倉比"] = {"value": f"{pc_val:.2f}%"}
except Exception:
    pass

try:
    r_fut_oi = requests.get("https://openapi.taifex.com.tw/v1/FuturesInstitutionalInvestors", headers=headers, verify=False, timeout=12).json()
    # 篩選外資臺指期未平倉
    for row in r_fut_oi:
        if row.get("ContractCode") in ["TX", "臺指期"] and "外資" in str(row.get("Identity", "")):
            oi_net = int(safe_float(row.get("OpenInterestNetVolume"), 0))
            old_oi = old_data.get("外資台指期未平倉", {}).get("value", oi_net)
            prev_oi = old_oi if isinstance(old_oi, (int, float)) and old_oi != oi_net else old_data.get("外資台指期未平倉", {}).get("prev", oi_net)
            data["外資台指期未平倉"] = {"value": oi_net, "prev": prev_oi}
            break
except Exception:
    pass

# 補齊所有預設值，避免欄位遺失
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

with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"update_time": now_str, "data": data}, f, ensure_ascii=False, indent=2, allow_nan=False)

print("✅ 官方 OpenAPI 資料更新完成！時間:", now_str)
