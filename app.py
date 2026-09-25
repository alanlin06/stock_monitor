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

st.title("台股強勢策略 (籌碼擴散與溫度計模型)")

DB_FILE = "industry_db.json"


# =========================================================
# 族群資料庫管理
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

if "consensus_group_checks" not in st.session_state:
    st.session_state.consensus_group_checks = {}


# =========================================================
# 搜尋功能
# =========================================================

search_query = st.sidebar.text_input(
    "🔍 側邊欄快速查找台股",
    placeholder="輸入代號或名稱 (例: 2330)",
)


# =========================================================
# 取得 TWSE 資料與計算連續買超天數
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

    for i in range(30):
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
                    if len(dates) >= 15:
                        break
        except Exception:
            pass
        curr -= timedelta(days=1)
        time.sleep(0.03)

    if len(dates) == 0:
        return {}, {}, {}, [], {}, {}

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

    return today_dict, prev_dict, latest_inst, dates, fii_consec_days, sitc_consec_days


# =========================================================
# 讀取資料
# =========================================================

with st.spinner("⏳ 正在取得市場資料並計算籌碼擴散與溫度計模型..."):
    today_dict, prev_dict, latest_inst, target_dates, fii_consec_days, sitc_consec_days = fetch_market_data()

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

        rows.append({
            "代號": c,
            "官方名稱": info["官方名稱"],
            "族群": ind,
            "外資連買日": f_days,
            "投信連買日": s_days,
            "外本比(%)": round(fii_ratio, 3),
            "投本比(%)": round(sitc_ratio, 3),
            "雙法人合佔比(%)": round(combined_ratio, 3),
            "漲跌幅(%)": pct_chg,
            "收盤價": close_p,
            "成交值(億)": round(amt_today / 100000000, 2),
        })

    return pd.DataFrame(rows)


# =========================================================
# 族群籌碼擴散、法人強度與市場注意力模型
# =========================================================

def build_group_summary(df, investor="外資"):
    if df.empty:
        return pd.DataFrame()

    ratio_col = "外本比(%)" if investor == "外資" else "投本比(%)"
    group_rows = []

    for g_name, sub in df.groupby("族群", dropna=False):
        total_stocks = len(sub)
        positive = sub[sub[ratio_col] > 0].copy()

        positive_count = len(positive)
        diffusion = positive_count / total_stocks if total_stocks > 0 else 0.0

        if positive_count > 0:
            sqrt_values = np.sqrt(positive[ratio_col].clip(lower=0))
            sqrt_strength_mean = float(sqrt_values.mean())
            sqrt_strength_sum = float(sqrt_values.sum())
            ratio_median = float(positive[ratio_col].median())
        else:
            sqrt_strength_mean = 0.0
            sqrt_strength_sum = 0.0
            ratio_median = 0.0

        total_amt = float(sub["成交值(億)"].sum())
        avg_amt = total_amt / total_stocks if total_stocks else 0.0
        market_attention = float(np.log1p(max(total_amt, 0.0)))
        temperature = diffusion * sqrt_strength_mean * market_attention * 10.0

        group_rows.append({
            "族群": g_name,
            "追蹤個股數": total_stocks,
            f"{investor}正向數": positive_count,
            f"{investor}擴散度(%)": round(diffusion * 100, 1),
            f"{investor}√強度": round(sqrt_strength_mean, 3),
            f"{investor}√強度總和": round(sqrt_strength_sum, 3),
            f"{investor}本比中位數(%)": round(ratio_median, 3),
            "總成交值億": round(total_amt, 2),
            "平均成交值億": round(avg_amt, 2),
            "市場注意力": round(market_attention, 3),
            f"{investor}族群溫度": round(temperature, 2),
            "平均漲跌幅(%)": round(sub["漲跌幅(%)"].mean(), 2),
            f"{investor}平均連買日": round(
                sub[f"{investor}連買日"].mean(), 1
            ),
        })

    result = pd.DataFrame(group_rows)
    if not result.empty:
        result = result.sort_values(
            by=[f"{investor}族群溫度", f"{investor}擴散度(%)", "總成交值億"],
            ascending=False
        ).reset_index(drop=True)

    return result


