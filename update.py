Python
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DATA_FILE = "data.json"

# 15 個指定鍵值的預設結構
DEFAULT_DATA = {
    "台指結算": {"value": None, "prev": None},
    "現貨量(億)": {"value": None},
    "融資餘額(億)": {"value": None, "prev": None},
    "美元兌台幣": {"value": None},
    "外資現貨(億)": {"value": None},
    "投信現貨(億)": {"value": None},
    "自營商現貨(億)": {"value": None},
    "外資台指期未平倉": {"value": None, "prev": None},
    "五大淨額(口)": {"value": None},
    "十大淨額(口)": {"value": None},
    "P/C未平倉比": {"value": None},
    "外資選擇權未平倉淨額(萬)": {"value": None},
    "小台散戶多空比(%)": {"value": None},
    "微台散戶多空比(%)": {"value": None},
    "台積電美股ADR指數": {"value": None, "change": None},
}

DEFAULT_STATUS = {
    field: {"last_updated": None, "state": "⚠️ 尚未初始化"}
    for field in DEFAULT_DATA.keys()
}


def get_current_tw_time():
  """取得當前台灣時間字串"""
  try:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
  except Exception:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_current_tw_date():
  """取得當前台灣日期字串 (YYYY-MM-DD)"""
  try:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
  except Exception:
    return datetime.now().strftime("%Y-%m-%d")


def load_existing_data():
  """讀取舊的 data.json，若不存在或毀損則回傳預設結構"""
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        content = json.load(f)
        return (
            content.get("trading_date", get_current_tw_date()),
            content.get("data", DEFAULT_DATA),
            content.get("status", DEFAULT_STATUS),
        )
    except Exception as e:
      print(f"⚠️ 讀取舊 data.json 失敗: {e}，將使用預設結構初始化。")
  return get_current_tw_date(), DEFAULT_DATA, DEFAULT_STATUS


def is_valid_number(val):
  """驗證數值是否為合理的數字格式（非 None、非空字串，且可轉為 float）"""
  if val is None:
    return False
  if isinstance(val, (int, float)):
    return True
  if isinstance(val, str):
    val_clean = val.strip().replace(",", "").replace("%", "")
    if not val_clean:
      return False
    try:
      float(val_clean)
      return True
    except ValueError:
      return False
  return False


def save_data(trading_date, data_dict, status_dict):
  """儲存結構化的 JSON 檔案"""
  output = {
      "update_time": get_current_tw_time(),
      "trading_date": trading_date,
      "data": data_dict,
      "status": status_dict,
  }
  with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=4)


def print_validation_report(status_dict, data_dict):
  """在終端機印出 15 項數據的檢查清單報告"""
  print("\n" + "=" * 65)
  print(f"📊 玩股網盤後數據抓取與驗證報告 ({get_current_tw_time()})")
  print("=" * 65)
  print(f"{'欄位名稱':<16} | {'狀態':<10} | {'最新數值 (Value)':<12} | {'最後更新時間'}")
  print("-" * 65)

  for field, info in status_dict.items():
    state = info.get("state", "未知")
    last_up = info.get("last_updated", "無記錄")

    # 取得目前數值顯示
    val_info = data_dict.get(field, {})
    if isinstance(val_info, dict):
      val = val_info.get("value")
      if field == "台積電美股ADR指數":
        chg = val_info.get("change")
        val_str = f"{val} ({chg})" if val is not None else "None"
      else:
        val_str = str(val) if val is not None else "None"
    else:
      val_str = str(val_info)

    print(f"{field:<16} | {state:<10} | {val_str:<16} | {last_up}")
  print("=" * 65 + "\n")


