from datetime import datetime, timedelta
import json
import os
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# =========================================================
# 基本設定
# =========================================================

st.set_page_config(
    page_title="台股強勢策略",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("台股強勢策略")

DB_FILE = "industry_db.json"


# =========================================================
# 族群資料庫
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


if "user_industry_map" not in st.session_state:
    st.session_state.user_industry_map = load_db()


# =========================================================
# 搜尋
# =========================================================

search_query = st.sidebar.text_input(
    "🔍 側邊欄快速查找台股",
    placeholder="輸入代號或名稱 (例: 2330)",
)


# =========================================================
# AI 指標計算邏輯 (AI-20日通道模型)
# =========================================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_history_cached(code, start_str):
    formatted_start = f"{start_str[:4]}-{start_str[4:6]}-{start_str[6:]}"
    
    try:
        ticker = f"{code}.TW"
        df = yf.download(ticker, start=formatted_start, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                close_series = df["Close"].iloc[:, 0] if "Close" in df.columns.levels[0] else pd.Series(dtype=float)
            else:
                close_series = df["Close"] if "Close" in df.columns else pd.Series(dtype=float)
            
            rows = [{"Close": float(val)} for val in close_series.dropna()]
            if len(rows) > 0:
                return rows
    except Exception:
        pass
        
    try:
        ticker = f"{code}.TWO"
        df = yf.download(ticker, start=formatted_start, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                close_series = df["Close"].iloc[:, 0] if "Close" in df.columns.levels[0] else pd.Series(dtype=float)
            else:
                close_series = df["Close"] if "Close" in df.columns else pd.Series(dtype=float)
            
            rows = [{"Close": float(val)} for val in close_series.dropna()]
            if len(rows) > 0:
                return rows
    except Exception:
        pass
        
    return []


def calculate_ai_signals_for_stocks(stock_codes, latest_date_str):
    signals_dict = {}
    try:
        ref_date = datetime.strptime(latest_date_str, "%Y%m%d")
    except Exception:
        ref_date = datetime.now()
        
    start_date = ref_date - timedelta(days=120)
    start_str = start_date.strftime("%Y%m%d")

    for code in stock_codes:
        try:
            rows = get_stock_history_cached(code, start_str)
            if len(rows) > 20:
                df_stock = pd.DataFrame(rows)
                df_stock["MA20"] = df_stock["Close"].rolling(window=20).mean()
                df_stock["STD20"] = df_stock["Close"].rolling(window=20).std()
                
                df_stock["Upper_Band"] = df_stock["MA20"] + (2.0 * df_stock["STD20"])
                df_stock["Lower_Band"] = df_stock["MA20"] - (2.0 * df_stock["STD20"])
                
                df_stock["Channel_Pct"] = (
                    (df_stock["Close"] - df_stock["Lower_Band"]) / 
                    (df_stock["Upper_Band"] - df_stock["Lower_Band"] + 1e-8)
                ) * 100
                
                if len(df_stock) >= 2:
                    curr_p = df_stock["Close"].iloc[-1]
                    prev_p = df_stock["Close"].iloc[-2]
                    upper = df_stock["Upper_Band"].iloc[-1]
                    lower = df_stock["Lower_Band"].iloc[-1]
                    curr_pct = df_stock["Channel_Pct"].iloc[-1]
                    prev_pct = df_stock["Channel_Pct"].iloc[-2]
                    
                    if pd.isna(curr_pct):
                        signals_dict[code] = "⚪ 計算中"
                    elif prev_pct < 25 and curr_pct >= 25:
                        signals_dict[code] = "🟢 買進訊號"
                    elif prev_pct > 75 and curr_pct <= 75:
                        signals_dict[code] = "🔴 賣出訊號"
                    elif curr_p <= lower or curr_pct <= 15:
                        signals_dict[code] = "🟢 處於低檔區"
                    elif curr_p >= upper or curr_pct >= 85:
                        signals_dict[code] = "🔴 處於高檔區"
                    else:
                        signals_dict[code] = "⚪ 區間震盪"
                else:
                    signals_dict[code] = "⚪ 資料不足"
            else:
                signals_dict[code] = "⚪ 暫無資料"
        except Exception:
            signals_dict[code] = "⚪ 暫無資料"
            
    return signals_dict


# =========================================================
# 取得 TWSE 資料
# =========================================================

@st.cache_data(ttl=600)
def fetch_top100_data():
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

    for i in range(20):
        d_str = curr.strftime("%Y%m%d")
        test_url = (
            "https://www.twse.com.tw/rwd/zh/afterTrading/"
            f"MI_INDEX?response=json&type=ALLBUT0999&date={d_str}"
        )
        try:
            res = session.get(test_url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get("stat") == "OK" and len(data.get("tables", [])) > 0:
                    dates.append(d_str)
                    if len(dates) >= 2:
                        break
        except Exception:
            pass
        curr -= timedelta(days=1)
        time.sleep(0.05)

    if len(dates) == 0:
        return {}, {}, {}, []

    latest_date = dates[0]
    prev_date = dates[1] if len(dates) > 1 else latest_date

    def get_t86_map(d_str):
        t_map = {}
        target_d = d_str
        for _ in range(5):
            url = (
                "https://www.twse.com.tw/rwd/zh/fund/"
                f"T86?response=json&date={target_d}&selectType=ALLBUT0999"
            )
            try:
                r = session.get(url, timeout=6)
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
            time.sleep(0.05)
        return t_map

    latest_inst = get_t86_map(latest_date)

    def get_day_market(d_str):
        m_dict = {}
        url = (
            "https://www.twse.com.tw/rwd/zh/afterTrading/"
            f"MI_INDEX?response=json&type=ALLBUT0999&date={d_str}"
        )
        try:
            res = session.get(url, timeout=8)
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

    return today_dict, prev_dict, latest_inst, dates


# =========================================================
# 執行資料取得與 AI 訊號計算
# =========================================================

with st.spinner("⏳ 正在取得最近有效交易日資料與籌碼，並透過 Yahoo Finance 計算 AI 訊號..."):
    today_dict, prev_dict, latest_inst, target_dates = fetch_top100_data()

    latest_date = target_dates[0] if target_dates else datetime.now().strftime("%Y%m%d")
    prev_date = target_dates[1] if len(target_dates) > 1 else latest_date
    
    all_active_codes = list(today_dict.keys())
    ai_signals_map = calculate_ai_signals_for_stocks(all_active_codes, latest_date)


if latest_date:
    st.sidebar.markdown("---")
    st.sidebar.success(f"📅 有效對應交易日：{latest_date} (對比 {prev_date})")


# =========================================================
# 篩選邏輯與取得清單
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

today_top100_set = set(get_top_n_amt_codes(today_dict, 100))

amt_top100_codes = get_top_n_amt_codes(today_dict, 100)
fii_top100_codes = get_top_n_fii_codes(latest_inst, 100)
sitc_top100_codes = get_top_n_sitc_codes(latest_inst, 100)


def get_inst_info(code):
    return latest_inst.get(code, {"外資淨買超股數": 0.0, "投信淨買超股數": 0.0})


def get_industry_institution_stats(industry):
    industry_codes = [
        code for code, ind in st.session_state.user_industry_map.items() if ind == industry
    ]
    if not industry_codes:
        return {
            "外資參與檔數": 0, 
            "投信參與檔數": 0, 
            "雙法人參與檔數": 0,  
            "法人參與檔數": 0, 
            "Top100檔數": 0,
            "族群外資參與檔數": 0,
            "族群投信參與檔數": 0,
            "族群雙法人參與檔數": 0,
            "族群法人參與檔數": 0,
            "族群Top100檔數": 0,
        }

    fii_count, sitc_count, both_count, institutional_count, top100_count = 0, 0, 0, 0, 0
    for code in industry_codes:
        inst = get_inst_info(code)
        fii, sitc = inst["外資淨買超股數"], inst["投信淨買超股數"]
        if fii > 0: fii_count += 1
        if sitc > 0: sitc_count += 1
        if fii > 0 and sitc > 0: both_count += 1
        if fii > 0 or sitc > 0: institutional_count += 1
        if code in today_top100_set: top100_count += 1

    return {
        "外資參與檔數": fii_count, 
        "投信參與檔數": sitc_count,  
        "雙法人參與檔數": both_count,  
        "法人參與檔數": institutional_count,
        "Top100檔數": top100_count,
        "族群外資參與檔數": fii_count,
        "族群投信參與檔數": sitc_count,
        "族群雙法人參與檔數": both_count,
        "族群法人參與檔數": institutional_count,
        "族群Top100檔數": top100_count,
    }


def classify_industry_state(target_code, industry_stats):
    top100_count = industry_stats["Top100檔數"]
    institutional_count = industry_stats["法人參與檔數"]
    if top100_count >= 2:
        return "🔥 族群擴散"
    if target_code in today_top100_set and institutional_count >= 2:
        return "🟡 族群醞釀"
    return "⚪ 單兵先行"


def build_group_stats_with_inst(codes_list):
    rows = []
    for c in codes_list:
        if c not in today_dict:
            continue
        info = today_dict[c]
        prev_info = prev_dict.get(c, {"成交金額": 0.0})

        amt_today = info["成交金額"]
        amt_yesterday = prev_info["成交金額"]
        multiplier = round(amt_today / amt_yesterday, 2) if amt_yesterday > 0 else 0.0
        pct_chg = info["漲跌幅(%)"]
        ind = st.session_state.user_industry_map.get(c, "未分類")
        close_p = info["收盤價"]
        inst_info = get_inst_info(c)

        fii_shares = inst_info["外資淨買超股數"]
        sitc_shares = inst_info["投信淨買超股數"]
        est_total_shares = (amt_today / close_p) * 15 if close_p > 0 else 1e7

        fii_ratio = (fii_shares / est_total_shares) * 100
        sitc_ratio = (sitc_shares / est_total_shares) * 100
        combined_ratio = fii_ratio + sitc_ratio

        if combined_ratio <= 0:
            continue

        eff_ratio_factor = multiplier / max(abs(pct_chg), 0.5) if multiplier > 0 else 0.0
        resonance_score = round(combined_ratio * min(eff_ratio_factor, 5.0), 3)

        if resonance_score <= 0:
            continue

        is_qualified_efficient = (pct_chg <= multiplier) and (combined_ratio > 0)

        industry_stats = get_industry_institution_stats(ind)
        industry_state = classify_industry_state(c, industry_stats)
        ai_signal = ai_signals_map.get(c, "⚪ 暫無資料")

        rows.append({
            "代號": c,
            "官方名稱": info["官方名稱"],
            "族群": ind,
            "雙法人合佔比(%)": round(combined_ratio, 3),
            "外資買超(張)": round(fii_shares / 1000, 1),
            "投信買超(張)": round(sitc_shares / 1000, 1),
            "🤖 AI訊號狀態": ai_signal,
            "🔥 效率籌碼共振分": resonance_score,
            "成交值放大倍數": multiplier,
            "漲跌幅(%)": pct_chg,
            "符合量價/籌碼優選": "符合" if is_qualified_efficient else "一般",
            "外本比(%)": round(fii_ratio, 3),
            "投本比(%)": round(sitc_ratio, 3),
            "收盤價": close_p,
            "成交值(億)": round(amt_today / 100000000, 2),
            "族群狀態": industry_state,
            "族群外資參與檔數": industry_stats["外資參與檔數"],
            "族群投信參與檔數": industry_stats["投信參與檔數"],
            "族群雙法人參與檔數": industry_stats["族群雙法人參與檔數"],
            "族群法人參與檔數": industry_stats["族群法人參與檔數"],
            "族群Top100檔數": industry_stats["Top100檔數"],
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = df.sort_values(by="🔥 效率籌碼共振分", ascending=False).reset_index(drop=True)
    total_count = len(df)
    
    group_summary = (
        df.groupby("族群")
        .agg(
            個股數=("代號", "count"),
            總成交值億=("成交值(億)", "sum"),
            平均共振分=("🔥 效率籌碼共振分", "mean"),
            平均放大倍數=("成交值放大倍數", "mean"),
            平均漲跌幅=("漲跌幅(%)", "mean"),
            平均雙法人合佔比=("雙法人合佔比(%)", "mean"),
            族群外資參與檔數=("族群外資參與檔數", "max"),
            族群投信參與檔數=("族群投信參與檔數", "max"),
            族群雙法人參與檔數=("族群雙法人參與檔數", "max"),
            族群法人參與檔數=("族群法人參與檔數", "max"),
            族群Top100檔數=("族群Top100檔數", "max"),
        )
        .reset_index()
    )

    group_summary["占比(%)"] = round((group_summary["個股數"] / total_count) * 100, 2)
    group_summary["平均共振分"] = round(group_summary["平均共振分"], 3)
    group_summary["平均放大倍數"] = round(group_summary["平均放大倍數"], 2)
    group_summary["平均漲跌幅"] = round(group_summary["平均漲跌幅"], 2)
    group_summary["平均雙法人合佔比"] = round(group_summary["平均雙法人合佔比"], 3)

    return df, group_summary


df_amt, grp_amt = build_group_stats_with_inst(amt_top100_codes)
df_fii, grp_fii = build_group_stats_with_inst(fii_top100_codes)
df_sitc, grp_sitc = build_group_stats_with_inst(sitc_top100_codes)

if search_query:
    if not df_amt.empty:
        df_amt = df_amt[df_amt["代號"].str.contains(search_query) | df_amt["官方名稱"].str.contains(search_query)]
    if not df_fii.empty:
        df_fii = df_fii[df_fii["代號"].str.contains(search_query) | df_fii["官方名稱"].str.contains(search_query)]
    if not df_sitc.empty:
        df_sitc = df_sitc[df_sitc["代號"].str.contains(search_query) | df_sitc["官方名稱"].str.contains(search_query)]


# =========================================================
# 市場共識交叉比對邏輯
# =========================================================

def build_market_consensus(d1, d2, d3):
    sets = []
    for df_item in [d1, d2, d3]:
        if not df_item.empty and "代號" in df_item.columns:
            sets.append(set(df_item["代號"].astype(str)))
        else:
            sets.append(set())
            
    if len(sets) == 3:
        common_codes = sets[0].intersection(sets[1]).intersection(sets[2])
    elif len(sets) == 2:
        common_codes = sets[0].intersection(sets[1])
    elif len(sets) == 1:
        common_codes = sets[0]
    else:
        common_codes = set()

    rows = []
    # 以成交值 TOP 100 完整資料源為基準來抓取對應欄位
    base_df = d1 if not d1.empty else (d2 if not d2.empty else d3)
    
    if not base_df.empty and common_codes:
        subset = base_df[base_df["代號"].astype(str).isin(common_codes)].copy()
        for _, row in subset.iterrows():
            c = row["代號"]
            # 額外統計出現在幾個分頁中
            in_amt = "✅" if (not d1.empty and c in set(d1["代號"].astype(str))) else "❌"
            in_fii = "✅" if (not d2.empty and c in set(d2["代號"].astype(str))) else "❌"
            in_sitc = "✅" if (not d3.empty and c in set(d3["代號"].astype(str))) else "❌"
            
            row_dict = row.to_dict()
            row_dict["成交值TOP100"] = in_amt
            row_dict["外資TOP100"] = in_fii
            row_dict["投信TOP100"] = in_sitc
            rows.append(row_dict)

    consensus_df = pd.DataFrame(rows)
    if not consensus_df.empty:
        consensus_df = consensus_df.sort_values(by="🔥 效率籌碼共振分", ascending=False).reset_index(drop=True)
        
        total_count = len(consensus_df)
        consensus_group = (
            consensus_df.groupby("族群")
            .agg(
                個股數=("代號", "count"),
                總成交值億=("成交值(億)", "sum"),
                平均共振分=("🔥 效率籌碼共振分", "mean"),
                平均放大倍數=("成交值放大倍數", "mean"),
                平均漲跌幅=("漲跌幅(%)", "mean"),
                平均雙法人合佔比=("雙法人合佔比(%)", "mean"),
                族群外資參與檔數=("族群外資參與檔數", "max"),
                族群投信參與檔數=("族群投信參與檔數", "max"),
                族群雙法人參與檔數=("族群雙法人參與檔數", "max"),
                族群法人參與檔數=("族群法人參與檔數", "max"),
                族群Top100檔數=("族群Top100檔數", "max"),
            )
            .reset_index()
        )
        consensus_group["占比(%)"] = round((consensus_group["個股數"] / total_count) * 100, 2)
        consensus_group["平均共振分"] = round(consensus_group["平均共振分"], 3)
        consensus_group["平均放大倍數"] = round(consensus_group["平均放大倍數"], 2)
        consensus_group["平均漲跌幅"] = round(consensus_group["平均漲跌幅"], 2)
        consensus_group["平均雙法人合佔比"] = round(consensus_group["平均雙法人合佔比"], 3)
        return consensus_df, consensus_group
        
    return pd.DataFrame(), pd.DataFrame()


df_consensus, grp_consensus = build_market_consensus(df_amt, df_fii, df_sitc)


def update_map_from_editor(edited_df):
    if not edited_df.empty and "代號" in edited_df.columns and "族群" in edited_df.columns:
        updated_map = st.session_state.user_industry_map.copy()
        for _, row in edited_df.iterrows():
            c_code = str(row["代號"]).strip()
            c_ind = str(row["族群"]).strip() if pd.notna(row["族群"]) else ""
            updated_map[c_code] = c_ind
        st.session_state.user_industry_map = updated_map
        save_db(updated_map)
        st.success("✅ 族群設定已成功更新！")


# =========================================================
# 頁籤介面
# =========================================================

tab1, tab2, tab3, tab4 = st.tabs([
    "💰 成交值 TOP 100",
    "🌍 外資買超 TOP 100",
    "🏛️ 投信買超 TOP 100",
    "🎯 市場共識",
])

with tab1:
    if not grp_amt.empty:
        c1, c2 = st.columns([1.1, 1.4])
        with c1:
            st.markdown("### 📊 族群分布")
            st.dataframe(grp_amt, use_container_width=True, hide_index=True)
        with c2:
            st.markdown(f"### 📋 個股清單 ({len(df_amt)}檔)")
            ed_amt = st.data_editor(
                df_amt,
                use_container_width=True,
                hide_index=True,
                disabled=[c for c in df_amt.columns if c not in ["族群"]],
                key="ed_amt_top100",
            )
            if st.button("💾 儲存成交值族群修改", key="btn_save_amt"):
                update_map_from_editor(ed_amt)
    else:
        st.info("目前無符合條件的成交值資料。")

with tab2:
    if not grp_fii.empty:
        c1, c2 = st.columns([1.1, 1.4])
        with c1:
            st.markdown("### 📊 族群分布")
            st.dataframe(grp_fii, use_container_width=True, hide_index=True)
        with c2:
            st.markdown(f"### 📋 個股清單 ({len(df_fii)}檔)")
            ed_fii = st.data_editor(
                df_fii,
                use_container_width=True,
                hide_index=True,
                disabled=[c for c in df_fii.columns if c not in ["族群"]],
                key="ed_fii_top100",
            )
            if st.button("💾 儲存外資買超族群修改", key="btn_save_fii"):
                update_map_from_editor(ed_fii)
    else:
        st.info("目前無符合條件的外資買超資料。")

with tab3:
    if not grp_sitc.empty:
        c1, c2 = st.columns([1.1, 1.4])
        with c1:
            st.markdown("### 📊 族群分布")
            st.dataframe(grp_sitc, use_container_width=True, hide_index=True)
        with c2:
            st.markdown(f"### 📋 個股清單 ({len(df_sitc)}檔)")
            ed_sitc = st.data_editor(
                df_sitc,
                use_container_width=True,
                hide_index=True,
                disabled=[c for c in df_sitc.columns if c not in ["族群"]],
                key="ed_sitc_top100",
            )
            if st.button("💾 儲存投信買超族群修改", key="btn_save_sitc"):
                update_map_from_editor(ed_sitc)
    else:
        st.info("目前無符合條件的投信買超資料。")

with tab4:
    if not grp_consensus.empty:
        c1, c2 = st.columns([1.1, 1.4])
        with c1:
            st.markdown("### 📊 族群分布")
            st.dataframe(grp_consensus, use_container_width=True, hide_index=True)
        with c2:
            st.markdown(f"### 📋 個股清單 ({len(df_consensus)}檔)")
            ed_consensus = st.data_editor(
                df_consensus,
                use_container_width=True,
                hide_index=True,
                disabled=[c for c in df_consensus.columns if c not in ["族群"]],
                key="ed_consensus_top100",
            )
            if st.button("💾 儲存市場共識族群修改", key="btn_save_consensus"):
                update_map_from_editor(ed_consensus)
    else:
        st.info("目前無同時符合三大指標清單交集的個股。")