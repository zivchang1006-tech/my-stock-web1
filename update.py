import json
import math
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

tw_tz = timezone(timedelta(hours=8))
now_dt = datetime.now(tw_tz)
now_str = now_dt.strftime("%Y-%m-%d %H:%M")
start_date = (now_dt - timedelta(days=10)).strftime("%Y-%m-%d")

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

def get_finmind(dataset, data_id="TAIEX"):
    url = f"https://finmindtrade.com{dataset}&data_id={data_id}&start_date={start_date}"
    try:
        r = requests.get(url, timeout=10).json()
        if r.get("msg") == "success" and r.get("data"):
            return r["data"]
        else:
            print(f"⚠️ FinMind({dataset}/{data_id}) 回傳訊息:", r.get("msg"))
    except Exception as e:
        print(f"⚠️ FinMind({dataset}/{data_id}) 連線錯誤:", e)
    return []

data = {}
logs = []

# 1. Yahoo 財經：台積電 ADR (TSM) & 美元兌台幣 (TWD=X)
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

# 2. FinMind (帶入 data_id=TAIEX)：三大法人現貨買賣超 (單位：億)
inst_rows = get_finmind("TaiwanStockTotalInstitutionalInvestors", "TAIEX")
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
    logs.append(f"✅ 三大法人現貨({last_date}): 外資{data.get('外資現貨(億)',{}).get('value')}億")

# 3. FinMind (帶入 data_id=TAIEX)：大盤現貨成交量 & 融資餘額 (單位：億)
mkt_rows = get_finmind("TaiwanStockPrice", "TAIEX")
if mkt_rows:
    vol_yi = round(safe_float(mkt_rows[-1].get("Trading_money"), 0) / 1e8, 2)
    if vol_yi > 0:
        data["現貨量(億)"] = {"value": vol_yi}
        logs.append(f"✅ 現貨量({mkt_rows[-1]['date']}): {vol_yi}億")

margin_rows = get_finmind("TaiwanStockTotalMarginPurchaseShortSale", "TAIEX")
if margin_rows:
    m_list = [x for x in margin_rows if x.get("name") == "MarginPurchaseMoney"]
    if len(m_list) >= 2:
        prev_m = round(safe_float(m_list[-2].get("TodayBalance"), 0) / 1e5, 2)
        curr_m = round(safe_float(m_list[-1].get("TodayBalance"), 0) / 1e5, 2)
        data["融資餘額(億)"] = {"value": curr_m, "prev": prev_m}
        logs.append(f"✅ 融資餘額: {curr_m}億 (前日:{prev_m})")

# 4. FinMind (帶入 data_id=TX)：台指期結算/收盤價
fut_rows = get_finmind("TaiwanFuturesDaily", "TX")
if fut_rows:
    reg_rows = [x for x in fut_rows if x.get("trading_session") == "position"]
    # 依日期分組取近月契約最大成交量
    dates = sorted(list(set(x["date"] for x in reg_rows)))
    if len(dates) >= 2:
        d_prev, d_curr = dates[-2], dates[-1]
        c_rows = [x for x in reg_rows if x["date"] == d_curr]
        p_rows = [x for x in reg_rows if x["date"] == d_prev]
        c_main = max(c_rows, key=lambda x: safe_float(x.get("volume"), 0))
        p_main = max(p_rows, key=lambda x: safe_float(x.get("volume"), 0))
        c_p = int(safe_float(c_main.get("close"), 0))
        p_p = int(safe_float(p_main.get("close"), 0))
        if c_p > 0:
            data["台指結算"] = {"value": c_p, "prev": p_p}
            logs.append(f"✅ 台指結算({d_curr}): {c_p} (前日:{p_p})")

# 5. FinMind (帶入 data_id=TX)：外資台指期未平倉
fut_inst = get_finmind("TaiwanFuturesInstitutionalInvestors", "TX")
if fut_inst:
    f_list = [x for x in fut_inst if "外資" in x.get("institutional_investors", "")]
    if len(f_list) >= 2:
        curr_oi = int(safe_float(f_list[-1].get("long_open_interest_balance_volume"), 0) - safe_float(f_list[-1].get("short_open_interest_balance_volume"), 0))
        prev_oi = int(safe_float(f_list[-2].get("long_open_interest_balance_volume"), 0) - safe_float(f_list[-2].get("short_open_interest_balance_volume"), 0))
        data["外資台指期未平倉"] = {"value": curr_oi, "prev": prev_oi}
        logs.append(f"✅ 外資台指期未平倉: {curr_oi} (前日:{prev_oi})")

# 6. FinMind (帶入 MTX 與 TMF)：小台與微台散戶多空比(%)
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

# 7. FinMind (帶入 data_id=TXO)：選擇權 P/C 未平倉比 & 外資選擇權未平倉淨額(萬)
opt_daily = get_finmind("TaiwanOptionDaily", "TXO")
if opt_daily:
    last_d = opt_daily[-1]["date"]
    day_opt = [x for x in opt_daily if x["date"] == last_d and x.get("trading_session") == "position"]
    put_oi = sum(safe_float(x.get("open_interest"), 0) for x in day_opt if x.get("call_put") == "put")
    call_oi = sum(safe_float(x.get("open_interest"), 0) for x in day_opt if x.get("call_put") == "call")
    if call_oi > 0:
        pc_ratio = round((put_oi / call_oi) * 100, 2)
        data["P/C未平倉比"] = {"value": f"{pc_ratio}%"}
        logs.append(f"✅ P/C未平倉比: {pc_ratio}%")

opt_inst = get_finmind("TaiwanOptionInstitutionalInvestors", "TXO")
if opt_inst:
    last_d = opt_inst[-1]["date"]
    f_opt = [x for x in opt_inst if x["date"] == last_d and "外資" in x.get("institutional_investors", "")]
    if f_opt:
        net_amt = sum(safe_float(x.get("long_open_interest_balance_amount"), 0) - safe_float(x.get("short_open_interest_balance_amount"), 0) for x in f_opt)
        val_wan = round(net_amt / 10000, 0)
        data["外資選擇權未平倉淨額(萬)"] = {"value": val_wan}
        logs.append(f"✅ 外資選擇權未平倉淨額: {val_wan}萬")

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


