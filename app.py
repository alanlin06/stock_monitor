from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# ==================== 頁面設定 ====================
st.set_page_config(
    page_title="台股籌碼集中度",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("台股籌碼集中度")

# ==================== 側邊欄參數與即時搜尋 ====================
st.sidebar.header("實戰參數與查找")
search_query = st.sidebar.text_input(
    "🔍 側邊欄快速查找台股", placeholder="輸入代號或名稱 (例: 2330)"
)


@st.cache_data(ttl=600)
def fetch_twse_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    curr = datetime.now()
    dates = []

    while len(dates) < 25 and (datetime.now() - curr).days < 40:
        if curr.weekday() < 5:
            d_str = curr.strftime("%Y%m%d")
            test_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d_str}&selectType=ALL"
            try:
                res = requests.get(test_url, headers=headers, timeout=4)
                data = res.json()
                if (
                    data.get("stat") == "OK"
                    and len(data.get("data", [])) > 0
                ):
                    dates.append(d_str)
            except:
                pass
        curr -= timedelta(days=1)

    if not dates:
        return {}, {}, [], ""

    latest_date = dates[0]

    mi_url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999&date={latest_date}"
    market_dict = {}
    try:
        res = requests.get(mi_url, headers=headers, timeout=8)
        data = res.json()
        if data.get("stat") == "OK":
            for table in data.get("tables", []):
                if "data" in table:
                    for row in table["data"]:
                        code = row[0].strip()
                        if len(code) == 4:
                            try:
                                name = row[1].strip()
                                issued_shares_total_raw = float(
                                    row[2].replace(",", "")
                                )
                                close_price = float(
                                    row[8].replace(",", "")
                                )
                                change_pct = (
                                    float(row[10].replace(",", "%"))
                                    if len(row) > 10
                                    and row[10]
                                    and row[10].strip() != ""
                                    else 0.0
                                )

                                market_dict[code] = {
                                    "官方名稱": name,
                                    "發行總股數": issued_shares_total_raw,
                                    "收盤價": close_price,
                                    "漲跌幅(%)": change_pct,
                                }
                            except:
                                continue
    except Exception as e:
        print(f"MI_INDEX error: {e}")

    latest_foreign_shares = {}
    hist_foreign_shares = {}
    for i, d_str in enumerate(dates):
        t86_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d_str}&selectType=ALL"
        try:
            res = requests.get(t86_url, headers=headers, timeout=5)
            data = res.json()
            if data.get("stat") == "OK":
                raw_rows = data.get("data", [])
                day_map = {}
                for r in raw_rows:
                    code = r[0].strip()
                    if len(code) == 4:
                        try:
                            net_shares = int(r[4].replace(",", ""))
                            day_map[code] = net_shares
                            if i == 0:
                                latest_foreign_shares[code] = net_shares
                        except:
                            continue
                hist_foreign_shares[d_str] = day_map
        except:
            continue

    return market_dict, latest_foreign_shares, hist_foreign_shares, dates, latest_date


with st.spinner("⏳ 正在同步官方籌碼資料..."):
    (
        market_dict,
        latest_foreign_shares,
        hist_foreign_shares,
        target_dates,
        latest_date,
    ) = fetch_twse_data()

if latest_date:
    st.sidebar.success(
        f"📅 官方同步日：{latest_date[:4]}/{latest_date[4:6]}/{latest_date[6:]}"
    )

