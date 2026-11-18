import json
import math
import urllib.parse
import urllib3
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

tw_tz = timezone(timedelta(hours=8))
now_str = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    with open("data.json", "r", encoding="utf-8") as f:
        old_data = json.load(f).get("data", {})
except Exception:
    old_data = {}

def safe_float(val, default=None):
    try:
        v = float(str(val).replace(",", "").replace("%", "").strip())
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default

def fetch_json_smart(url):
    # 先直接連線台灣官方伺服器，若被海外機房限制則自動切換公開中繼站
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=10)
        if r.status_code == 200 and r.text.strip():
            return r.json()
    except Exception:
        pass
    proxy_url = "https://allorigins.win" + urllib.parse.quote(url, safe="")
    r2 = requests.get(proxy_url, headers=headers, timeout=20)
    return r2.json()

data = {}
logs = []

# 1. 台積電美股 ADR (TSM) & 美元兌台幣 (TWD=X)
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
try:
    r = fetch_json_smart("https://twse.com.tw")
    if r.get("stat") == "OK":
        for row in r["data"]:
            name = str(row).strip()
            diff_raw = safe_float(row)
            if diff_raw is not None:
                diff = round(diff_raw / 1e8, 2)
                if "自營商" in name and "避險" not in name and "自行" not in name:
                    data["自營商現貨(億)"] = {"value": diff}
                elif "投信" in name:
                    data["投信現貨(億)"] = {"value": diff}
                elif "外資及陸資" in name:
                    data["外資現貨(億)"] = {"value": diff}
        logs.append("✅ 三大法人現貨抓取成功")
except Exception as e:
    logs.append(f"❌ 三大法人現貨失敗: {e}")

# 3. 證交所：大盤現貨成交量 (單位：億)
try:
    r_vol = fetch_json_smart("https://twse.com.tw")
    if r_vol.get("stat") == "OK" and r_vol.get("data"):
        last_row = r_vol["data"][-1]
        vol_raw = safe_float(last_row)
        if vol_raw is not None:
            data["現貨量(億)"] = {"value": round(vol_raw / 1e8, 2)}
            logs.append(f"✅ 現貨量抓取成功: {round(vol_raw / 1e8, 2)}億")
except Exception as e:
    logs.append(f"❌ 現貨量失敗: {e}")

# 4. 證交所：融資餘額 (單位：億)
try:
    r_mi = fetch_json_smart("https://twse.com.tw")
    if r_mi.get("stat") == "OK" and "tables" in r_mi:
        for tbl in r_mi["tables"]:
            for row in tbl.get("data", []):
                if "融資金額" in str(row):
                    p_raw = safe_float(row)
                    c_raw = safe_float(row)
                    if p_raw is not None and c_raw is not None:
                        data["融資餘額(億)"] = {"value": round(c_raw / 1e5, 2), "prev": round(p_raw / 1e5, 2)}
                        logs.append(f"✅ 融資餘額抓取成功: {round(c_raw / 1e5, 2)}億")
except Exception as e:
    logs.append(f"❌ 融資餘額失敗: {e}")

# 5. 期交所 OpenAPI：台指結算/收盤 & P/C比
try:
    r_fut = fetch_json_smart("https://taifex.com.tw")
    tx_rows = [x for x in r_fut if x.get("Contract") == "TX" and x.get("TradingSession") == "一般"]
    if tx_rows:
        close_p = safe_float(tx_rows.get("Close"))
        chg_p = safe_float(tx_rows.get("Change"), 0.0)
        if close_p is not None and close_p > 0:
            data["台指結算"] = {"value": int(close_p), "prev": int(close_p - chg_p)}
            logs.append(f"✅ 台指結算抓取成功: {int(close_p)}")
except Exception as e:
    logs.append(f"❌ 台指結算失敗: {e}")

try:
    r_pc = fetch_json_smart("https://taifex.com.tw")
    if r_pc:
        pc_val = safe_float(r_pc[-1].get("PutCallRatio"))
        if pc_val is not None:
            data["P/C未平倉比"] = {"value": f"{pc_val}%"}
            logs.append(f"✅ P/C比抓取成功: {pc_val}%")
except Exception as e:
    logs.append(f"❌ P/C比失敗: {e}")

# 6. 期交所 OpenAPI：三大法人台指期未平倉 & 選擇權未平倉淨額(萬)
try:
    r_inst = fetch_json_smart("https://taifex.com.tw")
    tx_foreign = [x for x in r_inst if "臺股期貨" in x.get("ContractCode", "") and "外資" in x.get("Item", "")]
    if tx_foreign:
        oi_raw = safe_float(tx_foreign[-1].get("OpenInterestNetVolume"))
        if oi_raw is not None:
            oi_net = int(oi_raw)
            old_oi = old_data.get("外資台指期未平倉", {}).get("value", oi_net)
            prev_oi = old_oi if isinstance(old_oi, (int, float)) and old_oi != oi_net else old_data.get("外資台指期未平倉", {}).get("prev", oi_net)
            data["外資台指期未平倉"] = {"value": oi_net, "prev": prev_oi}
            logs.append(f"✅ 外資台指期未平倉抓取成功: {oi_net}")
except Exception as e:
    logs.append(f"❌ 外資台指期失敗: {e}")

try:
    r_opt = fetch_json_smart("https://taifex.com.tw")
    opt_foreign = [x for x in r_opt if "臺指選擇權" in x.get("ContractCode", "") and "外資" in x.get("Item", "")]
    if opt_foreign:
        net_amt = sum(safe_float(x.get("OpenInterestNetContractAmount"), 0.0) for x in opt_foreign)
        data["外資選擇權未平倉淨額(萬)"] = {"value": round(net_amt / 10, 0)}
        logs.append(f"✅ 外資選擇權淨額抓取成功: {round(net_amt / 10, 0)}萬")
except Exception as e:
    logs.append(f"❌ 外資選擇權失敗: {e}")

# 7. 期交所 OpenAPI：五大、十大特定法人淨額(口)
try:
    r_top = fetch_json_smart("https://taifex.com.tw")
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
except Exception as e:
    logs.append(f"❌ 五大十大失敗: {e}")

# 8. 期交所 OpenAPI：小台(MTX)與微台(TMF)散戶多空比(%)
try:
    r_fut_all = fetch_json_smart("https://taifex.com.tw")
    r_inst_all = fetch_json_smart("https://taifex.com.tw")

    for code, cname, key_name in [("MTX", "小型臺指", "小台散戶多空比(%)"), ("TMF", "微型臺指", "微台散戶多空比(%)")]:
        tot_oi = sum(safe_float(x.get("OpenInterest"), 0.0) for x in r_fut_all if x.get("Contract") == code and x.get("TradingSession") == "一般")
        inst_net = sum(safe_float(x.get("OpenInterestNetVolume"), 0.0) for x in r_inst_all if cname in x.get("ContractCode", ""))
        if tot_oi > 0:
            retail_ratio = round((-inst_net / tot_oi) * 100, 2)
            data[key_name] = {"value": retail_ratio}
            logs.append(f"✅ {key_name}抓取成功: {retail_ratio}%")
except Exception as e:
    logs.append(f"❌ 散戶多空比失敗: {e}")

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
