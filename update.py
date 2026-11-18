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

# 1. 台積電美股 ADR & 美元兌台幣
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

# 2. 證交所現貨、成交量與融資
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

# 3. 期交所官方籌碼（外資期貨未平倉、五大十大、P/C比）
try:
    today_str = now_dt.strftime("%Y/%m/%d")
    start_str = (now_dt - timedelta(days=5)).strftime("%Y/%m/%d")

    # 外資台指期未平倉
    r_inst = requests.post("https://www.taifex.com.tw/cht/3/futContractsDateDown", data={"queryStartDate": start_str, "queryEndDate": today_str}, headers=headers, timeout=12)
    lines = r_inst.content.decode("cp950", errors="ignore").splitlines()
    for line in lines:
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

# 維持或防護其他未抓到的項目
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

print("✅ 數據更新完成！時間:", now_str)
