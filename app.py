from datetime import datetime, timedelta
import json
import os
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st


# =========================================================
# 基本設定
# =========================================================

st.set_page_config(
    page_title="台股市場共識策略",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("台股強勢策略")

DB_FILE = "industry_db.json"
BUY_TRACK_FILE = "buy_track_db.json"  # 用於持久化收集建議買進的股票清單


# =========================================================
# 族群資料庫與買進追蹤清單管理
# =========================================================

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "2330": "半導體(晶圓代工)",
        "3711": "半導體(封測)",
        "2449": "半導體(封測)",
        "2382": "AI伺服器",
        "3231": "AI伺服器",
        "2356": "AI伺服器",
        "6669": "AI伺服器/矽智財",
        "8105": "硬板",
    }


def save_db(db_data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(
                db_data,
                f,
                ensure_ascii=False,
                indent=4,
            )
    except Exception as e:
        st.error(f"儲存檔案失敗: {e}")


def load_buy_track_db():
    if os.path.exists(BUY_TRACK_FILE):
        try:
            with open(BUY_TRACK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_buy_track_db(track_data):
    try:
        with open(BUY_TRACK_FILE, "w", encoding="utf-8") as f:
            json.dump(
                track_data,
                f,
                ensure_ascii=False,
                indent=4,
            )
    except Exception as e:
        st.error(f"儲存追蹤檔案失敗: {e}")


if "user_industry_map" not in st.session_state:
    st.session_state.user_industry_map = load_db()

if "buy_track_list" not in st.session_state:
    st.session_state.buy_track_list = load_buy_track_db()


# =========================================================
# 搜尋功能
# =========================================================

search_query = st.sidebar.text_input(
    "🔍 側邊欄快速查找台股",
    placeholder="輸入代號或名稱 (例: 2330)",
)


# =========================================================
# 取得 TWSE 資料、歷史成交值與計算連續買超天數
# =========================================================

@st.cache_data(ttl=600)
def fetch_market_data():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.twse.com.tw/zh/trading/fund/T86.html",
        "X-Requested-With": "XMLHttpRequest",
    }

    session = requests.Session()
    session.headers.update(headers)

    curr = datetime.now()
    dates = []

    for i in range(50):
        d_str = curr.strftime("%Y%m%d")
        test_url = (
            "https://www.twse.com.tw/rwd/zh/afterTrading/"
            f"MI_INDEX?response=json&type=ALLBUT0999&date={d_str}"
        )
        try:
            res = session.get(test_url, timeout=4)
            if res.status_code == 200:
                data = res.json()
                if data.get("stat") == "OK" and len(data.get("tables", [])) > 0:
                    dates.append(d_str)
                    if len(dates) >= 35:
                        break
        except Exception:
            pass
        curr -= timedelta(days=1)
        time.sleep(0.03)

    if len(dates) == 0:
        return {}, {}, {}, [], {}, {}, {}

    latest_date = dates[0]
    prev_date = dates[1] if len(dates) > 1 else latest_date

    historical_inst = {}
    for d_str in dates[:10]:
        target_d = d_str
        t_map = {}
        for _ in range(3):
            url = (
                "https://www.twse.com.tw/rwd/zh/fund/"
                f"T86?response=json&date={target_d}&selectType=ALLBUT0999"
            )
            try:
                r = session.get(url, timeout=5)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("stat") == "OK" and "data" in d and len(d["data"]) > 0:
                        for row in d["data"]:
                            if len(row) > 10:
                                code = str(row[0]).strip()
                                name = str(row[1]).strip()
                                if len(code) == 4 and code.isdigit():
                                    try:
                                        f_val = float(str(row[4]).replace(",", ""))
                                        t_val = float(str(row[10]).replace(",", ""))
                                        t_map[code] = {
                                            "官方名稱": name,
                                            "外資淨買超股數": f_val,
                                            "投信淨買超股數": t_val,
                                        }
                                    except Exception:
                                        pass
                        break 
            except Exception:
                pass
            dt = datetime.strptime(target_d, "%Y%m%d") - timedelta(days=1)
            target_d = dt.strftime("%Y%m%d")
            time.sleep(0.03)
        historical_inst[d_str] = t_map

    latest_inst = historical_inst.get(latest_date, {})

    fii_consec_days = {}
    sitc_consec_days = {}
    
    all_codes = set()
    for d_str in dates[:10]:
        all_codes.update(historical_inst.get(d_str, {}).keys())

    for code in all_codes:
        f_days = 0
        for d_str in dates[:10]:
            day_data = historical_inst.get(d_str, {}).get(code, {})
            if day_data.get("外資淨買超股數", 0) > 0:
                f_days += 1
            else:
                break
        fii_consec_days[code] = f_days

        s_days = 0
        for d_str in dates[:10]:
            day_data = historical_inst.get(d_str, {}).get(code, {})
            if day_data.get("投信淨買超股數", 0) > 0:
                s_days += 1
            else:
                break
        sitc_consec_days[code] = s_days

    def get_day_market(d_str):
        m_dict = {}
        url = (
            "https://www.twse.com.tw/rwd/zh/afterTrading/"
            f"MI_INDEX?response=json&type=ALLBUT0999&date={d_str}"
        )
        try:
            res = session.get(url, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if data.get("stat") == "OK":
                    for table in data.get("tables", []):
                        if "data" not in table:
                            continue
                        for row in table["data"]:
                            if len(row) < 11:
                                continue
                            code = str(row[0]).strip()
                            if not (len(code) == 4 and code.isdigit()):
                                continue
                            try:
                                name = str(row[1]).strip()
                                tv = 0.0
                                try:
                                    tv = float(str(row[4]).replace(",", ""))
                                except Exception:
                                    try:
                                        tv = float(str(row[5]).replace(",", ""))
                                    except Exception:
                                        pass

                                close_raw = str(row[8]).replace(",", "").strip()
                                if close_raw in ["--", "-", ""]:
                                    continue
                                close_p = float(close_raw)

                                sign = -1.0 if ("-" in str(row[9]) or "跌" in str(row[9])) else 1.0
                                chg_raw = str(row[10]).replace(",", "").strip()
                                if chg_raw not in ["--", "-", ""]:
                                    chg_val = float(chg_raw) * sign
                                else:
                                    chg_val = 0.0

                                prev_p = close_p - chg_val
                                pct_val = (chg_val / prev_p) * 100 if prev_p > 0 else 0.0

                                m_dict[code] = {
                                    "官方名稱": name,
                                    "收盤價": close_p,
                                    "漲跌幅(%)": round(pct_val, 2),
                                    "成交金額": tv,
                                }
                            except Exception:
                                continue
        except Exception:
            pass
        return m_dict

    today_dict = get_day_market(latest_date)
    prev_dict = get_day_market(prev_date)

    historical_market = {}
    for d_str in dates[:30]:
        historical_market[d_str] = get_day_market(d_str)
        time.sleep(0.02)

    return today_dict, prev_dict, latest_inst, dates, fii_consec_days, sitc_consec_days, historical_market


# =========================================================
# 讀取資料
# =========================================================

with st.spinner("⏳ 正在取得市場資料並計算籌碼擴散、蓄勢指標與 20日價格模型..."):
    (
        today_dict,
        prev_dict,
        latest_inst,
        target_dates,
        fii_consec_days,
        sitc_consec_days,
        historical_market,
    ) = fetch_market_data()

    latest_date = target_dates[0] if target_dates else datetime.now().strftime("%Y%m%d")
    prev_date = target_dates[1] if len(target_dates) > 1 else latest_date


if latest_date:
    st.sidebar.markdown("---")
    st.sidebar.success(f"📅 有效對應交易日：{latest_date}\n(對比 {prev_date})")


# =========================================================
# 取得 TOP 100 清單
# =========================================================

def get_top_n_amt_codes(m_dict, n=100):
    s = sorted(
        [(k, v["成交金額"]) for k, v in m_dict.items() if v["成交金額"] > 0],
        key=lambda x: x[1],
        reverse=True,
    )
    return [item[0] for item in s[:n]]

def get_top_n_fii_codes(inst_map, n=100):
    s = sorted(
        [(code, data["外資淨買超股數"]) for code, data in inst_map.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    return [item[0] for item in s[:n]]

def get_top_n_sitc_codes(inst_map, n=100):
    s = sorted(
        [(code, data["投信淨買超股數"]) for code, data in inst_map.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    return [item[0] for item in s[:n]]

amt_top100_codes = get_top_n_amt_codes(today_dict, 100)
fii_top100_codes = get_top_n_fii_codes(latest_inst, 100)
sitc_top100_codes = get_top_n_sitc_codes(latest_inst, 100)


def get_inst_info(code):
    return latest_inst.get(code, {"外資淨買超股數": 0.0, "投信淨買超股數": 0.0})


# =========================================================
# 計算 20 日平均成交值與 20日價格模型指標
# =========================================================

def calculate_amt_20d_metrics(code, today_amt):
    if today_amt <= 0 or not historical_market:
        return 0.0, 0.0

    historical_values = []
    sorted_dates = sorted(historical_market.keys(), reverse=True)
    for d_str in sorted_dates:
        if target_dates and d_str == target_dates[0]:
            continue
        day_data = historical_market.get(d_str, {})
        if code in day_data:
            amt = day_data[code].get("成交金額", 0)
            if amt > 0:
                historical_values.append(amt)
        if len(historical_values) >= 20:
            break

    if len(historical_values) == 0:
        return 0.0, 0.0

    avg_20d = float(np.mean(historical_values))
    ratio = (today_amt / avg_20d) if avg_20d > 0 else 0.0
    return round(avg_20d / 100000000, 2), round(ratio, 2)


def calculate_ai_20_model(code, current_close):
    if not historical_market or current_close <= 0:
        return 0.0, "🟡 【盤整震盪 - 資料不足】"

    historical_prices = []
    latest_date_val = target_dates[0] if target_dates else None

    sorted_dates = sorted(historical_market.keys(), reverse=True)

    for d_str in sorted_dates:
        if latest_date_val and d_str == latest_date_val:
            continue

        day_data = historical_market.get(d_str, {})
        if code not in day_data:
            continue

        p = day_data[code].get("收盤價", 0)
        if p > 0:
            historical_prices.append(float(p))

        if len(historical_prices) >= 20:
            break

    if len(historical_prices) < 20:
        return 0.0, "🟡 【盤整震盪 - 資料不足】"

    previous_20 = list(reversed(historical_prices[:20]))

    ma20_prices = previous_20[-19:] + [float(current_close)]
    ma20 = float(np.mean(ma20_prices))

    bias20 = (
        ((float(current_close) - ma20) / ma20) * 100
        if ma20 > 0 else 0.0
    )

    price_20d_ago = previous_20[0]

    momentum20 = (
        ((float(current_close) - price_20d_ago) / price_20d_ago) * 100
        if price_20d_ago > 0 else 0.0
    )

    model_score = round(
        bias20 * 0.5 + momentum20 * 0.5,
        2
    )

    if model_score <= -2.5:
        status = "🟢 【建議買進 - 價格修正/低接】"
    elif model_score >= 4.0:
        status = "🔴 【建議賣出 - 價格過熱/高檔】"
    else:
        status = "🟡 【盤整震盪 - 區間整理】"

    return model_score, status


def build_dataframe_for_codes(codes_list):
    rows = []
    for c in codes_list:
        if c not in today_dict:
            continue
        info = today_dict[c]

        amt_today = info["成交金額"]
        pct_chg = info["漲跌幅(%)"]
        ind = st.session_state.user_industry_map.get(c, "未分類")
        close_p = info["收盤價"]
        inst_info = get_inst_info(c)

        fii_shares = inst_info["外資淨買超股數"]
        sitc_shares = inst_info["投信淨買超股數"]
        est_total_shares = (amt_today / close_p) * 15 if close_p > 0 else 1e7

        fii_ratio = max(0.0, (fii_shares / est_total_shares) * 100)
        sitc_ratio = max(0.0, (sitc_shares / est_total_shares) * 100)
        combined_ratio = fii_ratio + sitc_ratio

        f_days = fii_consec_days.get(c, 0)
        s_days = sitc_consec_days.get(c, 0)

        avg_20d_yi, amt_ratio = calculate_amt_20d_metrics(c, amt_today)
        ai20_score, ai20_status = calculate_ai_20_model(c, close_p)

        rows.append({
            "代號": c,
            "名稱": info["官方名稱"],
            "族群": ind,
            "收盤價": close_p,
            "漲跌幅(%)": pct_chg,
            "成交金額(億)": round(amt_today / 100000000, 2),
            "20日均量(億)": avg_20d_yi,
            "量能倍數": amt_ratio,
            "外資買超(張)": int(fii_shares / 1000),
            "投信買超(張)": int(sitc_shares / 1000),
            "法人買超占比(%)": round(combined_ratio, 2),
            "外資連買": f_days,
            "投信連買": s_days,
            "20日模型分數": ai20_score,
            "價格狀態": ai20_status,
        })
    return pd.DataFrame(rows)


# =========================================================
# 頁面主體展示範例
# =========================================================

st.subheader("📊 成交金額前 100 大個股清單")
if today_dict:
    df_amt = build_dataframe_for_codes(amt_top100_codes)
    st.dataframe(df_amt, use_container_width=True)
else:
    st.warning("⚠️ 目前無法取得台股市場資料，請稍後再試。")