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
    page_title="台股強勢策略",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("台股強勢策略")

DB_FILE = "industry_db.json"


# =========================================================
# 族群資料庫 (未設定時預設給空白)
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
# 執行資料取得
# =========================================================

with st.spinner("⏳ 正在取得最近有效交易日資料與籌碼..."):
    today_dict, prev_dict, latest_inst, target_dates = fetch_top100_data()

    latest_date = target_dates[0] if target_dates else datetime.now().strftime("%Y%m%d")
    prev_date = target_dates[1] if len(target_dates) > 1 else latest_date


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

amt_top100_codes = get_top_n_amt_codes(today_dict, 100)
fii_top100_codes = get_top_n_fii_codes(latest_inst, 100)
sitc_top100_codes = get_top_n_sitc_codes(latest_inst, 100)


def get_inst_info(code):
    return latest_inst.get(code, {"外資淨買超股數": 0.0, "投信淨買超股數": 0.0})


def build_group_stats_with_inst(codes_list):
    rows = []
    for c in codes_list:
        if c not in today_dict:
            continue
        info = today_dict[c]

        amt_today = info["成交金額"]
        pct_chg = info["漲跌幅(%)"]
        
        ind = st.session_state.user_industry_map.get(c, "")
        
        close_p = info["收盤價"]
        inst_info = get_inst_info(c)

        fii_shares = inst_info["外資淨買超股數"]
        sitc_shares = inst_info["投信淨買超股數"]
        est_total_shares = (amt_today / close_p) * 15 if close_p > 0 else 1e7

        fii_ratio = max(0.0, (fii_shares / est_total_shares) * 100)
        sitc_ratio = max(0.0, (sitc_shares / est_total_shares) * 100)
        combined_ratio = fii_ratio + sitc_ratio

        rows.append({
            "代號": c,
            "官方名稱": info["官方名稱"],
            "族群": ind,
            "外本比(%)": round(fii_ratio, 3),
            "投本比(%)": round(sitc_ratio, 3),
            "雙法人合佔比(%)": round(combined_ratio, 3),
            "漲跌幅(%)": pct_chg,
            "收盤價": close_p,
            "成交值(億)": round(amt_today / 100000000, 2),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    def weighted_avg_sqrt(sub_df, col_name):
        valid = sub_df[sub_df[col_name] > 0]
        if valid.empty:
            return 0.0
        weights = valid["成交值(億)"]
        if weights.sum() == 0:
            raw_mean = valid[col_name].mean()
        else:
            raw_mean = np.average(valid[col_name], weights=weights)
        return round(float(np.sqrt(max(0.0, raw_mean))), 3)

    group_rows = []
    for g_name, sub in df.groupby("族群"):
        group_rows.append({
            "族群": g_name,
            "個股數": len(sub),
            "總成交值億": round(sub["成交值(億)"].sum(), 2),
            "外本比": weighted_avg_sqrt(sub, "外本比(%)"),
            "投本比": weighted_avg_sqrt(sub, "投本比(%)"),
            "雙法人平均籌碼集中度": weighted_avg_sqrt(sub, "雙法人合佔比(%)"),
        })

    group_summary = pd.DataFrame(group_rows)
    return df, group_summary


df_amt, grp_amt = build_group_stats_with_inst(amt_top100_codes)
df_fii, grp_fii = build_group_stats_with_inst(fii_top100_codes)
df_sitc, grp_sitc = build_group_stats_with_inst(sitc_top100_codes)

if search_query:
    for d in [df_amt, df_fii, df_sitc]:
        if not d.empty:
            match = d["代號"].str.contains(search_query) | d["官方名稱"].str.contains(search_query)
            d.drop(d.index[~match], inplace=True)


# =========================================================
# 市場共識邏輯修正：依據「雙法人平均籌碼集中度」取前三強
# =========================================================

def get_top3_groups_by_concentration(grp_df):
    if grp_df.empty:
        return set()
    valid_grp = grp_df[grp_df["族群"].str.strip() != ""]
    if valid_grp.empty:
        return set()
    # 改為依據「雙法人平均籌碼集中度」由高到低排序取前 3 強
    top3 = valid_grp.sort_values(by="雙法人平均籌碼集中度", ascending=False).head(3)
    return set(top3["族群"])

top3_amt_groups = get_top3_groups_by_concentration(grp_amt)
top3_fii_groups = get_top3_groups_by_concentration(grp_fii)
top3_sitc_groups = get_top3_groups_by_concentration(grp_sitc)

# 三方前三強聯集 (Union)
consensus_groups = top3_amt_groups.union(top3_fii_groups).union(top3_sitc_groups)

def build_market_consensus_new(d_amt, d_fii, d_sitc, target_groups):
    if not target_groups:
        return pd.DataFrame(), pd.DataFrame()
        
    all_dfs = [d for d in [d_amt, d_fii, d_sitc] if not d.empty and "族群" in d.columns]
    if not all_dfs:
        return pd.DataFrame(), pd.DataFrame()
        
    combined_df = pd.concat(all_dfs).drop_duplicates(subset=["代號"]).copy()
    consensus_df = combined_df[combined_df["族群"].isin(target_groups)].copy()
    
    if consensus_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    def weighted_avg_sqrt_cons(sub_df, col_name):
        valid = sub_df[sub_df[col_name] > 0]
        if valid.empty:
            return 0.0
        weights = valid["成交值(億)"]
        if weights.sum() == 0:
            raw_mean = valid[col_name].mean()
        else:
            raw_mean = np.average(valid[col_name], weights=weights)
        return round(float(np.sqrt(max(0.0, raw_mean))), 3)

    group_rows = []
    for g_name, sub in consensus_df.groupby("族群"):
        total_amt = round(sub["成交值(億)"].sum(), 2)
        group_rows.append({
            "族群": g_name,
            "個股數": len(sub),
            "總成交值億": total_amt,
            "外本比": weighted_avg_sqrt_cons(sub, "外本比(%)"),
            "投本比": weighted_avg_sqrt_cons(sub, "投本比(%)"),
            "雙法人平均籌碼集中度": weighted_avg_sqrt_cons(sub, "雙法人合佔比(%)"),
        })

    consensus_group_summary = pd.DataFrame(group_rows)
    # 共識區一樣依「雙法人平均籌碼集中度」與總成交值進行強弱排序
    if not consensus_group_summary.empty:
        consensus_group_summary = consensus_group_summary.sort_values(
            by=["雙法人平均籌碼集中度", "總成交值億"], ascending=False
        ).reset_index(drop=True)

    return consensus_df, consensus_group_summary

df_consensus, grp_consensus = build_market_consensus_new(df_amt, df_fii, df_sitc, consensus_groups)


def update_map_from_editor(edited_df):
    if not edited_df.empty and "代號" in edited_df.columns and "族群" in edited_df.columns:
        updated_map = st.session_state.user_industry_map.copy()
        for _, row in edited_df.iterrows():
            c_code = str(row["代號"]).strip()
            c_ind = str(row["族群"]).strip() if pd.notna(row["族群"]) else ""
            if c_ind != "":
                updated_map[c_code] = c_ind
            elif c_code in updated_map:
                del updated_map[c_code]
        st.session_state.user_industry_map = updated_map
        save_db(updated_map)
        st.success("✅ 族群設定已成功更新！")


# =========================================================
# 頁籤介面
# =========================================================

tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 市場共識",
    "💰 成交值 TOP 100",
    "🌍 外資買超 TOP 100",
    "🏛️ 投信買超 TOP 100",
])

