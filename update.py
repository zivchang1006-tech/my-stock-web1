import json
import math
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

tw_tz = timezone(timedelta(hours=8))
now_dt = datetime.now(tw_tz)
now_str = now_dt.strftime("%Y-%m-%d %H:%M")
start_date = (now_dt - timedelta(days=10)).strftime("%Y-%m-%d")

FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoieml2Y2hhbmcxMDA2QGdtYWlsLmNvbSIsImVtYWlsIjoieml2Y2hhbmcxMDA2QGdtYWlsLmNvbSIsInRva2VuX3ZlcnNpb24iOjB9.TVG3yuVUINXfZLW8vctJ33W_M3-WB_6Uaq81L1DK7Dk"

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
    url = "https://finmindtrade.com"
    params = {
        "dataset": dataset,
        "start_date": start_date,
        "token": FINMIND_TOKEN
    }
    if data_id:
        params["data_id"] = data_id
    try:
        r = requests.get(url, params=params, timeout=12).json()
        if r.get("msg") == "success" and r.get("data"):
            return r["data"]
        else:
            print(f"⚠️ {dataset} 回傳:", r.get("msg"))
    except Exception as e:
        print(f"⚠️ {dataset} 錯誤:", e)
    return []

data = {}

# 1. 台積電 ADR & 美元兌台幣
try:
    tsm = yf.Ticker("TSM").history(period="5d").dropna(subset=["Close"])
    if len(tsm) >= 2:
        val, prev_v = safe_float(tsm["Close"].iloc[-1]), safe_float(tsm["Close"].iloc[-2])
        if val and prev_v:
            data["台積電美股ADR指數"] = {"value": round(val, 2), "change": round(val - prev_v, 2)}
except Exception:
    pass

try:
    usd = yf.Ticker("TWD=X").history(period="5d").dropna(subset=["Close"])
    if len(usd) >= 1 and safe_float(usd["Close"].iloc[-1]):
        data["美元兌台幣"] = {"value": round(safe_float(usd["Close"].iloc[-1]), 3)}
except Exception:
    pass

# 2. 三大法人現貨買賣超 (億)
inst_rows = get_finmind("TaiwanStockTotalInstitutionalInvestors")
if inst_rows:
    last_d = inst_rows[-1]["date"]
    for x in [r for r in inst_rows if r["date"] == last_d]:
        net_yi = round((safe_float(x.get("buy"), 0) - safe_float(x.get("sell"), 0)) / 1e8, 2)
        name = x.get("name", "")
        if "Foreign_Investor" in name:
            data["外資現貨(億)"] = {"value": net_yi}
        elif "Investment_Trust" in name:
            data["投信現貨(億)"] = {"value": net_yi}
        elif "Dealer_self" in name:
            data["自營商現貨(億)"] = {"value": net_yi}

# 3. 大盤現貨成交量 & 融資餘額 (億)
mkt_rows = get_finmind("TaiwanStockPrice", "TAIEX")
if mkt_rows:
    vol_yi = round(safe_float(mkt_rows[-1].get("Trading_money"), 0) / 1e8, 2)
    if vol_yi > 0:
        data["現貨量(億)"] = {"value": vol_yi}

margin_rows = get_finmind("TaiwanStockTotalMarginPurchaseShortSale")
if margin_rows:
    m_list = [x for x in margin_rows if x.get("name") == "MarginPurchaseMoney"]
    if len(m_list) >= 2:
        data["融資餘額(億)"] = {
            "value": round(safe_float(m_list[-1].get("TodayBalance"), 0) / 1e5, 2),
            "prev": round(safe_float(m_list[-2].get("TodayBalance"), 0) / 1e5, 2)
        }

# 4. 台指結算/收盤價
fut_rows = get_finmind("TaiwanFuturesDaily", "TX")
if fut_rows:
    reg = [x for x in fut_rows if x.get("trading_session") == "position"]
    dates = sorted(list(set(x["date"] for x in reg)))
    if len(dates) >= 2:
        c_main = max([x for x in reg if x["date"] == dates[-1]], key=lambda x: safe_float(x.get("volume"), 0))
        p_main = max([x for x in reg if x["date"] == dates[-2]], key=lambda x: safe_float(x.get("volume"), 0))
        data["台指結算"] = {"value": int(safe_float(c_main.get("close"), 0)), "prev": int(safe_float(p_main.get("close"), 0))}

