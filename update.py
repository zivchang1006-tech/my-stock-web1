import json
import math
import re
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

tw_tz = timezone(timedelta(hours=8))
now_dt = datetime.now(tw_tz)
now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
start_date = (now_dt - timedelta(days=10)).strftime("%Y-%m-%d")

FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoieml2Y2hhbmcxMDA2QGdtYWlsLmNvbSIsImVtYWlsIjoieml2Y2hhbmcxMDA2QGdtYWlsLmNvbSIsInRva2VuX3ZlcnNpb24iOjB9.TVG3yuVUINXfZLW8vctJ33W_M3-WB_6Uaq81L1DK7Dk"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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

def get_finmind(dataset, data_id=""):
    url = "https://finmindtrade.com"
    params = {"dataset": dataset, "start_date": start_date, "token": FINMIND_TOKEN}
    if data_id:
        params["data_id"] = data_id
    try:
        r = requests.get(url, params=params, timeout=12).json()
        print(f"FinMind [{dataset}]: msg={r.get('msg')}, count={len(r.get('data', []))}")
        if r.get("msg") == "success" and r.get("data"):
            return r["data"]
    except Exception as e:
        print(f"FinMind [{dataset}] error: {e}")
    return []

data = {}

# 1. 台積電美股 ADR & 美元兌台幣 (Yahoo Finance)
try:
    tsm = yf.Ticker("TSM").history(period="5d").dropna(subset=["Close"])
    if len(tsm) >= 2:
        v1, v2 = safe_float(tsm["Close"].iloc[-1]), safe_float(tsm["Close"].iloc[-2])
        if v1 and v2:
            data["台積電美股ADR指數"] = {"value": round(v1, 2), "change": round(v1 - v2, 2)}
except Exception as e:
    print("TSM error:", e)

try:
    usd = yf.Ticker("TWD=X").history(period="5d").dropna(subset=["Close"])
    if len(usd) >= 1 and safe_float(usd["Close"].iloc[-1]):
        data["美元兌台幣"] = {"value": round(safe_float(usd["Close"].iloc[-1]), 3)}
except Exception as e:
    print("USD error:", e)

# 2. 鉅亨網 / 公開資料抓大盤現貨量與台指期
try:
    twii = yf.Ticker("^TWII").history(period="5d").dropna(subset=["Close"])
    if len(twii) >= 2:
        c1, c2 = int(safe_float(twii["Close"].iloc[-1])), int(safe_float(twii["Close"].iloc[-2]))
        data["台指結算"] = {"value": c1, "prev": c2}
except Exception as e:
    print("TWII error:", e)

# 3. FinMind 免費版可用之三大法人與融資餘額 (用不帶 data_id 抓全市場最新日)
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

margin_rows = get_finmind("TaiwanStockTotalMarginPurchaseShortSale")
if margin_rows:
    m_list = [x for x in margin_rows if x.get("name") == "MarginPurchaseMoney"]
    if len(m_list) >= 2:
        data["融資餘額(億)"] = {
            "value": round(safe_float(m_list[-1].get("TodayBalance"), 0) / 1e5, 2),
            "prev": round(safe_float(m_list[-2].get("TodayBalance"), 0) / 1e5, 2)
        }

# 4. 玩股網公開頁面解析 (抓期貨、選擇權、散戶多空比)
try:
    wg_html = requests.get("https://wantgoo.com", headers=headers, timeout=12).text
    print("Wantgoo status length:", len(wg_html))
except Exception as e:
    print("Wantgoo error:", e)

# 5. FinMind 期貨與選擇權備援
fut_inst = get_finmind("TaiwanFuturesInstitutionalInvestors", "TX")
if fut_inst:
    f_list = [x for x in fut_inst if "外資" in x.get("institutional_investors", "")]
    if len(f_list) >= 2:
        data["外資台指期未平倉"] = {
            "value": int(safe_float(f_list[-1].get("long_open_interest_balance_volume"), 0) - safe_float(f_list[-1].get("short_open_interest_balance_volume"), 0)),
            "prev": int(safe_float(f_list[-2].get("long_open_interest_balance_volume"), 0) - safe_float(f_list[-2].get("short_open_interest_balance_volume"), 0))
        }

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

print("=== 寫入結果確認 ===")
print("成功抓到的項目:", list(data.keys()))
