import io
import json
import math
import urllib.parse
import urllib3
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

tw_tz = timezone(timedelta(hours=8))
now_str = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"
}

try:
    with open("data.json", "r", encoding="utf-8") as f:
        old_data = json.load(f).get("data", {})
except Exception:
    old_data = {}

def safe_float(val, default=None):
    try:
        v = float(str(val).replace(",", "").replace("%", "").replace("+", "").strip())
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default

def fetch_text_smart(url):
    # 多路通道備援：直連 -> corsproxy -> codetabs -> allorigins
    proxies = [
        url,
        "https://corsproxy.io?" + urllib.parse.quote(url, safe=""),
        "https://codetabs.com" + urllib.parse.quote(url, safe=""),
        "https://allorigins.win" + urllib.parse.quote(url, safe="")
    ]
    for target in proxies:
        try:
            r = requests.get(target, headers=headers, verify=False, timeout=12)
            if r.status_code == 200 and len(r.text.strip()) > 50:
                return r.text
        except Exception:
            continue
    return None

def fetch_json_smart(url):
    txt = fetch_text_smart(url)
    if txt:
        try:
            return json.loads(txt)
        except Exception:
            pass
    return None

data = {}
logs = []

# 1. Yahoo 財經引擎：台積電 ADR (TSM) & 美元兌台幣 (TWD=X)
try:
    tsm = yf.Ticker("TSM").history(period="5d").dropna(subset=["Close"])
    if len(tsm) >= 2:
        val = safe_float(tsm["Close"].iloc[-1])
        prev_v = safe_float(tsm["Close"].iloc[-2])
        if val is not None and prev_v is not None:
            data["台積電美股ADR指數"] = {"value": round(val, 2), "change": round(val - prev_v, 2)}
            logs.append(f"✅ 台積電ADR: {round(val, 2)}")
except Exception as e:
    logs.append(f"❌ 台積電ADR失敗: {e}")

try:
    usd = yf.Ticker("TWD=X").history(period="5d").dropna(subset=["Close"])
    if len(usd) >= 1:
        val = safe_float(usd["Close"].iloc[-1])
        if val is not None:
            data["美元兌台幣"] = {"value": round(val, 3)}
            logs.append(f"✅ 美元兌台幣: {round(val, 3)}")
except Exception as e:
    logs.append(f"❌ 美元兌台幣失敗: {e}")

# 2. 證交所：三大法人現貨買賣超 (單位：億)
r_bfi = fetch_json_smart("https://twse.com.tw")
if r_bfi and r_bfi.get("stat") == "OK":
    for row in r_bfi.get("data", []):
        name = str(row[0]).strip()
        diff_raw = safe_float(row[3])
        if diff_raw is not None:
            diff = round(diff_raw / 1e8, 2)
            if "自營商" in name and "避險" not in name and "自行" not in name:
                data["自營商現貨(億)"] = {"value": diff}
            elif "投信" in name:
                data["投信現貨(億)"] = {"value": diff}
            elif "外資及陸資" in name:
                data["外資現貨(億)"] = {"value": diff}
    logs.append("✅ 三大法人現貨抓取成功")
else:
    logs.append("❌ 三大法人現貨連線受阻")

# 3. 證交所：大盤現貨成交量 (單位：億)
r_vol = fetch_json_smart("https://twse.com.tw")
if r_vol and r_vol.get("stat") == "OK" and r_vol.get("data"):
    last_row = r_vol["data"][-1]
    vol_raw = safe_float(last_row[2])
    if vol_raw is not None:
        data["現貨量(億)"] = {"value": round(vol_raw / 1e8, 2)}
        logs.append(f"✅ 現貨量({last_row[0]}): {round(vol_raw / 1e8, 2)}億")
else:
    logs.append("❌ 現貨量連線受阻")

# 4. 證交所：融資餘額 (單位：億)
r_mi = fetch_json_smart("https://twse.com.tw")
if r_mi and r_mi.get("stat") == "OK" and "tables" in r_mi:
    for tbl in r_mi["tables"]:
        for row in tbl.get("data", []):
            if "融資金額" in str(row[0]):
                p_raw = safe_float(row[4])
                c_raw = safe_float(row[5])
                if p_raw is not None and c_raw is not None:
                    data["融資餘額(億)"] = {"value": round(c_raw / 1e5, 2), "prev": round(p_raw / 1e5, 2)}
                    logs.append(f"✅ 融資餘額: {round(c_raw / 1e5, 2)}億")
else:
    logs.append("❌ 融資餘額連線受阻")