with tab1:
    if not df_consensus.empty:
        if "consensus_group_checks" not in st.session_state:
            st.session_state.consensus_group_checks = {}

        editor_grp_data = []
        for _, r in grp_consensus.iterrows():
            g_name = r["族群"]
            if g_name not in st.session_state.consensus_group_checks:
                st.session_state.consensus_group_checks[g_name] = True
                
            row_dict = r.to_dict()
            row_dict["選擇"] = st.session_state.consensus_group_checks[g_name]
            cols_order = ["選擇", "族群"] + [c for c in r.index if c != "族群"]
            editor_grp_data.append({k: row_dict[k] for k in cols_order if k in row_dict})

        df_grp_editable = pd.DataFrame(editor_grp_data)

        edited_grp_df = st.data_editor(
            df_grp_editable,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in df_grp_editable.columns if c != "選擇"],
            key="ed_consensus_group_table",
        )

        active_groups = []
        for _, row in edited_grp_df.iterrows():
            g_name = row["族群"]
            is_sel = bool(row["選擇"])
            st.session_state.consensus_group_checks[g_name] = is_sel
            if is_sel:
                active_groups.append(g_name)

        st.markdown("---")
        
        filtered_consensus = df_consensus[df_consensus["族群"].isin(active_groups)] if active_groups else df_consensus.iloc[0:0]

        ed_consensus = st.data_editor(
            filtered_consensus,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in filtered_consensus.columns if c not in ["族群"]],
            key="ed_consensus_top100",
        )
        if st.button("💾 儲存市場共識族群修改", key="btn_save_consensus"):
            update_map_from_editor(ed_consensus)
    else:
        st.info("目前無符合條件的市場共識族群。")

with tab2:
    if not df_amt.empty:
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

with tab3:
    if not df_fii.empty:
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

with tab4:
    if not df_sitc.empty:
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