if market_dict:
    base_rows = []
    for code, info in market_dict.items():
        f_shares = latest_foreign_shares.get(code, 0)
        base_rows.append(
            {
                "代號": code,
                "官方名稱": info["官方名稱"],
                "發行總股數": info["發行總股數"],
                "收盤價": info["收盤價"],
                "漲跌幅(%)": info["漲跌幅(%)"],
                "外資買賣超股數": f_shares,
                "外資買賣超張數": f_shares / 1000,
            }
        )

    df_market = pd.DataFrame(base_rows)

    if not df_market.empty:

        def enrich_data(df):
            df = df.copy()
            df["外本比(%)"] = df.apply(
                lambda row: round(
                    (row["外資買賣超股數"] / row["發行總股數"]) * 100, 3
                )
                if row["發行總股數"] > 0
                else 0.0,
                axis=1,
            )

            def calc_20d_metrics(code):
                accumulated_shares = 0
                active_streak = 0

                for i, d_str in enumerate(target_dates[:20]):
                    day_map = hist_foreign_shares.get(d_str, {})
                    if code in day_map:
                        accumulated_shares += day_map[code]
                    else:
                        break

                for d_str in target_dates:
                    if (
                        code in hist_foreign_shares.get(d_str, {})
                        and hist_foreign_shares[d_str][code] > 0
                    ):
                        active_streak += 1
                    else:
                        break

                return accumulated_shares / 1000, active_streak

            res_20d = df["代號"].apply(calc_20d_metrics)
            df["近20日外資累積買超(張)"] = [r[0] for r in res_20d]
            df["連續買超天數"] = [r[1] for r in res_20d]

            def calc_efficiency(row):
                f_ratio = row["外本比(%)"]
                pct = row["漲跌幅(%)"]
                if f_ratio > 0:
                    return round(pct / f_ratio, 2)
                return 0.0

            df["單日資金攻擊效率"] = df.apply(calc_efficiency, axis=1)
            df["顯示名稱"] = df["官方名稱"]
            return df

        df_all_enriched = enrich_data(df_market)

        # 1. 準備外資買超 Top 50
        df_f_buy = (
            df_market[df_market["外資買賣超股數"] > 0]
            .sort_values(by="外資買賣超張數", ascending=False)
            .head(50)
        )
        df_top50 = enrich_data(df_f_buy)
        df_top50 = df_top50.sort_values(by="外本比(%)", ascending=False)
        df_top50.insert(0, "外本比排名", range(1, len(df_top50) + 1))

        # 2. 準備成交值 Top 100
        df_t_100 = df_market.sort_values(
            by="外資買賣超張數", ascending=False
        ).head(100)
        df_top100 = enrich_data(df_t_100)
        df_top100.insert(0, "排名", range(1, len(df_top100) + 1))

        # 3. 雙榜交叉比對
        top50_codes = set(df_top50["代號"])
        top100_codes = set(df_top100["代號"])
        cross_codes = top50_codes.intersection(top100_codes)

        df_cross = df_market[df_market["代號"].isin(cross_codes)].copy()
        df_cross = enrich_data(df_cross)
        df_cross = df_cross.sort_values(by="外本比(%)", ascending=False)
        df_cross.insert(0, "外本比排序", range(1, len(df_cross) + 1))

        # ==================== 頁面頂部：即時搜尋篩選面板 ====================
        st.markdown("### 🔍 任意台股快速查找與篩選")
        col_input, _ = st.columns([1, 3])
        with col_input:
            direct_search = st.text_input(
                "輸入代號或名稱",
                value=search_query,
                placeholder="例如: 2330 或 台積電",
                key="main_search_input",
            )

        if direct_search:
            matched_df = df_all_enriched[
                df_all_enriched["代號"].str.contains(direct_search)
                | df_all_enriched["官方名稱"].str.contains(direct_search)
            ]
            if not matched_df.empty:
                st.success(f"找到符合「{direct_search}」的股票：")
                st.dataframe(matched_df, use_container_width=True, hide_index=True)
            else:
                st.warning("查無此台股代號或名稱，請確認輸入是否正確。")
            st.markdown("---")

        # ==================== 分頁顯示排行榜 ====================
        tab_cross, tab_top50, tab_top100 = st.tabs(
            [
                "🎯 雙榜交叉比對",
                "🔥 1. 外資買超 Top 50",
                "💰 2. 成交值 Top 100",
            ]
        )

        with tab_cross:
            st.dataframe(
                df_cross, use_container_width=True, hide_index=True, height=500
            )

        with tab_top50:
            st.dataframe(
                df_top50, use_container_width=True, hide_index=True, height=500
            )

        with tab_top100:
            st.dataframe(
                df_top100, use_container_width=True, hide_index=True, height=500
            )

        # ==================== 重點權值股對加權指數影響點數計算 ====================
        st.markdown("---")
        st.subheader("⚡ 重點權值股對加權指數影響點數計算 (模擬試算)")

        top12_weights = [
            {
                "排名": 1,
                "股票": "台積電",
                "代號": "2330",
                "權重": 41.4777,
                "每漲1元影響點數": 8.43,
            },
            {
                "排名": 2,
                "股票": "聯發科",
                "代號": "2454",
                "權重": 4.1867,
                "每漲1元影響點數": 0.48,
            },
            {
                "排名": 3,
                "股票": "台達電",
                "代號": "2308",
                "權重": 3.1786,
                "每漲1元影響點數": 0.78,
            },
            {
                "排名": 4,
                "股票": "鴻海",
                "代號": "2317",
                "權重": 2.3325,
                "每漲1元影響點數": 4.59,
            },
            {
                "排名": 5,
                "股票": "日月光投控",
                "代號": "3711",
                "權重": 1.7363,
                "每漲1元影響點數": 1.33,
            },
            {
                "排名": 6,
                "股票": "富邦金",
                "代號": "2881",
                "權重": 1.3415,
                "每漲1元影響點數": 3.91,
            },
            {
                "排名": 7,
                "股票": "台光電",
                "代號": "2383",
                "權重": 1.3071,
                "每漲1元影響點數": 0.10,
            },
            {
                "排名": 8,
                "股票": "南亞",
                "代號": "1303",
                "權重": 1.2791,
                "每漲1元影響點數": 0.35,
            },
            {
                "排名": 9,
                "股票": "南亞科",
                "代號": "2408",
                "權重": 1.1190,
                "每漲1元影響點數": 0.15,
            },
            {
                "排名": 10,
                "股票": "欣興",
                "代號": "3037",
                "權重": 1.0889,
                "每漲1元影響點數": 0.38,
            },
            {
                "排名": 11,
                "股票": "聯電",
                "代號": "2303",
                "權重": 1.0790,
                "每漲1元影響點數": 1.10,
            },
            {
                "排名": 12,
                "股票": "國泰金",
                "代號": "2882",
                "權重": 1.0780,
                "每漲1元影響點數": 4.79,
            },
        ]

        calc_rows = []
        total_impact_points = 0.0

        for item in top12_weights:
            c = item["代號"]
            latest_px, price_change = 0.0, 0.0
            try:
                for suffix in [".TW", ".TWO"]:
                    t_df = yf.download(
                        f"{c}{suffix}",
                        period="2d",
                        interval="1d",
                        progress=False,
                    )
                    if not t_df.empty:
                        if isinstance(t_df.columns, pd.MultiIndex):
                            t_df.columns = t_df.columns.droplevel(1)
                        if "Close" in t_df.columns:
                            latest_px = float(t_df["Close"].iloc[-1])
                            prev_px = float(
                                t_df["Close"].iloc[-2]
                                if len(t_df) > 1
                                else latest_px
                            )
                            price_change = round(latest_px - prev_px, 2)
                            break
            except:
                pass

            impact_pts = round(price_change * item["每漲1元影響點數"], 2)
            total_impact_points += impact_pts

            calc_rows.append(
                {
                    "排名": item["排名"],
                    "股票": item["股票"],
                    "代號": c,
                    "權重(%)": item["權重"],
                    "最新股價": latest_px,
                    "每漲1元影響點數": item["每漲1元影響點數"],
                    "漲跌金額": price_change,
                    "影響點數": impact_pts,
                }
            )

        df_impact = pd.DataFrame(calc_rows)
        st.dataframe(df_impact, use_container_width=True, hide_index=True)

        st.metric(
            label="📊 重點權值股總影響點數",
            value=f"{round(total_impact_points, 2)} 點",
        )