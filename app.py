from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st

# ==================== 頁面設定 ====================
st.set_page_config(
    page_title="台股籌碼集中度 (外本比 + 投本比 + 法人同步指標)",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("台股籌碼集中度 (外本比、投本比與法人動向雙A追蹤)")

# ==================== 側邊欄參數與即時搜尋 ====================
st.sidebar.header("實戰參數與查找")
search_query = st.sidebar.text_input(
    "🔍 側邊欄快速查找台股", placeholder="輸入代號或名稱 (例: 2330)"
)


@st.cache_data(ttl=600)
def fetch_twse_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    curr = datetime.now()
    dates = []

    # 往前尋找最近的 25 個交易日 (針對外資、投信 T86)
    while len(dates) < 25 and (datetime.now() - curr).days < 60:
        if curr.weekday() < 5:
            d_str = curr.strftime("%Y%m%d")
            test_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d_str}&selectType=ALL"
            try:
                res = requests.get(test_url, headers=headers, timeout=3)
                if res.status_code == 200:
                    data = res.json()
                    if (
                        data.get("stat") == "OK"
                        and len(data.get("data", [])) > 0
                    ):
                        dates.append(d_str)
            except Exception:
                pass
        curr -= timedelta(days=1)

    if not dates:
        return {}, {}, {}, [], ""

    latest_date = dates[0]

    # 抓取當日收盤行情 (MI_INDEX)
    mi_url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999&date={latest_date}"
    market_dict = {}
    try:
        res = requests.get(mi_url, headers=headers, timeout=6)
        if res.status_code == 200:
            data = res.json()
            if data.get("stat") == "OK":
                for table in data.get("tables", []):
                    if "data" in table:
                        for row in table["data"]:
                            if len(row) > 10:
                                code = row[0].strip()
                                if len(code) == 4 and code.isdigit():
                                    try:
                                        name = row[1].strip()
                                        issued_shares_total_raw = float(
                                            row[2].replace(",", "")
                                        )
                                        close_price = float(
                                            row[8].replace(",", "")
                                        )

                                        market_dict[code] = {
                                            "官方名稱": name,
                                            "發行總股數": issued_shares_total_raw,
                                            "收盤價": close_price,
                                        }
                                    except Exception:
                                        continue
    except Exception as e:
        print(f"MI_INDEX error: {e}")

    latest_foreign_shares = {}
    latest_trust_shares = {}
    hist_foreign_shares = {}
    for i, d_str in enumerate(dates):
        t86_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d_str}&selectType=ALL"
        try:
            res = requests.get(t86_url, headers=headers, timeout=4)
            if res.status_code == 200:
                data = res.json()
                if data.get("stat") == "OK":
                    raw_rows = data.get("data", [])
                    day_map = {}
                    for r in raw_rows:
                        if len(r) > 10:
                            code = r[0].strip()
                            if len(code) == 4 and code.isdigit():
                                try:
                                    # 外資買賣超股數 (index 4)
                                    net_foreign = int(r[4].replace(",", ""))
                                    # 投信買賣超股數 (index 10)
                                    net_trust = int(r[10].replace(",", ""))

                                    day_map[code] = net_foreign
                                    if i == 0:
                                        latest_foreign_shares[code] = (
                                            net_foreign
                                        )
                                        latest_trust_shares[code] = net_trust
                                except Exception:
                                    continue
                    hist_foreign_shares[d_str] = day_map
        except Exception:
            continue

    return (
        market_dict,
        latest_foreign_shares,
        latest_trust_shares,
        hist_foreign_shares,
        dates,
        latest_date,
    )


with st.spinner("⏳ 正在同步官方外資與投信籌碼資料，請稍候..."):
    (
        market_dict,
        latest_foreign_shares,
        latest_trust_shares,
        hist_foreign_shares,
        target_dates,
        latest_date,
    ) = fetch_twse_data()

if latest_date:
    st.sidebar.success(
        f"📅 官方同步日：{latest_date[:4]}/{latest_date[4:6]}/{latest_date[6:]}"
    )
else:
    st.warning("⚠️ 無法取得證交所官方資料，請檢查網路連線或稍後再試。")

if market_dict:
    base_rows = []
    for code, info in market_dict.items():
        f_shares = latest_foreign_shares.get(code, 0)
        t_shares = latest_trust_shares.get(code, 0)

        base_rows.append(
            {
                "代號": code,
                "官方名稱": info["官方名稱"],
                "發行總股數": info["發行總股數"],
                "收盤價": info["收盤價"],
                "外資買賣超股數": f_shares,
                "外資買賣超張數": f_shares / 1000,
                "投信買賣超股數": t_shares,
                "投信買賣超張數": t_shares / 1000,
            }
        )

    df_market = pd.DataFrame(base_rows)

    if not df_market.empty:

        def enrich_data(df):
            df = df.copy()
            # 外本比 (%)
            df["外本比(%)"] = df.apply(
                lambda row: round(
                    (row["外資買賣超股數"] / row["發行總股數"]) * 100, 3
                )
                if row["發行總股數"] > 0
                else 0.0,
                axis=1,
            )

            # 投本比 (%)
            df["投本比(%)"] = df.apply(
                lambda row: round(
                    (row["投信買賣超股數"] / row["發行總股數"]) * 100, 3
                )
                if row["發行總股數"] > 0
                else 0.0,
                axis=1,
            )

            def calc_20d_metrics(code):
                accumulated_shares = 0
                active_streak = 0

                for d_str in target_dates[:20]:
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

            # 依照需求：在顯示名稱後方備註外資與投信的同步動向（雙買、對做、或單邊）
            def format_display_name(row):
                name = row["官方名稱"]
                f_net = row["外資買賣超股數"]
                t_net = row["投信買賣超股數"]

                if f_net > 0 and t_net > 0:
                    return f"{name} [🔥 雙A合擊: 雙買]"
                elif f_net < 0 and t_net < 0:
                    return f"{name} [❄️ 雙A雙賣]"
                elif f_net > 0 and t_net < 0:
                    return f"{name} [⚠️ 法人對做: 外買投賣]"
                elif f_net < 0 and t_net > 0:
                    return f"{name} [⚠️ 法人對做: 外賣投買]"
                elif f_net > 0:
                    return f"{name} [外資獨買]"
                elif t_net > 0:
                    return f"{name} [投信獨買]"
                else:
                    return name

            df["顯示名稱"] = df.apply(format_display_name, axis=1)
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
                df_cross, use_container_width=True, hide_index=True, height=600
            )

        with tab_top50:
            st.dataframe(
                df_top50, use_container_width=True, hide_index=True, height=600
            )

        with tab_top100:
            st.dataframe(
                df_top100, use_container_width=True, hide_index=True, height=600
            )