# 5. 期交所 OpenAPI：台指結算/收盤 & P/C比
r_fut = fetch_json_smart("https://taifex.com.tw")
if isinstance(r_fut, list):
    tx_rows = [x for x in r_fut if x.get("Contract") == "TX" and x.get("TradingSession") == "一般"]
    if tx_rows:
        close_p = safe_float(tx_rows[0].get("Close"))
        chg_p = safe_float(tx_rows[0].get("Change"), 0.0)
        if close_p is not None and close_p > 0:
            data["台指結算"] = {"value": int(close_p), "prev": int(close_p - chg_p)}
            logs.append(f"✅ 台指結算: {int(close_p)}")
else:
    logs.append("❌ 台指結算連線受阻")

r_pc = fetch_json_smart("https://taifex.com.tw")
if isinstance(r_pc, list) and r_pc:
    pc_val = safe_float(r_pc[-1].get("PutCallRatio"))
    if pc_val is not None:
        data["P/C未平倉比"] = {"value": f"{pc_val}%"}
        logs.append(f"✅ P/C比: {pc_val}%")
else:
    logs.append("❌ P/C比連線受阻")

# 6. 期交所 OpenAPI：三大法人台指期未平倉 & 選擇權未平倉淨額(萬)
r_inst = fetch_json_smart("https://taifex.com.tw")
if isinstance(r_inst, list):
    tx_foreign = [x for x in r_inst if "臺股期貨" in x.get("ContractCode", "") and "外資" in x.get("Item", "")]
    if tx_foreign:
        oi_raw = safe_float(tx_foreign[-1].get("OpenInterestNetVolume"))
        if oi_raw is not None:
            oi_net = int(oi_raw)
            old_oi = old_data.get("外資台指期未平倉", {}).get("value", oi_net)
            prev_oi = old_oi if isinstance(old_oi, (int, float)) and old_oi != oi_net else old_data.get("外資台指期未平倉", {}).get("prev", oi_net)
            data["外資台指期未平倉"] = {"value": oi_net, "prev": prev_oi}
            logs.append(f"✅ 外資台指期未平倉: {oi_net}")
else:
    logs.append("❌ 外資台指期連線受阻")

r_opt = fetch_json_smart("https://taifex.com.tw")
if isinstance(r_opt, list):
    opt_foreign = [x for x in r_opt if "臺指選擇權" in x.get("ContractCode", "") and "外資" in x.get("Item", "")]
    if opt_foreign:
        net_amt = sum(safe_float(x.get("OpenInterestNetContractAmount"), 0.0) for x in opt_foreign)
        data["外資選擇權未平倉淨額(萬)"] = {"value": round(net_amt / 10, 0)}
        logs.append(f"✅ 外資選擇權淨額: {round(net_amt / 10, 0)}萬")
else:
    logs.append("❌ 外資選擇權連線受阻")

# 7. 期交所 OpenAPI：五大、十大特定法人淨額(口)
r_top = fetch_json_smart("https://taifex.com.tw")
if isinstance(r_top, list):
    tx_top = [x for x in r_top if x.get("ContractCode") == "TX" and "所有契約" in x.get("ContractMonth", "")]
    if tx_top:
        row = tx_top[-1]
        t5_b = safe_float(row.get("Top5SpecificBuyOI"))
        t5_s = safe_float(row.get("Top5SpecificSellOI"))
        t10_b = safe_float(row.get("Top10SpecificBuyOI"))
        t10_s = safe_float(row.get("Top10SpecificSellOI"))
        if None not in (t5_b, t5_s, t10_b, t10_s):
            data["五大淨額(口)"] = {"value": int(t5_b - t5_s)}
            data["十大淨額(口)"] = {"value": int(t10_b - t10_s)}
            logs.append("✅ 五大/十大淨額抓取成功")
else:
    logs.append("❌ 五大十大連線受阻")

# 8. 期交所 OpenAPI：小台(MTX)與微台(TMF)散戶多空比(%)
if isinstance(r_fut, list) and isinstance(r_inst, list):
    for code, cname, key_name in [("MTX", "小型臺指", "小台散戶多空比(%)"), ("TMF", "微型臺指", "微台散戶多空比(%)")]:
        tot_oi = sum(safe_float(x.get("OpenInterest"), 0.0) for x in r_fut if x.get("Contract") == code and x.get("TradingSession") == "一般")
        inst_net = sum(safe_float(x.get("OpenInterestNetVolume"), 0.0) for x in r_inst if cname in x.get("ContractCode", ""))
        if tot_oi > 0:
            retail_ratio = round((-inst_net / tot_oi) * 100, 2)
            data[key_name] = {"value": retail_ratio}
            logs.append(f"✅ {key_name}: {retail_ratio}%")

# 補齊任何暫時未抓到的欄位
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

print("=== 執行診斷報告 ===")
for line in logs:
    print(line)
print("✅ 更新完成時間:", now_str)
