import json
import math
import urllib3
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

tw_tz = timezone(timedelta(hours=8))
now_dt = datetime.now(tw_tz)
now_str = now_dt.strftime("%Y-%m-%d %H:%M")
start_date = (now_dt - timedelta(days=7)).strftime("%Y-%m-%d")

try:
    with open("data.json", "r", encoding="utf-8") as f:
        old_data = json.load(f).get("data", {})
except Exception:
    old_data = {}

def safe_float(val, default=None):
    try:
        v = float(str(val).replace(",", "").replace("%", "").strip())
        return None if (math.isnan(v) or math.isinf(v)) else v
    except Exception:
        return default

def get_finmind(dataset, data_id=""):
    url = f"https://finmindtrade.com{dataset}&start_date={start_date}"
    if data_id:
        url += f"&data_id={data_id}"
    try:
        r = requests.get(url, timeout=8).json()
        if r.get("msg") == "success" and r.get("data"):
            return r["data"]
    except Exception:
        pass
    return []

data = {}
logs = []

# 1. Yahoo 財經：台積電 ADR (TSM) & 美元兌台幣 (TWD=X) & 大盤現貨量 (^TWII)
try:
    tsm = yf.Ticker("TSM").history(period="5d").dropna(subset=["Close"])
    if len(tsm) >= 2:
        val = safe_float(tsm["Close"].iloc[-1])
        prev_v = safe_float(tsm["Close"].iloc[-2])
        if val and prev_v:
            data["台積電美股ADR指數"] = {"value": round(val, 2), "change": round(val - prev_v, 2)}
            logs.append(f"✅ 台積電ADR: {round(val, 2)}")
except Exception as e:
    logs.append(f"❌ 台積電ADR: {e}")

try:
    usd = yf.Ticker("TWD=X").history(period="5d").dropna(subset=["Close"])
    if len(usd) >= 1:
        val = safe_float(usd["Close"].iloc[-1])
        if val:
            data["美元兌台幣"] = {"value": round(val, 3)}
            logs.append(f"✅ 美元兌台幣: {round(val, 3)}")
except Exception as e:
    logs.append(f"❌ 美元兌台幣: {e}")

# 2. FinMind 台灣股市開放資料庫：三大法人現貨買賣超 (單位：億)
inst_rows = get_finmind("TaiwanStockTotalInstitutionalInvestors")
if inst_rows:
    last_date = inst_rows[-1]["date"]
    day_rows = [x for x in inst_rows if x["date"] == last_date]
    for x in day_rows:
        net_yi = round((safe_float(x.get("buy"), 0) - safe_float(x.get("sell"), 0)) / 1e8, 2)
        name = x.get("name", "")
        if "Foreign_Investor" in name:
            data["外資現貨(億)"] = {"value": net_yi}
        elif "Investment_Trust" in name:
            data["投信現貨(億)"] = {"value": net_yi}
        elif "Dealer_self" in name:
            data["自營商現貨(億)"] = {"value": net_yi}
    logs.append(f"✅ 三大法人現貨({last_date})抓取成功")

# 3. FinMind：大盤現貨成交量 & 融資餘額 (單位：億)
mkt_rows = get_finmind("TaiwanStockTotalReturnIndex")
if not mkt_rows:
    mkt_rows = get_finmind("TaiwanStockPrice", "TAIEX")
if mkt_rows:
    vol_yi = round(safe_float(mkt_rows[-1].get("Trading_money"), 0) / 1e8, 2)
    if vol_yi > 0:
        data["現貨量(億)"] = {"value": vol_yi}
        logs.append(f"✅ 現貨量: {vol_yi}億")

margin_rows = get_finmind("TaiwanStockTotalMarginPurchaseShortSale")
if margin_rows:
    m_list = [x for x in margin_rows if x.get("name") == "MarginPurchaseMoney"]
    if len(m_list) >= 2:
        prev_m = round(safe_float(m_list[-2].get("TodayBalance"), 0) / 1e5, 2)
        curr_m = round(safe_float(m_list[-1].get("TodayBalance"), 0) / 1e5, 2)
        data["融資餘額(億)"] = {"value": curr_m, "prev": prev_m}
        logs.append(f"✅ 融資餘額: {curr_m}億 (前日:{prev_m})")

# 4. FinMind：台指期結算/收盤價
fut_rows = get_finmind("TaiwanFuturesDaily", "TX")
if fut_rows:
    reg_rows = [x for x in fut_rows if x.get("trading_session") == "position"]
    if len(reg_rows) >= 2:
        c_p = int(safe_float(reg_rows[-1].get("close"), 0))
        p_p = int(safe_float(reg_rows[-2].get("close"), 0))
        if c_p > 0:
            data["台指結算"] = {"value": c_p, "prev": p_p}
            logs.append(f"✅ 台指結算: {c_p}")

# 5. FinMind：外資台指期未平倉 & 小台/微台散戶多空比
fut_inst = get_finmind("TaiwanFuturesInstitutionalInvestors", "TX")
if fut_inst:
    f_list = [x for x in fut_inst if "外資" in x.get("institutional_investors", "")]
    if len(f_list) >= 2:
        curr_oi = int(safe_float(f_list[-1].get("long_open_interest_balance_volume"), 0) - safe_float(f_list[-1].get("short_open_interest_balance_volume"), 0))
        prev_oi = int(safe_float(f_list[-2].get("long_open_interest_balance_volume"), 0) - safe_float(f_list[-2].get("short_open_interest_balance_volume"), 0))
        data["外資台指期未平倉"] = {"value": curr_oi, "prev": prev_oi}
        logs.append(f"✅ 外資台指期未平倉: {curr_oi}")

for code, key_name in [("MTX", "小台散戶多空比(%)"), ("TMF", "微台散戶多空比(%)")]:
    f_all = get_finmind("TaiwanFuturesDaily", code)
    i_all = get_finmind("TaiwanFuturesInstitutionalInvestors", code)
    if f_all and i_all:
        last_d = f_all[-1]["date"]
        tot_oi = sum(safe_float(x.get("open_interest"), 0) for x in f_all if x["date"] == last_d and x.get("trading_session") == "position")
        inst_net = sum(safe_float(x.get("long_open_interest_balance_volume"), 0) - safe_float(x.get("short_open_interest_balance_volume"), 0) for x in i_all if x["date"] == last_d)
        if tot_oi > 0:
            ratio = round((-inst_net / tot_oi) * 100, 2)
            data[key_name] = {"value": ratio}
            logs.append(f"✅ {key_name}: {ratio}%")

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

