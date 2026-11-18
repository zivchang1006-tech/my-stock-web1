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
    "Referer": "https://wantgoo.com",
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

# 1. 台積電美股 ADR & 美元兌台幣（抓前一交易日收盤）
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

# 2. 玩股網頁面解析（優先抓取玩股網公開盤後數據）
try:
    wg_html = requests.get("https://wantgoo.comfutures/retail-indicator/wmx", headers=headers, timeout=12).text
    mtx_match = re.search(r'"mtxRatio"\s*:\s*([-\d.]+)', wg_html)
    tmf_match = re.search(r'"tmfRatio"\s*:\s*([-\d.]+)', wg_html)
    if mtx_match:
        data["小台散戶多空比(%)"] = {"value": round(float(mtx_match.group(1)), 2)}
    if tmf_match:
        data["微台散戶多空比(%)"] = {"value": round(float(tmf_match.group(1)), 2)}
except Exception:
    pass

# 3. 證交所：前一日三大法人現貨、成交量與融資餘額
try:
    r_bfi = requests.get("https://twse.com.tw", headers=headers, verify=False, timeout=12).json()
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
    r_vol = requests.get("https://twse.com.tw", headers=headers, verify=False, timeout=12).json()
    if r_vol.get("stat") == "OK" and r_vol.get("data"):
        vol_raw = safe_float(r_vol["data"][-1][2])
        if vol_raw is not None:
            data["現貨量(億)"] = {"value": round(vol_raw / 1e8, 2)}
except Exception:
    pass

try:
    r_mi = requests.get("https://twse.com.tw", headers=headers, verify=False, timeout=12).json()
    if r_mi.get("stat") == "OK" and "tables" in r_mi:
        for tbl in r_mi["tables"]:
            for row in tbl.get("data", []):
                if "融資金額" in str(row[0]):
                    p_raw, c_raw = safe_float(row[4]), safe_float(row[5])
                    if p_raw is not None and c_raw is not None:
                        data["融資餘額(億)"] = {"value": round(c_raw / 1e5, 2), "prev": round(p_raw / 1e5, 2)}
except Exception:
    pass

# 4. 期交所：前一日台指期、外資未平倉、五大十大、P/C比與散戶多空比
r_fut, r_inst = [], []
try:
    r_fut = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=12).json()
    if isinstance(r_fut, list):
        tx_rows = [x for x in r_fut if x.get("Contract") == "TX" and x.get("TradingSession") == "一般"]
        if tx_rows:
            close_p = safe_float(tx_rows[0].get("Close"))
            chg_p = safe_float(tx_rows[0].get("Change"), 0.0)
            if close_p and close_p > 0:
                data["台指結算"] = {"value": int(close_p), "prev": int(close_p - chg_p)}
except Exception:
    pass

try:
    r_pc = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=12).json()
    if isinstance(r_pc, list) and r_pc and safe_float(r_pc[-1].get("PutCallRatio")) is not None:
        data["P/C未平倉比"] = {"value": f"{safe_float(r_pc[-1].get('PutCallRatio'))}%"}
except Exception:
    pass

try:
    r_inst = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=12).json()
    if isinstance(r_inst, list):
        tx_foreign = [x for x in r_inst if "臺股期貨" in x.get("ContractCode", "") and "外資" in x.get("Item", "")]
        if tx_foreign and safe_float(tx_foreign[-1].get("OpenInterestNetVolume")) is not None:
            oi_net = int(safe_float(tx_foreign[-1].get("OpenInterestNetVolume")))
            old_oi = old_data.get("外資台指期未平倉", {}).get("value", oi_net)
            prev_oi = old_oi if isinstance(old_oi, (int, float)) and old_oi != oi_net else old_data.get("外資台指期未平倉", {}).get("prev", oi_net)
            data["外資台指期未平倉"] = {"value": oi_net, "prev": prev_oi}
except Exception:
    pass

try:
    r_opt = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=12).json()
    if isinstance(r_opt, list):
        opt_foreign = [x for x in r_opt if "臺指選擇權" in x.get("ContractCode", "") and "外資" in x.get("Item", "")]
        if opt_foreign:
            net_amt = sum(safe_float(x.get("OpenInterestNetContractAmount"), 0.0) for x in opt_foreign)
            data["外資選擇權未平倉淨額(萬)"] = {"value": round(net_amt / 10, 0)}
except Exception:
    pass

try:
    r_top = requests.get("https://taifex.com.tw", headers=headers, verify=False, timeout=12).json()
    if isinstance(r_top, list):
        tx_top = [x for x in r_top if x.get("ContractCode") == "TX" and "所有契約" in x.get("ContractMonth", "")]
        if tx_top:
            row = tx_top[-1]
            t5_b, t5_s = safe_float(row.get("Top5SpecificBuyOI")), safe_float(row.get("Top5SpecificSellOI"))
            t10_b, t10_s = safe_float(row.get("Top10SpecificBuyOI")), safe_float(row.get("Top10SpecificSellOI"))
            if None not in (t5_b, t5_s, t10_b, t10_s):
                data["五大淨額(口)"] = {"value": int(t5_b - t5_s)}
                data["十大淨額(口)"] = {"value": int(t10_b - t10_s)}
except Exception:
    pass

if isinstance(r_fut, list) and isinstance(r_inst, list) and r_fut and r_inst:
    for code, cname, key_name in [("MTX", "小型臺指", "小台散戶多空比(%)"), ("TMF", "微型臺指", "微台散戶多空比(%)")]:
        if key_name not in data:
            tot_oi = sum(safe_float(x.get("OpenInterest"), 0.0) for x in r_fut if x.get("Contract") == code and x.get("TradingSession") == "一般")
            inst_net = sum(safe_float(x.get("OpenInterestNetVolume"), 0.0) for x in r_inst if cname in x.get("ContractCode", ""))
            if tot_oi > 0:
                data[key_name] = {"value": round((-inst_net / tot_oi) * 100, 2)}

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

print("✅ 玩股網與官方盤後備援更新完成！時間:", now_str)