def build_common_group_summary(d_fii, d_sitc):
    if d_fii.empty or d_sitc.empty:
        return pd.DataFrame()

    fii = d_fii[["代號", "族群", "外本比(%)", "成交值(億)"]].copy()
    sitc = d_sitc[["代號", "投本比(%)"]].copy()

    merged = fii.merge(sitc, on="代號", how="inner")
    if merged.empty:
        return pd.DataFrame()

    rows = []
    for g_name, sub in merged.groupby("族群", dropna=False):
        fii_positive = sub[sub["外本比(%)"] > 0]
        sitc_positive = sub[sub["投本比(%)"] > 0]
        common = sub[(sub["外本比(%)"] > 0) & (sub["投本比(%)"] > 0)]

        total = len(sub)
        common_count = len(common)
        common_diffusion = common_count / total if total else 0.0

        if common_count:
            fii_sqrt = np.sqrt(common["外本比(%)"].clip(lower=0))
            sitc_sqrt = np.sqrt(common["投本比(%)"].clip(lower=0))
            common_strength = float(((fii_sqrt + sitc_sqrt) / 2).mean())
        else:
            common_strength = 0.0

        total_amt = float(sub["成交值(億)"].sum())
        attention = float(np.log1p(max(total_amt, 0.0)))
        temperature = common_diffusion * common_strength * attention * 10.0

        rows.append({
            "族群": g_name,
            "共同追蹤個股數": total,
            "外資正向數": len(fii_positive),
            "投信正向數": len(sitc_positive),
            "雙法人共同數": common_count,
            "共同擴散度(%)": round(common_diffusion * 100, 1),
            "共同√強度": round(common_strength, 3),
            "總成交值億": round(total_amt, 2),
            "市場注意力": round(attention, 3),
            "雙法人共同溫度": round(temperature, 2),
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(
            by=["雙法人共同溫度", "共同擴散度(%)", "總成交值億"],
            ascending=False
        ).reset_index(drop=True)

    return result


# =========================================================
# 產生各法人個股資料
# =========================================================

df_amt = build_dataframe_for_codes(amt_top100_codes)
df_fii = build_dataframe_for_codes(fii_top100_codes)
df_sitc = build_dataframe_for_codes(sitc_top100_codes)

grp_fii = build_group_summary(df_fii, "外資")
grp_sitc = build_group_summary(df_sitc, "投信")
grp_common = build_common_group_summary(df_fii, df_sitc)


# =========================================================
# 市場共識邏輯與個股綜合觀察
# =========================================================

def build_market_consensus(d_fii, d_sitc, common_groups):
    if d_fii.empty or d_sitc.empty:
        return pd.DataFrame()

    fii_codes = set(d_fii["代號"].astype(str))
    sitc_codes = set(d_sitc["代號"].astype(str))
    common_codes = fii_codes.intersection(sitc_codes)

    if not common_codes:
        return pd.DataFrame()

    consensus_df = d_fii[
        d_fii["代號"].astype(str).isin(common_codes)
    ].copy()

    if consensus_df.empty:
        return pd.DataFrame()

    sitc_ratio_map = d_sitc.set_index("代號")["投本比(%)"].to_dict()
    consensus_df["投本比(%)"] = consensus_df["代號"].map(sitc_ratio_map).fillna(0.0)

    consensus_df["雙法人合佔比(%)"] = (
        consensus_df["外本比(%)"] + consensus_df["投本比(%)"]
    ).round(3)

    consensus_df = consensus_df[
        consensus_df["雙法人合佔比(%)"] > 0
    ].copy()

    if consensus_df.empty:
        return pd.DataFrame()

    common_temp_map = (
        common_groups.set_index("族群")["雙法人共同溫度"].to_dict()
        if not common_groups.empty else {}
    )

    consensus_df["雙法人共同溫度"] = (
        consensus_df["族群"].map(common_temp_map).fillna(0.0)
    )

    consensus_df["綜合得分"] = round(
        np.sqrt(consensus_df["雙法人合佔比(%)"].clip(lower=0)) * 0.6
        + np.sqrt(consensus_df["雙法人共同溫度"].clip(lower=0)) * 0.4,
        2
    )

    return consensus_df.sort_values(
        by=["綜合得分", "雙法人合佔比(%)"],
        ascending=False
    ).reset_index(drop=True)


df_consensus = build_market_consensus(df_fii, df_sitc, grp_common)


if search_query:
    for d in [df_consensus, df_amt, df_fii, df_sitc]:
        if not d.empty:
            match = d["代號"].str.contains(search_query) | d["官方名稱"].str.contains(search_query)
            d.drop(d.index[~match], inplace=True)


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
# 分頁介面
# =========================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🤝 雙法人共同擴散",
    "🔥 雙法人共識",
    "🌍 外資族群雷達",
    "🏛️ 投信族群雷達",
    "💰 成交值 TOP 100",
    "📋 法人個股 TOP 100",
])

