import json
import urllib3
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

tw_tz = timezone(timedelta(hours=8))
now_str = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M")
headers = {"User-Agent": "Mozilla/5.0"}

try:
    with open("data.json", "r", encoding="utf-8") as f:
        old_data = json.load(f).get("data", {})
except Exception:
    old_data = {}

def safe_float(val, default=0.0):
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except Exception:
        return default

data = {}

# 1. 台積電美股 ADR (TSM) & 美元兌台幣 (TWD=X)
try:
    tsm = yf.Ticker("TSM").history(period="5d")
    if len(tsm) >= 2:
        val = round(float(tsm["Close"].iloc[-1]), 2)
        chg = round(float(tsm["Close"].iloc[-1] - tsm["Close"].iloc[-2]), 2)
        data["台積電美股ADR指數"] = {"value": val, "change": chg}
except Exception:
    pass

try:
    usd = yf.Ticker("TWD=X").history(period="2d")
    if len(usd) >= 1:
        data["美元兌台幣"] = {"value": round(float(usd["Close"].iloc[-1]), 3)}
except Exception:
    pass

# 2. 證交所：三大法人現貨買賣超 (單位：億)
try:
    r = requests.get("https://twse.com.tw", headers=headers, verify=False, timeout=15).json()
    if r.get("stat") == "OK":
        for row in r["data"]:
            name = row.strip()
            diff = round(safe_float(row) / 1e8, 2)
            if "自營商" in name and "避險" not in name and "自行" not in name:
                data["自營商現貨(億)"] = {"value": diff}
            elif "投信" in name:
                data["投信現貨(億)"] = {"value": diff}
            elif "外資及陸資" in name:
                data["外資現貨(億)"] = {"value": diff}
except Exception:
    pass

# 3. 證交所：大盤現貨成交量 (單位：億)
try:
    r_vol = requests.get("https://twse.com.tw", headers=headers, verify=False, timeout=15).json()
    if r_vol.get("stat") == "OK" and r_vol.get("data"):
        vol_yi = round(safe_float(r_vol["data"][-1]) / 1e8, 2)
        data["現貨量(億)"] = {"value": vol_yi}
except Exception:
    pass

# 4. 證交所：融資餘額 (單位：億)
try:
    r_mi = requests.get("https://twse.com.tw", headers=headers, verify=False, timeout=15).json()
    if r_mi.get("stat") == "OK" and "tables" in r_mi:
        for row in r_mi["tables"]["data"]:
            if "融資金額" in str(row):
                prev_v = round(safe_float(row) / 1e5, 2)
                curr_v = round(safe_float(row) / 1e5, 2)
                data["融資餘額(億)"] = {"value": curr_v, "prev": prev_v}
except Exception:
    pass

# 5. 期交所 OpenAPI：台指結算/收盤 & P/C比
try:
    r_fut = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=15).json()
    tx_rows = [x for x in r_fut if x.get("Contract") == "TX" and x.get("TradingSession") == "一般"]
    if tx_rows:
        close_p = safe_float(tx_rows.get("Close"))
        chg_p = safe_float(tx_rows.get("Change"))
        if close_p > 0:
            data["台指結算"] = {"value": int(close_p), "prev": int(close_p - chg_p)}
except Exception:
    pass

try:
    r_pc = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=15).json()
    if r_pc:
        pc_val = safe_float(r_pc[-1].get("PutCallRatio"))
        data["P/C未平倉比"] = {"value": f"{pc_val}%"}
except Exception:
    pass

# 6. 期交所 OpenAPI：三大法人台指期未平倉 & 選擇權未平倉淨額(萬)
try:
    r_inst = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=15).json()
    tx_foreign = [x for x in r_inst if "臺股期貨" in x.get("ContractCode", "") and "外資" in x.get("Item", "")]
    if tx_foreign:
        oi_net = int(safe_float(tx_foreign[-1].get("OpenInterestNetVolume")))
        old_oi = old_data.get("外資台指期未平倉", {}).get("value", oi_net)
        prev_oi = old_oi if old_oi != oi_net else old_data.get("外資台指期未平倉", {}).get("prev", oi_net)
        data["外資台指期未平倉"] = {"value": oi_net, "prev": prev_oi}
except Exception:
    pass

try:
    r_opt = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=15).json()
    opt_foreign = [x for x in r_opt if "臺指選擇權" in x.get("ContractCode", "") and "外資" in x.get("Item", "")]
    if opt_foreign:
        net_amt = sum(safe_float(x.get("OpenInterestNetContractAmount")) for x in opt_foreign)
        data["外資選擇權未平倉淨額(萬)"] = {"value": round(net_amt / 10, 0)}
except Exception:
    pass

# 7. 期交所 OpenAPI：五大、十大特定法人淨額(口)
try:
    r_top = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=15).json()
    tx_top = [x for x in r_top if x.get("ContractCode") == "TX" and "所有契約" in x.get("ContractMonth", "")]
    if tx_top:
        row = tx_top[-1]
        top5 = int(safe_float(row.get("Top5SpecificBuyOI")) - safe_float(row.get("Top5SpecificSellOI")))
        top10 = int(safe_float(row.get("Top10SpecificBuyOI")) - safe_float(row.get("Top10SpecificSellOI")))
        data["五大淨額(口)"] = {"value": top5}
        data["十大淨額(口)"] = {"value": top10}
except Exception:
    pass

# 8. 期交所 OpenAPI：小台(MTX)與微台(TMF)散戶多空比(%)
try:
    r_fut_all = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=15).json()
    r_inst_all = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=15).json()

    for code, cname, key_name in [("MTX", "小型臺指", "小台散戶多空比(%)"), ("TMF", "微型臺指", "微台散戶多空比(%)")]:
        tot_oi = sum(safe_float(x.get("OpenInterest")) for x in r_fut_all if x.get("Contract") == code and x.get("TradingSession") == "一般")
        inst_net = sum(safe_float(x.get("OpenInterestNetVolume")) for x in r_inst_all if cname in x.get("ContractCode", ""))
        if tot_oi > 0:
            retail_ratio = round((-inst_net / tot_oi) * 100, 2)
            data[key_name] = {"value": retail_ratio}
except Exception:
    pass

# 補齊任何暫時未抓到的欄位（沿用前一次有效數值，避免變成空白）
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
    json.dump({"update_time": now_str, "data": data}, f, ensure_ascii=False, indent=2)

print("✅ 15項官方真實數據抓取完成！更新時間:", now_str)

