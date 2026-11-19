#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""台股每日盤後籌碼更新器
資料來源：TWSE、TAIFEX、Yahoo Finance
輸出：data.json（最新一日）、history.json（以日期為 key 的每日歷史物件）

重要：不把抓取失敗的欄位補成 0；失敗時存成 "--"，並把原因寫入 errors。
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Callable

import pandas as pd
import requests

try:
    import yfinance as yf
except Exception:
    yf = None

TZ = ZoneInfo("Asia/Taipei")
ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data.json"
HISTORY_FILE = ROOT / "history.json"

# 使用者要求回補的日期。成功回補後仍保留這三天，重跑時會重新核對官方資料。
BOOTSTRAP_DATES = ["2026-11-16", "2026-11-17", "2026-11-18"]

# 今日資料至少 17:00 才抓，GitHub Actions 設定在台灣時間 17:15 執行。
PUBLISH_TIME = dtime(17, 0)
RECENT_LOOKBACK_DAYS = 7

TWSE = "https://www.twse.com.tw/rwd/zh"
TAIFEX = "https://www.taifex.com.tw/cht/3"

URL_FUT_INST = f"{TAIFEX}/futContractsDateDown"
URL_FUT_DAILY = f"{TAIFEX}/futDataDown"
URL_LARGE_TRADER = f"{TAIFEX}/largeTraderFutDown"
URL_OPT_INST = f"{TAIFEX}/optContractsDateDown"
URL_PC_RATIO = f"{TAIFEX}/pcRatioDown"