with tab1:
    st.markdown("### 🤝 雙法人共同擴散（首要觀察）")
    st.info(
        "依照策略順序：先看『雙法人共同擴散』確認市場資金與族群熱度，"
        "再向下勾選有興趣的族群挑選個股！"
    )

    if not grp_common.empty:
        st.dataframe(
            grp_common,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")
        st.markdown("#### 🎯 互動選股：勾選族群以檢視個股")
        
        if not df_fii.empty and not df_sitc.empty:
            fii_temp = df_fii[["代號", "官方名稱", "族群", "外本比(%)", "漲跌幅(%)", "收盤價", "成交值(億)"]].copy()
            sitc_ratio_map = df_sitc.set_index("代號")["投本比(%)"].to_dict()
            fii_temp["投本比(%)"] = fii_temp["代號"].map(sitc_ratio_map).fillna(0.0)
            fii_temp["雙法人合佔比(%)"] = (fii_temp["外本比(%)"] + fii_temp["投本比(%)"]).round(3)
            
            selected_groups = []
            cols_checkbox = st.columns(3)
            
            for idx, g_name in enumerate(grp_common["族群"].tolist()):
                col_target = cols_checkbox[idx % 3]
                with col_target:
                    if st.checkbox(f"📁 {g_name}", key=f"chk_grp_{idx}"):
                        selected_groups.append(g_name)
            
            if selected_groups:
                st.markdown(f"**目前選取的族群：** `{', '.join(selected_groups)}`")
                filtered_stocks = fii_temp[fii_temp["族群"].isin(selected_groups)].sort_values(by="雙法人合佔比(%)", ascending=False)
                
                if not filtered_stocks.empty:
                    st.dataframe(filtered_stocks, use_container_width=True, hide_index=True)
                else:
                    st.info("所選族群中目前沒有符合條件的個股資料。")
            else:
                st.caption("👆 請在上方勾選一個或多個族群方框，即可展開對應的個股清單。")
    else:
        st.info("目前沒有雙法人共同擴散資料。")


with tab2:
    st.markdown("### 🔥 雙法人共識")
    st.info(
        "外資與投信各自獨立計算族群擴散；本頁只在最後觀察兩法人共同正向的個股，"
        "避免單一法人剛開始擴散時被另一法人尚未進場而過早排除。"
    )

    if not df_consensus.empty:
        ed_consensus = st.data_editor(
            df_consensus,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in df_consensus.columns if c not in ["族群"]],
            key="ed_consensus_top100",
        )

        if st.button("💾 儲存雙法人共識族群修改", key="btn_save_consensus"):
            update_map_from_editor(ed_consensus)
    else:
        st.info("目前無符合條件的雙法人共識個股。")


with tab3:
    st.markdown("### 🌍 外資族群雷達")
    st.caption("資料來源：外資買超 TOP 100；只把外本比 > 0 的股票視為正向籌碼。")

    if not grp_fii.empty:
        st.dataframe(grp_fii, use_container_width=True, hide_index=True)

        st.markdown("#### 外資族群正向個股")
        positive_fii = df_fii[df_fii["外本比(%)"] > 0].copy()

        if not positive_fii.empty:
            ed_fii_positive = st.data_editor(
                positive_fii,
                use_container_width=True,
                hide_index=True,
                disabled=[c for c in positive_fii.columns if c not in ["族群"]],
                key="ed_fii_positive",
            )

            if st.button("💾 儲存外資族群修改", key="btn_save_fii"):
                update_map_from_editor(ed_fii_positive)
        else:
            st.info("目前外資 TOP 100 中沒有外本比 > 0 的資料。")
    else:
        st.info("目前無外資族群資料。")


with tab4:
    st.markdown("### 🏛️ 投信族群雷達")
    st.caption("資料來源：投信買超 TOP 100；只把投本比 > 0 的股票視為正向籌碼。")

    if not grp_sitc.empty:
        st.dataframe(grp_sitc, use_container_width=True, hide_index=True)

        st.markdown("#### 投信族群正向個股")
        positive_sitc = df_sitc[df_sitc["投本比(%)"] > 0].copy()

        if not positive_sitc.empty:
            ed_sitc_positive = st.data_editor(
                positive_sitc,
                use_container_width=True,
                hide_index=True,
                disabled=[c for c in positive_sitc.columns if c not in ["族群"]],
                key="ed_sitc_positive",
            )

            if st.button("💾 儲存投信族群修改", key="btn_save_sitc"):
                update_map_from_editor(ed_sitc_positive)
        else:
            st.info("目前投信 TOP 100 中沒有投本比 > 0 的資料。")
    else:
        st.info("目前無投信族群資料。")


with tab5:
    st.markdown("### 💰 成交值 TOP 100")
    st.caption("成交值不直接決定法人籌碼強度；在族群雷達中作為『市場注意力』的獨立確認因子。")

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


with tab6:
    st.markdown("### 📋 法人個股 TOP 100")

    st.markdown("#### 🌍 外資買超 TOP 100")
    if not df_fii.empty:
        ed_fii = st.data_editor(
            df_fii,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in df_fii.columns if c not in ["族群"]],
            key="ed_fii_top100",
        )
        if st.button("💾 儲存外資個股族群修改", key="btn_save_fii_top100"):
            update_map_from_editor(ed_fii)
    else:
        st.info("目前無符合條件的外資買超資料。")

    st.markdown("#### 🏛️ 投信買超 TOP 100")
    if not df_sitc.empty:
        ed_sitc = st.data_editor(
            df_sitc,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in df_sitc.columns if c not in ["族群"]],
            key="ed_sitc_top100",
        )
        if st.button("💾 儲存投信個股族群修改", key="btn_save_sitc_top100"):
            update_map_from_editor(ed_sitc)
    else:
        st.info("目前無符合條件的投信買超資料。")