def process_field_update(
    field_name,
    new_val,
    old_data,
    new_data,
    status_dict,
    is_new_trading_day,
    has_triple_prev=False,
):
  """處理單一欄位的智慧增量更新與防洗掉邏輯"""
  current_time = get_current_tw_time()

  # 1. 驗證新抓到的數值是否合法
  if is_valid_number(new_val):
    # 清理數值格式（轉型標準化）
    if isinstance(new_val, str):
      new_val_clean = new_val.strip().replace(",", "")
      try:
        new_val = (
            int(new_val_clean)
            if "." not in new_val_clean
            else float(new_val_clean)
        )
      except ValueError:
        pass

    old_val = old_data.get(field_name, {}).get("value")

    if has_triple_prev:
      # 規則 2: 只有當偵測到「交易日期跨入新的一天」且「數值有變動/抓到新收盤數據」時才更新 prev
      if is_new_trading_day and new_val != old_val:
        new_data[field_name]["prev"] = old_val
        print(
            f"🔄 [{field_name}] 跨日更新：舊值 {old_val} 已成功推進存入 prev。"
        )
      else:
        # 同一天內的每小時抓取或數值無變動，保持原本的 prev 不變
        new_data[field_name]["prev"] = old_data.get(field_name, {}).get("prev")

    # 更新當前 value
    new_data[field_name]["value"] = new_val

    # 更新狀態為正常
    status_dict[field_name] = {
        "last_updated": current_time,
        "state": "✅ 正常",
    }
  else:
    # 規則 1: 抓不到新數字或驗證失敗（如假日休市、網站維護），完整保留舊數值與狀態
    new_data[field_name] = old_data.get(field_name, new_data[field_name])
    old_status = status_dict.get(field_name, {}).get(
        "state", "⚠️ 沿用舊資料"
    )
    status_dict[field_name] = {
        "last_updated": status_dict.get(field_name, {}).get(
            "last_updated", "無記錄"
        ),
        "state": "⚠️ 沿用舊資料",
    }
    print(
        f"🛡️ [{field_name}] 抓取值無效或未開盤，已啟動防護：保留舊數值"
        f" ({new_data[field_name].get('value')})"
    )


def scrape_wantgoo():
  stored_date, old_data, status_dict = load_existing_data()
  new_data = json.loads(
      json.dumps(old_data)
  )  # 深拷貝一份舊資料作為預設保留基底

  today_date = get_current_tw_date()
  # 判定是否為新的一天（若系統日期大於檔案記錄的日期，代表跨日）
  is_new_trading_day = today_date > stored_date
  if is_new_trading_day:
    print(
        f"📅 偵測到跨入新交易日 ({today_date})，將準備更新前日基準 (prev)..."
    )
    active_date = today_date
  else:
    active_date = stored_date

  with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()

    try:
      print("🌐 正在連線至玩股網 (台股大盤頁面)...")
      page.goto("https://www.wantgoo.com/stock", timeout=60000)
      page.wait_for_load_state("domcontentloaded")
      soup_stock = BeautifulSoup(page.content(), "html.parser")

      print("🌐 正在連線至玩股網 (期貨選擇權籌碼頁面)...")
      page.goto("https://www.wantgoo.com/futures", timeout=60000)
      page.wait_for_load_state("domcontentloaded")
      soup_futures = BeautifulSoup(page.content(), "html.parser")

      # --- 💡 實際抓取數值字典 (請根據您實際的 CSS Selector 填入解析邏輯) ---
      scraped_values = {
          "台指結算": None,
          "現貨量(億)": None,
          "融資餘額(億)": None,
          "美元兌台幣": None,
          "外資現貨(億)": None,
          "投信現貨(億)": None,
          "自營商現貨(億)": None,
          "外資台指期未平倉": None,
          "五大淨額(口)": None,
          "十大淨額(口)": None,
          "P/C未平倉比": None,
          "外資選擇權未平倉淨額(萬)": None,
          "小台散戶多空比(%)": None,
          "微台散戶多空比(%)": None,
          "台積電美股ADR指數": None,
          "台積電美股ADR漲跌": None,
      }

      # 範例選擇器套用提示：
      # stock_qty = soup_stock.select_one('.your-selector')
      # if stock_qty: scraped_values["現貨量(億)"] = stock_qty.text

      # 依序執行 15 個欄位的驗證與寫入
      triple_fields = ["台指結算", "融資餘額(億)", "外資台指期未平倉"]

      for key in DEFAULT_DATA.keys():
        if key == "台積電美股ADR指數":
          val = scraped_values.get("台積電美股ADR指數")
          chg = scraped_values.get("台積電美股ADR漲跌")
          if is_valid_number(val):
            new_data[key]["value"] = val
            if chg is not None:
              new_data[key]["change"] = chg
            status_dict[key] = {
                "last_updated": get_current_tw_time(),
                "state": "✅ 正常",
            }
          else:
            status_dict[key]["state"] = "⚠️ 沿用舊資料"
        else:
          has_prev = key in triple_fields
          new_val = scraped_values.get(key)
          process_field_update(
              key,
              new_val,
              old_data,
              new_data,
              status_dict,
              is_new_trading_day,
              has_triple_prev=has_prev,
          )

    except Exception as e:
      print(f"❌ 爬取過程中發生例外錯誤: {e}，全面啟動防護保留舊資料。")
    finally:
      browser.close()

  # 儲存結果並印出報告
  save_data(active_date, new_data, status_dict)
  print_validation_report(status_dict, new_data)


if __name__ == "__main__":
  print("=== 開始執行玩股網每小時智慧補齊任務 ===")
  scrape_wantgoo()