# 5. 外資台指期未平倉
fut_inst = get_finmind("TaiwanFuturesInstitutionalInvestors", "TX")
if fut_inst:
    f_list = [x for x in fut_inst if "外資" in x.get("institutional_investors", "")]
    if len(f_list) >= 2:
        data["外資台指期未平倉"] = {
            "value": int(safe_float(f_list[-1].get("long_open_interest_balance_volume"), 0) - safe_float(f_list[-1].get("short_open_interest_balance_volume"), 0)),
            "prev": int(safe_float(f_list[-2].get("long_open_interest_balance_volume"), 0) - safe_float(f_list[-2].get("short_open_interest_balance_volume"), 0))
        }

# 6. 五大、十大特定法人淨額(口)
top_rows = get_finmind("TaiwanFuturesOpenInterestLargeTraders", "TX")
if top_rows:
    all_contract = [x for x in top_rows if "999999" in str(x.get("contract_date", "")) or "所有" in str(x.get("contract_date", ""))]
    target_row = all_contract[-1] if all_contract else top_rows[-1]
    t5 = int(safe_float(target_row.get("top5_specific_buy_open_interest"), 0) - safe_float(target_row.get("top5_specific_sell_open_interest"), 0))
    t10 = int(safe_float(target_row.get("top10_specific_buy_open_interest"), 0) - safe_float(target_row.get("top10_specific_sell_open_interest"), 0))
    data["五大淨額(口)"] = {"value": t5}
    data["十大淨額(口)"] = {"value": t10}

# 7. 小台與微台散戶多空比(%)
for code, key_name in [("MTX", "小台散戶多空比(%)"), ("TMF", "微台散戶多空比(%)")]:
    f_all = get_finmind("TaiwanFuturesDaily", code)
    i_all = get_finmind("TaiwanFuturesInstitutionalInvestors", code)
    if f_all and i_all:
        last_d = f_all[-1]["date"]
        tot_oi = sum(safe_float(x.get("open_interest"), 0) for x in f_all if x["date"] == last_d and x.get("trading_session") == "position")
        inst_net = sum(safe_float(x.get("long_open_interest_balance_volume"), 0) - safe_float(x.get("short_open_interest_balance_volume"), 0) for x in i_all if x["date"] == last_d)
        if tot_oi > 0:
            data[key_name] = {"value": round((-inst_net / tot_oi) * 100, 2)}

# 8. P/C未平倉比 & 外資選擇權未平倉淨額(萬)
opt_daily = get_finmind("TaiwanOptionDaily", "TXO")
if opt_daily:
    last_d = opt_daily[-1]["date"]
    day_opt = [x for x in opt_daily if x["date"] == last_d and x.get("trading_session") == "position"]
    put_oi = sum(safe_float(x.get("open_interest"), 0) for x in day_opt if x.get("call_put") == "put")
    call_oi = sum(safe_float(x.get("open_interest"), 0) for x in day_opt if x.get("call_put") == "call")
    if call_oi > 0:
        data["P/C未平倉比"] = {"value": f"{round((put_oi / call_oi) * 100, 2)}%"}

opt_inst = get_finmind("TaiwanOptionInstitutionalInvestors", "TXO")
if opt_inst:
    last_d = opt_inst[-1]["date"]
    f_opt = [x for x in opt_inst if x["date"] == last_d and "外資" in x.get("institutional_investors", "")]
    if f_opt:
        net_amt = sum(safe_float(x.get("long_open_interest_balance_amount"), 0) - safe_float(x.get("short_open_interest_balance_amount"), 0) for x in f_opt)
        data["外資選擇權未平倉淨額(萬)"] = {"value": round(net_amt / 10000, 0)}

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

print("✅ 全部更新完成！時間:", now_str)