ALL_KEYS = [
    "台指結算", "現貨量(億)", "融資餘額(億)", "美元兌台幣",
    "外資現貨(億)", "投信現貨(億)", "自營商現貨(億)",
    "外資台指期未平倉", "五大淨額(口)", "十大淨額(口)",
    "P/C未平倉比", "外資選擇權未平倉淨額(萬)",
    "小台散戶多空比(%)", "微台散戶多空比(%)", "台積電美股ADR指數",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.taifex.com.tw/cht/3/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ---------- 共用工具 ----------

def now_taipei() -> datetime:
    return datetime.now(TZ)


def date_slash(day: str) -> str:
    return datetime.strptime(day, "%Y-%m-%d").strftime("%Y/%m/%d")


def ymd(day: str) -> str:
    return day.replace("-", "")


def parse_number(value: Any) -> float | None:
    """把數值轉成 float；空白、--、NaN 一律回傳 None，不偽裝成 0。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    s = str(value).strip().replace(",", "").replace("％", "%")
    s = s.replace("%", "").replace("+", "")
    if not s or s.lower() in {"nan", "none", "null", "--", "-", "n/a"}:
        return None
    try:
        n = float(s)
        return None if (math.isnan(n) or math.isinf(n)) else n
    except (TypeError, ValueError):
        return None


def roc_date_to_iso(value: Any) -> str | None:
    """民國日期 115/11/18 或西元日期轉 YYYY-MM-DD。"""
    s = str(value).strip().replace("-", "/")
    m = re.search(r"(\d{2,4})/(\d{1,2})/(\d{1,2})", s)
    if not m:
        return None
    yy, mm, dd = map(int, m.groups())
    if yy < 1911:
        yy += 1911
    try:
        return date(yy, mm, dd).isoformat()
    except ValueError:
        return None


def norm_text(value: Any) -> str:
    return re.sub(r"[\s\u3000_()（）％%：:、,，]+", "", str(value or "")).strip().lower()


def find_col(df: pd.DataFrame, *, contains: tuple[str, ...], excludes: tuple[str, ...] = ()) -> str:
    """以欄名關鍵字找欄位，避免依賴 c[11]、c[14] 等易變的位置。"""
    # 正規化後的空字串不能當排除條件；例如「%」會被正規化成空字串，
    # 若不過濾，空字串會被視為所有欄名都包含它，造成全部欄位都找不到。
    wanted = [token for x in contains if (token := norm_text(x))]
    unwanted = [token for x in excludes if (token := norm_text(x))]
    for col in df.columns:
        name = norm_text(col)
        if all(token in name for token in wanted) and not any(token in name for token in unwanted):
            return str(col)
    raise ValueError(
        f"找不到欄位，關鍵字={contains}；目前欄位={list(map(str, df.columns))}"
    )


def find_col_optional(df: pd.DataFrame, *, contains: tuple[str, ...], excludes: tuple[str, ...] = ()) -> str | None:
    try:
        return find_col(df, contains=contains, excludes=excludes)
    except ValueError:
        return None


def series_numbers(series: pd.Series) -> pd.Series:
    return series.map(parse_number)


def request_get_json(url: str, params: dict[str, Any], timeout: int = 25) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = SESSION.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"TWSE 回傳格式不是 JSON 物件：{url}")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 + attempt * 2)
    raise RuntimeError(f"GET 失敗：{url}；原因：{last_error}")


def request_post_csv(url: str, form: dict[str, Any], timeout: int = 35) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = SESSION.post(url, data=form, timeout=timeout)
            response.raise_for_status()
            # TAIFEX CSV 為 MS950/CP950；解碼失敗時保留替代字元並在欄名檢查時報錯。
            text = response.content.decode("ms950", errors="replace").replace("\ufeff", "")
            if not text.strip():
                raise ValueError("下載回傳空白內容")
            df = pd.read_csv(io.StringIO(text), dtype=str, index_col=False)
            df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
            df = df.dropna(how="all").reset_index(drop=True)
            if df.empty:
                raise ValueError("CSV 沒有資料列")
            return df
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 + attempt * 2)
    raise RuntimeError(f"TAIFEX CSV 下載失敗：{url}；原因：{last_error}")


def taifex_form(day: str) -> dict[str, str]:
    return {"queryStartDate": date_slash(day), "queryEndDate": date_slash(day)}


def value_entry(value: Any) -> dict[str, Any]:
    if value is None:
        return {"value": "--"}
    if isinstance(value, float):
        if not math.isfinite(value):
            return {"value": "--"}
        value = round(value, 2)
    return {"value": value}


# ---------- TWSE：成交量、融資、三大法人現貨 ----------

_FMTQIK_CACHE: dict[str, dict[str, float]] = {}


def fetch_month_volume_map(day: str) -> dict[str, float]:
    month_key = day[:7]
    if month_key in _FMTQIK_CACHE:
        return _FMTQIK_CACHE[month_key]

    first_day = day[:7].replace("-", "") + "01"
    payload = request_get_json(
        f"{TWSE}/afterTrading/FMTQIK",
        {"response": "json", "date": first_day},
    )
    if payload.get("stat") not in ("OK", "很抱歉，沒有符合條件的資料!") and not payload.get("data"):
        raise RuntimeError(f"FMTQIK 沒有回傳有效資料：{payload.get('stat')}")

    out: dict[str, float] = {}
    for row in payload.get("data", []):
        if len(row) < 3:
            continue
        key = roc_date_to_iso(row[0])
        amount = parse_number(row[2])
        if key and amount is not None:
            out[key] = round(amount / 1e8, 2)
    if not out:
        raise RuntimeError("FMTQIK 回傳資料但無法辨識日期／成交金額欄")
    _FMTQIK_CACHE[month_key] = out
    return out


def fetch_twse_funds(day: str) -> dict[str, float]:
    payload = request_get_json(
        f"{TWSE}/fund/BFI82U",
        {"response": "json", "dayDate": ymd(day)},
    )
    if payload.get("stat") != "OK":
        raise RuntimeError(f"BFI82U 查詢失敗：{payload.get('stat')}")

    result: dict[str, float] = {}
    for row in payload.get("data", []):
        if len(row) < 4:
            continue
        name = str(row[0]).strip()
        diff = parse_number(row[3])
        if diff is None:
            continue
        diff_100m = round(diff / 1e8, 2)
        if name == "自營商(自行買賣)":
            result["自營商現貨(億)"] = diff_100m
        elif "投信" in name:
            result["投信現貨(億)"] = diff_100m
        elif "外資及陸資" in name:
            result["外資現貨(億)"] = diff_100m

    if len(result) < 3:
        raise RuntimeError(f"BFI82U 三大法人資料不完整：已取得 {list(result.keys())}")
    return result


def fetch_twse_margin(day: str) -> float:
    payload = request_get_json(
        f"{TWSE}/marginTrading/MI_MARGN",
        {"response": "json", "date": ymd(day)},
    )
    if payload.get("stat") != "OK":
        raise RuntimeError(f"MI_MARGN 查詢失敗：{payload.get('stat')}")

    for table in payload.get("tables", []):
        for row in table.get("data", []):
            if row and "融資金額" in str(row[0]) and len(row) > 5:
                current = parse_number(row[5])
                if current is not None:
                    # TWSE 欄位單位為仟元；換算億元需除以 100,000。
                    return round(current / 1e5, 2)
    raise RuntimeError("MI_MARGN 找不到『融資金額』的今日餘額")


# ---------- TAIFEX：法人期貨未平倉、全市場 OI、台指結算 ----------

PRODUCT_NAME = {
    "TX": ("臺股期貨", "台股期貨"),
    "MTX": ("小型臺指期貨", "小型台指期貨"),
    "TMF": ("微型臺指期貨", "微型台指期貨"),
}


def product_mask(series: pd.Series, product: str) -> pd.Series:
    s = series.fillna("").astype(str)
    if product == "TX":
        # 排除小台、微台，避免「臺股期貨」相似名稱誤抓。
        return s.map(lambda x: ("臺股期貨" in x or "台股期貨" in x) and "小型" not in x and "微型" not in x)
    return s.map(lambda x: any(word in x for word in PRODUCT_NAME[product]))


def fetch_fut_institution_df(day: str) -> pd.DataFrame:
    return request_post_csv(URL_FUT_INST, taifex_form(day) | {"commodityId": ""})


def fetch_future_daily_df(day: str, product: str) -> pd.DataFrame:
    form = {
        "down_type": "1",
        "commodity_id": product,
        "queryStartDate": date_slash(day),
        "queryEndDate": date_slash(day),
        "MarketCode": "0",
    }
    return request_post_csv(URL_FUT_DAILY, form)


def get_inst_oi_columns(df: pd.DataFrame) -> tuple[str, str, str, str]:
    name_col = find_col(df, contains=("商品名稱",)) if find_col_optional(df, contains=("商品名稱",)) else find_col(df, contains=("契約名稱",))
    role_col = find_col_optional(df, contains=("身份別",)) or find_col_optional(df, contains=("身分別",))
    if role_col is None:
        role_col = find_col(df, contains=("交易人類別",))
    long_col = (
        find_col_optional(df, contains=("多方未平倉", "口數"))
        or find_col_optional(df, contains=("買方未平倉", "口數"))
    )
    short_col = (
        find_col_optional(df, contains=("空方未平倉", "口數"))
        or find_col_optional(df, contains=("賣方未平倉", "口數"))
    )
    if not all((name_col, role_col, long_col, short_col)):
        raise ValueError(f"期貨法人 CSV 欄位不完整：{list(df.columns)}")
    return name_col, role_col, long_col, short_col


def fetch_institution_position_data(day: str) -> tuple[int, dict[str, float]]:
    """回傳外資 TX 淨未平倉，以及三大法人在 MTX/TMF 的合計淨未平倉。"""
    df = fetch_fut_institution_df(day)
    name_col, role_col, long_col, short_col = get_inst_oi_columns(df)
    names = df[name_col].fillna("").astype(str)
    roles = df[role_col].fillna("").astype(str)

    foreign_tx = df[product_mask(names, "TX") & roles.str.contains("外資", na=False)]
    if foreign_tx.empty:
        raise RuntimeError("TAIFEX 法人期貨 CSV 找不到『臺股期貨／外資』資料")

    f_long = series_numbers(foreign_tx[long_col]).sum(min_count=1)
    f_short = series_numbers(foreign_tx[short_col]).sum(min_count=1)
    if pd.isna(f_long) or pd.isna(f_short):
        raise RuntimeError("外資 TX 未平倉多／空欄位無有效數值")
    foreign_tx_net = int(round(float(f_long - f_short)))

    result: dict[str, float] = {}
    for product, label in (("MTX", "小台"), ("TMF", "微台")):
        sub = df[product_mask(names, product) & roles.str.contains("外資|投信|自營", na=False)]
        if sub.empty:
            raise RuntimeError(f"TAIFEX 法人期貨 CSV 找不到 {label} 的三大法人資料")
        long_sum = series_numbers(sub[long_col]).sum(min_count=1)
        short_sum = series_numbers(sub[short_col]).sum(min_count=1)
        if pd.isna(long_sum) or pd.isna(short_sum):
            raise RuntimeError(f"{label} 三大法人未平倉資料含空值")
        result[label] = float(long_sum - short_sum)

    return foreign_tx_net, result


def get_daily_market_oi_and_settlement(df: pd.DataFrame, product: str) -> tuple[int, float | None]:
    """從期貨每日行情 CSV 加總 OI；TX 另外取最近月契約結算價。"""
    contract_col = find_col_optional(df, contains=("契約",))
    if contract_col is None:
        contract_col = find_col(df, contains=("商品代號",))
    month_col = find_col(df, contains=("到期月份",))
    oi_col = find_col(df, contains=("未沖銷契約數",))
    session_col = find_col_optional(df, contains=("交易時段",))

    sub = df[df[contract_col].fillna("").astype(str).str.strip().eq(product)].copy()
    if sub.empty:
        raise RuntimeError(f"{product} 期貨每日行情沒有資料")
    if session_col:
        regular = sub[session_col].fillna("").astype(str).str.strip().eq("一般")
        if regular.any():
            sub = sub[regular].copy()
    sub["_month"] = sub[month_col].fillna("").astype(str).str.strip()
    # 排除價差單；保留月契約及週契約，作為全市場 OI 分母。
    valid_oi = sub[~sub["_month"].str.contains("/", na=False)]
    oi_values = series_numbers(valid_oi[oi_col])
    total_oi = oi_values.sum(min_count=1)
    if pd.isna(total_oi) or total_oi <= 0:
        raise RuntimeError(f"{product} 全市場未平倉量無有效值")

    settlement: float | None = None
    if product == "TX":
        settle_col = find_col_optional(df, contains=("結算價",))
        if settle_col is None:
            raise RuntimeError("TX 期貨每日行情找不到『結算價』欄位")
        month_only = valid_oi[~valid_oi["_month"].str.upper().str.contains("W", na=False)].copy()
        # 優先使用 YYYYMM 月契約，排除小計與非月份列。
        month_only = month_only[month_only["_month"].str.match(r"^\d{6}$", na=False)]
        month_only = month_only.sort_values("_month")
        if month_only.empty:
            raise RuntimeError("TX 找不到近月月契約，無法取得結算價")
        settlement = parse_number(month_only.iloc[0][settle_col])
        if settlement is None:
            raise RuntimeError("TX 近月月契約結算價欄位不是有效數字")

    return int(round(float(total_oi))), settlement


def fetch_large_trader_net(day: str) -> tuple[int, int]:
    """大額交易人：只取 TX、所有契約、一般統計；按欄名找買賣口數。"""
    df = request_post_csv(
        URL_LARGE_TRADER,
        taifex_form(day) | {"doQuery": "1"},
    )

    contract_col = find_col_optional(df, contains=("契約",))
    if contract_col is None:
        contract_col = find_col(df, contains=("商品代號",))
    expiry_col = find_col(df, contains=("到期月份",))

    def find_position_col(rank: str, side: str) -> str:
        # 不取百分比欄，避免把百分比當成口數。
        candidate = find_col_optional(
            df,
            contains=(rank, side),
            excludes=("比率", "百分比", "百分率"),
        )
        if candidate is None:
            raise ValueError(f"大額交易人 CSV 找不到 {rank}{side}數量欄；欄位={list(df.columns)}")
        return candidate

    b5_col = find_position_col("前五大", "買方")
    s5_col = find_position_col("前五大", "賣方")
    b10_col = find_position_col("前十大", "買方")
    s10_col = find_position_col("前十大", "賣方")

    sub = df[df[contract_col].fillna("").astype(str).str.strip().str.upper().eq("TX")].copy()
    expiry = sub[expiry_col].fillna("").astype(str).str.strip()
    all_contracts = expiry.str.contains("所有|全部|999999|ALL", case=False, regex=True, na=False)
    sub = sub[all_contracts].copy()
    if sub.empty:
        raise RuntimeError(
            "大額交易人 CSV 找不到 TX『所有契約／999999』彙總列；"
            "程式不會改用各月份相加，以免重複計算。"
        )

    # 若 CSV 同時提供「一般」與「特定法人」統計，取一般（整體前五／前十名）。
    class_col = find_col_optional(df, contains=("交易人類別",))
    if class_col:
        class_values = sub[class_col].fillna("").astype(str).str.strip()
        general = class_values.str.contains("一般|所有|全部|整體", case=False, regex=True, na=False)
        if general.any():
            sub = sub[general].copy()
        elif class_values.nunique() > 1:
            raise RuntimeError(f"大額交易人 CSV 的交易人類別無法判斷：{class_values.unique().tolist()}")

    if len(sub) > 1:
        # 有些下載版本會把相同彙總列分為不同市場類別；若欄位完全重複只留一筆，否則拒絕猜測。
        compare_cols = [b5_col, s5_col, b10_col, s10_col]
        if len(sub[compare_cols].drop_duplicates()) == 1:
            sub = sub.iloc[[0]]
        else:
            raise RuntimeError(f"TX 所有契約彙總列不只一筆且數值不同：{sub[compare_cols].to_dict('records')}")

    row = sub.iloc[0]
    vals = [parse_number(row[c]) for c in (b5_col, s5_col, b10_col, s10_col)]
    if any(v is None for v in vals):
        raise RuntimeError("大額交易人買／賣口數欄位有空值")
    b5, s5, b10, s10 = vals
    return int(round(b5 - s5)), int(round(b10 - s10))


# ---------- TAIFEX：P/C、外資選擇權未平倉金額 ----------

def fetch_pc_oi_ratio(day: str) -> float:
    df = request_post_csv(URL_PC_RATIO, taifex_form(day))
    col = find_col(df, contains=("未平倉量比率",))
    value = parse_number(df.iloc[0][col])
    if value is None:
        raise RuntimeError("P/C 未平倉比欄位沒有數值")
    return round(value, 2)


def fetch_foreign_option_net_amount_wan(day: str) -> int:
    """取臺指選擇權外資「多空未平倉契約金額」，原始單位千元，換算萬元。"""
    df = request_post_csv(URL_OPT_INST, taifex_form(day))
    name_col = find_col_optional(df, contains=("商品名稱",)) or find_col(df, contains=("契約名稱",))
    role_col = find_col_optional(df, contains=("身份別",)) or find_col_optional(df, contains=("身分別",))
    if role_col is None:
        role_col = find_col(df, contains=("交易人類別",))

    # optContractsDateDown 的多空淨額契約金額，直接是多方未平倉金額減空方未平倉金額。
    net_amt_col = (
        find_col_optional(df, contains=("多空未平倉", "契約金額"))
        or find_col_optional(df, contains=("未平倉淨額", "契約金額"))
    )
    if net_amt_col is None:
        raise ValueError(f"選擇權法人 CSV 找不到『多空未平倉契約金額』欄位；欄位={list(df.columns)}")

    sub = df[
        df[name_col].fillna("").astype(str).str.contains("臺指選擇權|台指選擇權", regex=True, na=False)
        & df[role_col].fillna("").astype(str).str.contains("外資", na=False)
    ].copy()
    if sub.empty:
        raise RuntimeError("選擇權法人 CSV 找不到『臺指選擇權／外資』資料")

    amounts = series_numbers(sub[net_amt_col]).dropna()
    if amounts.empty:
        raise RuntimeError("外資臺指選擇權未平倉淨額契約金額沒有有效數值")
    # 期交所金額單位為千元；1 萬元 = 10 千元。若同日同商品有多筆序列，合計淨額。
    return int(round(float(amounts.sum()) / 10))


# ---------- Yahoo Finance：ADR、美元兌台幣 ----------

def fetch_yahoo_taiwan_date_map(symbol: str, days: int = 45) -> dict[str, float]:
    if yf is None:
        raise RuntimeError("yfinance 尚未安裝")
    hist = yf.Ticker(symbol).history(period=f"{days}d", auto_adjust=False)
    if hist is None or hist.empty or "Close" not in hist:
        raise RuntimeError(f"Yahoo Finance {symbol} 沒有 Close 資料")

    out: dict[str, float] = {}
    for idx, row in hist.iterrows():
        close = parse_number(row.get("Close"))
        if close is None:
            continue
        ts = pd.Timestamp(idx)
        if ts.tzinfo is None:
            # yfinance 通常回傳美東時區；若沒有時區就以美東收盤日期處理。
            ts = ts.tz_localize("America/New_York")
        taipei_day = ts.tz_convert(TZ).date().isoformat()
        out[taipei_day] = float(close)
    return out


def fetch_yahoo_maps() -> tuple[dict[str, float], dict[str, float]]:
    errors: list[str] = []
    try:
        adr = fetch_yahoo_taiwan_date_map("TSM")
    except Exception as exc:
        adr = {}
        errors.append(f"TSM ADR：{exc}")
    try:
        usd = fetch_yahoo_taiwan_date_map("TWD=X")
    except Exception as exc:
        usd = {}
        errors.append(f"USD/TWD：{exc}")
    if errors and not (adr or usd):
        raise RuntimeError("；".join(errors))
    return adr, usd


# ---------- 歷史資料格式與增減值 ----------

def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path.name} JSON 格式錯誤，為避免覆蓋原檔已停止：{exc}")


def normalize_history(raw: Any) -> dict[str, dict[str, Any]]:
    """同時兼容舊 Apps Script 的日期物件，以及 Python 版的陣列格式。"""
    out: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("date"):
                out[str(item["date"])] = item
    elif isinstance(raw, dict):
        for key, item in raw.items():
            if isinstance(item, dict) and isinstance(item.get("data"), dict):
                out[str(item.get("date") or key)] = {
                    "date": str(item.get("date") or key),
                    "update_time": item.get("update_time", ""),
                    "data": item.get("data", {}),
                    **({"errors": item["errors"]} if "errors" in item else {}),
                }
    return out


def number_from_entry(entry: Any) -> float | None:
    if not isinstance(entry, dict):
        return None
    return parse_number(entry.get("value"))


def attach_previous_values(history: dict[str, dict[str, Any]]) -> None:
    prev_keys = ["台指結算", "融資餘額(億)", "外資台指期未平倉"]
    dates = sorted(history)
    for i, day in enumerate(dates):
        data = history[day].setdefault("data", {})
        earlier_values: dict[str, float] = {}
        for prev_day in reversed(dates[:i]):
            prev_data = history[prev_day].get("data", {})
            for key in prev_keys:
                if key not in earlier_values:
                    val = number_from_entry(prev_data.get(key))
                    if val is not None:
                        earlier_values[key] = val
        for key in prev_keys:
            current = data.get(key)
            if isinstance(current, dict) and number_from_entry(current) is not None and key in earlier_values:
                current["prev"] = earlier_values[key]


def choose_target_dates(now: datetime) -> list[str]:
    dates = set(BOOTSTRAP_DATES)
    today = now.date()
    # 回看最近 7 個日曆日，避免某天排程失敗就永遠漏一天。
    for offset in range(1, RECENT_LOOKBACK_DAYS + 1):
        d = today - timedelta(days=offset)
        if d.weekday() < 5:
            dates.add(d.isoformat())
    # 今日盤後資料只在台灣時間 17:00 後納入。
    if today.weekday() < 5 and now.time() >= PUBLISH_TIME:
        dates.add(today.isoformat())
    return sorted(dates)


# ---------- 單日更新 ----------

def fetch_one_day(day: str, yahoo_adr: dict[str, float], yahoo_usd: dict[str, float]) -> dict[str, Any]:
    data: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    def capture(key: str, fn: Callable[[], Any], formatter: Callable[[Any], Any] | None = None) -> None:
        try:
            result = fn()
            if result is None:
                raise RuntimeError("來源回傳空值")
            if formatter:
                result = formatter(result)
            data[key] = value_entry(result)
        except Exception as exc:
            data[key] = {"value": "--"}
            errors.append(f"{key}: {exc}")

    # 每個商品每日行情只下載一次；TX 用於台指結算，MTX/TMF 用於散戶比率分母。
    future_stats_cache: dict[str, tuple[int, float | None]] = {}

    def get_daily_stats(product: str) -> tuple[int, float | None]:
        if product not in future_stats_cache:
            daily_df = fetch_future_daily_df(day, product)
            future_stats_cache[product] = get_daily_market_oi_and_settlement(daily_df, product)
        return future_stats_cache[product]

    # 1–7：現貨、成交量、融資與匯率
    capture("台指結算", lambda: get_daily_stats("TX")[1], lambda x: int(round(float(x))))
    capture("現貨量(億)", lambda: fetch_month_volume_map(day)[day])
    capture("融資餘額(億)", lambda: fetch_twse_margin(day))

    def assign_funds() -> dict[str, float]:
        result = fetch_twse_funds(day)
        return result

    try:
        fund_data = assign_funds()
        for key in ("外資現貨(億)", "投信現貨(億)", "自營商現貨(億)"):
            data[key] = value_entry(fund_data[key])
    except Exception as exc:
        for key in ("外資現貨(億)", "投信現貨(億)", "自營商現貨(億)"):
            data[key] = {"value": "--"}
        errors.append(f"三大法人現貨: {exc}")

    capture("美元兌台幣", lambda: yahoo_usd.get(day), lambda x: round(float(x), 3))
    capture("台積電美股ADR指數", lambda: yahoo_adr.get(day), lambda x: round(float(x), 2))

    # 8、13、14：同一份法人未平倉 CSV，欄位依中文欄名定位。
    inst_cache: dict[str, Any] = {}

    def get_inst() -> tuple[int, dict[str, float]]:
        if "value" not in inst_cache:
            inst_cache["value"] = fetch_institution_position_data(day)
        return inst_cache["value"]

    capture("外資台指期未平倉", lambda: get_inst()[0])

    # 13、14 的分母為各商品全市場 OI；分子為三大法人淨 OI 的相反數。
    # 這裡的「散戶」是三大法人以外的市場部位估算，不是期交所公布的自然人統計。
    def retail_ratio(product: str, label: str) -> float:
        _, inst_net = get_inst()
        total_oi, _ = get_daily_stats(product)
        ratio = (-inst_net[label] / total_oi) * 100.0
        return round(ratio, 2)

    capture("小台散戶多空比(%)", lambda: retail_ratio("MTX", "小台"))
    capture("微台散戶多空比(%)", lambda: retail_ratio("TMF", "微台"))

    # 9、10：大額交易人前五大／前十大買賣未平倉口數差。
    def large_values() -> tuple[int, int]:
        return fetch_large_trader_net(day)

    large_cache: dict[str, Any] = {}

    def get_large() -> tuple[int, int]:
        if "value" not in large_cache:
            large_cache["value"] = large_values()
        return large_cache["value"]

    capture("五大淨額(口)", lambda: get_large()[0])
    capture("十大淨額(口)", lambda: get_large()[1])

    # 11：臺指選擇權未平倉 Put/Call ratio。
    capture("P/C未平倉比", lambda: fetch_pc_oi_ratio(day), lambda x: f"{float(x):.2f}%")

    # 12：外資 TXO 買方 OI 金額減賣方 OI 金額，千元換算萬元。
    capture("外資選擇權未平倉淨額(萬)", lambda: fetch_foreign_option_net_amount_wan(day))

    # 15：保留欄位完整性。若 Yahoo 對特定日期沒有收盤值，留 --，不沿用前一天數字。
    for key in ALL_KEYS:
        if key not in data:
            data[key] = {"value": "--"}

    return {
        "date": day,
        "update_time": now_taipei().strftime("%Y-%m-%d %H:%M:%S"),
        "data": data,
        "errors": errors,
    }


def count_valid_values(payload: dict[str, Any]) -> int:
    data = payload.get("data", {})
    return sum(1 for key in ALL_KEYS if number_from_entry(data.get(key)) is not None)


def main() -> int:
    now = now_taipei()
    dates = choose_target_dates(now)
    print(f"台灣時間：{now:%Y-%m-%d %H:%M:%S}")
    print(f"本次更新日期：{', '.join(dates)}")
    if now.weekday() < 5 and now.time() < PUBLISH_TIME:
        print("提醒：目前尚未 17:00，今日資料不會抓取；同時移除舊程式留下的今日盤中資料。")

    # 載入歷史。可兼容舊 Apps Script 的日期物件與 Python list；輸出保留原 Apps Script 日期物件格式。
    raw_history = load_json(HISTORY_FILE, {})
    history_map = normalize_history(raw_history)

    # 清除目前交易日尚未完成或可能由舊程式寫入的盤中資料，避免 17:00 前被當成盤後資料。
    today_key = now.date().isoformat()
    if now.weekday() < 5:
        history_map.pop(today_key, None)

    # Yahoo 一次抓取較長區間，日期統一換算成台北日期。
    try:
        yahoo_adr, yahoo_usd = fetch_yahoo_maps()
    except Exception as exc:
        print(f"Yahoo Finance 警告：{exc}")
        yahoo_adr, yahoo_usd = {}, {}

    changed = 0
    for day in dates:
        # 保護機制：未滿 17:00 不允許當日盤後資料進入 history。
        if day == now.date().isoformat() and now.weekday() < 5 and now.time() < PUBLISH_TIME:
            continue
        try:
            payload = fetch_one_day(day, yahoo_adr, yahoo_usd)
        except Exception as exc:
            print(f"{day} 整日更新失敗：{exc}")
            continue

        valid_count = count_valid_values(payload)
        chip_keys = ALL_KEYS[7:14]  # 畫面第 8～14 項：期貨大戶、選擇權與散戶比率
        chip_valid = sum(1 for key in chip_keys if number_from_entry(payload["data"].get(key)) is not None)
        if valid_count < 8 or chip_valid < 5:
            print(
                f"{day} 有效指標 {valid_count}/{len(ALL_KEYS)}；第 8～14 項僅 {chip_valid}/7，"
                "低於安全門檻；不覆蓋歷史資料。"
            )
            print("  錯誤：" + " | ".join(payload.get("errors", [])))
            continue

        history_map[day] = payload
        changed += 1
        print(f"{day} 完成：有效指標 {valid_count}/{len(ALL_KEYS)}；錯誤 {len(payload.get('errors', []))} 項")
        for error in payload.get("errors", []):
            print(f"  - {error}")

    if not history_map:
        print("沒有任何歷史資料可寫入，停止。")
        return 1

    # 以最近可用交易日填入 prev，只作為漲跌比較；不複製前一天的 value。
    attach_previous_values(history_map)
    ordered_dates = sorted(history_map)
    history_object = {day: history_map[day] for day in ordered_dates}
    latest = history_map[ordered_dates[-1]]

    # 沿用原 Apps Script 格式，降低舊前端因 list/object 不一致而讀取失敗的風險。
    # data.json 額外保留 date 欄位，不影響舊版只讀 update_time/data 的前端。
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(latest, file, ensure_ascii=False, indent=2, allow_nan=False)
    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history_object, file, ensure_ascii=False, indent=2, allow_nan=False)

    print(f"更新完成：本次更新 {changed} 日；歷史總天數 {len(history_object)} 天；最新日期 {latest['date']}")
    print(f"已寫入：{DATA_FILE.name}、{HISTORY_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
