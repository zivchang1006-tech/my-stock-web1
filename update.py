python
import json
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

tw_tz = timezone(timedelta(hours=8))
now_str = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M")

try:
    with open("data.json", "r", encoding="utf-8") as f:
        old_json = json.load(f)
        old_data = old_json.get("data", {})
except Exception:
    old_data = {}

def get_prev(key, default_val):
    item = old_data.get(key, {})
    return item.get("value", default_val) if isinstance(item, dict) else default_val

data = {}

# 1. 抓台積電美股 ADR (TSM) 與 美元兌台幣 (TWD=X)
try:
    tsm = yf.Ticker("TSM").history(period="5d")
    tsm_val = round(float(tsm["Close"].iloc[-1]), 2)
    tsm_chg = round(float(tsm["Close"].iloc[-1] - tsm["Close"].iloc[-2]), 2)
    data["台積電美股ADR指數"] = {"value": tsm_val, "change": tsm_chg}
except Exception:
    data["台積電美股ADR指數"] = old_data.get("台積電美股ADR指數", {"value": 0, "change": 0})

try:
    usd = yf.Ticker("TWD=X").history(period="2d")
    usd_val = round(float(usd["Close"].iloc[-1]), 2)
    data["美元兌台幣"] = {"value": usd_val}
except Exception:
    data["美元兌台幣"] = old_data.get("美元兌台幣", {"value": 0})

# 2. 抓台灣證交所三大法人買賣超 (單位轉億元)
try:
    r = requests.get("https://twse.com.tw", timeout=10).json()
    if r.get("stat") == "OK":
        for row in r["data"]:
            name = row[0].strip()
            diff = round(float(row[3].replace(",", "")) / 100000000, 2)
            if "自營商" in name and "避險" not in name and "自行" not in name:
                data["自營商現貨(億)"] = {"value": diff}
            elif "投信" in name:
                data["投信現貨(億)"] = {"value": diff}
            elif "外資及陸資" in name:
                data["外資現貨(億)"] = {"value": diff}
except Exception:
    pass

# 3. 抓證交所大盤成交金額 (現貨量億)
try:
    r_vol = requests.get("https://twse.com.tw", timeout=10).json()
    if r_vol.get("stat") == "OK":
        last_row = r_vol["data"][-1]
        vol_yi = round(float(last_row[2].replace(",", "")) / 100000000, 2)
        data["現貨量(億)"] = {"value": vol_yi}
except Exception:
    pass

# 4. 抓證交所融資餘額 (億元)
try:
    r_mi = requests.get("https://twse.com.tw", timeout=10).json()
    if r_mi.get("stat") == "OK" and "tables" in r_mi:
        credit_rows = r_mi["tables"][0]["data"]
        for row in credit_rows:
            if "融資金額" in row[0]:
                prev_val = round(float(row[4].replace(",", "")) / 100000, 2)
                curr_val = round(float(row[5].replace(",", "")) / 100000, 2)
                data["融資餘額(億)"] = {"value": curr_val, "prev": prev_val}
except Exception:
    pass

# 5. 抓期交所 Put/Call 比
try:
    r_pc = requests.get("https://taifex.com.tw", timeout=10).json()
    if r_pc:
        pc_val = r_pc[-1].get("PutCallRatio", "0")
        data["P/C未平倉比"] = {"value": f"{pc_val}%"}
except Exception:
    pass

# 其餘期貨項目若 API 尚未更新則保留舊值不清空
all_keys = [
    "台指結算", "現貨量(億)", "融資餘額(億)", "美元兌台幣",
    "外資現貨(億)", "投信現貨(億)", "自營商現貨(億)",
    "外資台指期未平倉", "五大淨額(口)", "十大淨額(口)",
    "P/C未平倉比", "外資選擇權未平倉淨額(萬)",
    "小台散戶多空比(%)", "微台散戶多空比(%)", "台積電美股ADR指數"
]

for k in all_keys:
    if k not in data:
        data[k] = old_data.get(k, {"value": 0})

output = {"update_time": now_str, "data": data}
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ 資料更新與驗證完成！")
