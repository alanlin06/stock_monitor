from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="台股雙軌籌碼終端機 (外本比核心版)",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚡ 台股雙軌籌碼透視終端機 (全面以【外本比】為核心)")
st.caption("🔄 100% 串接證交所官方 MI_INDEX 與 T86 API | 聚焦外資佔發行總股數比例精準透視")


@st.cache_data(ttl=600)
def fetch_twse_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    curr = datetime.now()
    dates = []

    while len(dates) < 5 and (datetime.now() - curr).days < 20:
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

    # 1. 抓取 MI_INDEX 取得官方發行總股數、總成交金額、成交量、收盤價與成交均價 (VWAP)
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
                                )  # 官方發行總股數
                                total_turnover = float(
                                    row[3].replace(",", "")
                                )  # 總成交金額
                                trading_volume = float(
                                    row[4].replace(",", "")
                                )  # 成交股數
                                close_price = float(
                                    row[7].replace(",", "")
                                )
                                change_pct = (
                                    float(row[10].replace(",", "%"))
                                    if len(row) > 10
                                    and row[10]
                                    and row[10].strip() != ""
                                    else 0.0
                                )

                                vwap = (
                                    (total_turnover / trading_volume)
                                    if trading_volume > 0
                                    else close_price
                                )

                                market_dict[code] = {
                                    "官方名稱": name,
                                    "發行總股數": issued_shares_total_raw,
                                    "總成交金額_元": total_turnover,
                                    "收盤價": close_price,
                                    "成交均價": round(vwap, 2),
                                    "漲跌幅(%)": change_pct,
                                }
                            except:
                                continue
    except Exception as e:
        print(f"MI_INDEX error: {e}")

    # 2. 抓取多日 T86 三大法人買賣超
    hist_foreign_shares = {}
    latest_foreign_shares = {}
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
                            net_shares = int(
                                r[4].replace(",", "")
                            )  # 外資買賣超原始股數
                            day_map[code] = net_shares
                            if i == 0:
                                latest_foreign_shares[code] = net_shares
                        except:
                            continue
                hist_foreign_shares[d_str] = day_map
        except:
            continue

    return market_dict, latest_foreign_shares, hist_foreign_shares, dates, latest_date


with st.spinner("⚡ 正在同步證交所官方市場資料與外本比計算中..."):
    (
        market_dict,
        latest_foreign_shares,
        hist_foreign_shares,
        target_dates,
        latest_date,
    ) = fetch_twse_data()

if latest_date:
    st.sidebar.success(
        f"📅 官方同步交易日：{latest_date[:4]}/{latest_date[4:6]}/{latest_date[6:]}"
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
                "總成交金額_元": info["總成交金額_元"],
                "總成交金額(億)": round(info["總成交金額_元"] / 1e8, 2),
                "收盤價": info["收盤價"],
                "成交均價": info["成交均價"],
                "漲跌幅(%)": info["漲跌幅(%)"],
                "外資買賣超股數": f_shares,
                "外資買賣超張數": f_shares / 1000,
            }
        )

    df_market = pd.DataFrame(base_rows)

    if not df_market.empty:

        # 共用計算函式：計算外本比與連續買超天數
        def enrich_data(df):
            df = df.copy()
            df["外資買賣超金額_元"] = (
                df["外資買賣超張數"] * 1000 * df["成交均價"]
            )
            df["外資買賣超金額(億)"] = round(df["外資買賣超金額_元"] / 1e8, 2)
            df["外本比(%)"] = df.apply(
                lambda row: round(
                    (row["外資買賣超股數"] / row["發行總股數"]) * 100, 3
                )
                if row["發行總股數"] > 0
                else 0.0,
                axis=1,
            )

            def calc_streak(code):
                streak = 0
                for d_str in target_dates:
                    if code in hist_foreign_shares.get(d_str, {}):
                        if hist_foreign_shares[d_str][code] > 0:
                            streak += 1
                        else:
                            break
                    else:
                        break
                return streak

            df["連續買超天數"] = df["代號"].apply(calc_streak)
            return df

        # 1. 準備外資買超 Top 50（並改以「外本比」由高到低排序）
        df_f_buy = (
            df_market[df_market["外資買賣超股數"] > 0]
            .sort_values(by="外資買賣超張數", ascending=False)
            .head(50)
        )
        df_top50 = enrich_data(df_f_buy)
        df_top50 = df_top50.sort_values(by="外本比(%)", ascending=False)
        df_top50.insert(0, "外本比排名", range(1, len(df_top50) + 1))

        # 2. 準備成交值 Top 100（同樣計算外本比）
        df_t_100 = df_market.sort_values(
            by="總成交金額_元", ascending=False
        ).head(100)
        df_top100 = enrich_data(df_t_100)
        df_top100.insert(0, "成交值排名", range(1, len(df_top100) + 1))

        # 3. 雙榜交叉比對 (Top 50 ∩ Top 100)，強制全面以「外本比」排序
        top50_codes = set(df_top50["代號"])
        top100_codes = set(df_top100["代號"])
        cross_codes = top50_codes.intersection(top100_codes)

        df_cross = df_market[df_market["代號"].isin(cross_codes)].copy()
        df_cross = enrich_data(df_cross)
        df_cross = df_cross.sort_values(by="外本比(%)", ascending=False)
        df_cross.insert(0, "外本比排序", range(1, len(df_cross) + 1))

        # ==================== 頂部總覽看板（全外本比導向） ====================
        top_cross_row = (
            df_cross.iloc[0] if not df_cross.empty else df_top50.iloc[0]
        )
        top_50_row = df_top50.iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "🔥 雙榜交集標的數",
            f"{len(df_cross)} 檔",
            "同時名列外資Top50與成交值Top100",
        )
        c2.metric(
            "👑 雙榜最高外本比",
            f"{top_cross_row['官方名稱']} ({top_cross_row['代號']})",
            f"{top_cross_row['外本比(%)']}% (佔發行股數)",
        )
        c3.metric(
            "🌟 外資買超 Top50 最高外本比",
            f"{top_50_row['官方名稱']} ({top_50_row['代號']})",
            f"{top_50_row['外本比(%)']}%",
        )
        c4.metric(
            "📊 雙榜交集平均外本比",
            f"{round(df_cross['外本比(%)'].mean(), 3)} %"
            if not df_cross.empty
            else "0.0 %",
            "強勢籌碼集中度指標",
        )
        st.markdown("---")

        # ==================== 三頁籤分頁顯示 ====================
        tab_cross, tab_top50, tab_top100 = st.tabs(
            [
                "🎯 雙榜交叉比對 (外本比排序)",
                "🔥 1. 外資買超 Top 50 (外本比排序)",
                "💰 2. 全市場成交值 Top 100 (含外本比)",
            ]
        )

        with tab_cross:
            col_c1, col_c2 = st.columns([4, 1])
            with col_c1:
                st.subheader(
                    "🎯 雙榜交集強勢清單 (同時在買超Top50與成交值Top100，完全依外本比排序)"
                )
            with col_c2:
                export_cross = df_cross[
                    [
                        "外本比排序",
                        "代號",
                        "官方名稱",
                        "外本比(%)",
                        "外資買賣超張數",
                        "外資買賣超金額(億)",
                        "總成交金額(億)",
                        "成交均價",
                        "連續買超天數",
                        "漲跌幅(%)",
                    ]
                ]
                st.download_button(
                    label="📥 下載交叉外本比 CSV",
                    data=export_cross.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"雙榜交叉外本比排行_{latest_date}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            st.dataframe(
                export_cross,
                column_config={
                    "外本比排序": "外本比排序",
                    "代號": "代號",
                    "官方名稱": "名稱",
                    "外本比(%)": st.column_config.NumberColumn(
                        "🔥 外本比 (佔發行股數)", format="%.3f %%"
                    ),
                    "外資買賣超張數": st.column_config.NumberColumn(
                        "📈 外資買超張數", format="%d 張"
                    ),
                    "外資買賣超金額(億)": st.column_config.NumberColumn(
                        "💵 買超金額", format="%.2f 億"
                    ),
                    "總成交金額(億)": st.column_config.NumberColumn(
                        "💰 總成交金額", format="%.2f 億"
                    ),
                    "成交均價": st.column_config.NumberColumn(
                        "成交均價", format="%.2f"
                    ),
                    "連續買超天數": st.column_config.NumberColumn(
                        "連買天數", format="%d 天"
                    ),
                    "漲跌幅(%)": st.column_config.NumberColumn(
                        "漲跌幅", format="%.2f %%"
                    ),
                },
                use_container_width=True,
                hide_index=True,
                height=600,
            )

        with tab_top50:
            col_1, col_2 = st.columns([4, 1])
            with col_1:
                st.subheader(
                    "📋 外資買超 Top 50 完整排行 (已依外本比由高到低排序)"
                )
            with col_2:
                export_50 = df_top50[
                    [
                        "外本比排名",
                        "代號",
                        "官方名稱",
                        "外本比(%)",
                        "外資買賣超張數",
                        "成交均價",
                        "外資買賣超金額(億)",
                        "連續買超天數",
                        "漲跌幅(%)",
                    ]
                ]
                st.download_button(
                    label="📥 下載外資Top50 CSV",
                    data=export_50.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"外資買超Top50外本比_{latest_date}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            st.dataframe(
                export_50,
                column_config={
                    "外本比排名": "外本比排名",
                    "代號": "代號",
                    "官方名稱": "名稱",
                    "外本比(%)": st.column_config.NumberColumn(
                        "🔥 外本比 (佔發行股數)", format="%.3f %%"
                    ),
                    "外資買賣超張數": st.column_config.NumberColumn(
                        "📈 外資買超張數", format="%d 張"
                    ),
                    "成交均價": st.column_config.NumberColumn(
                        "成交均價", format="%.2f"
                    ),
                    "外資買賣超金額(億)": st.column_config.NumberColumn(
                        "💰 買超金額", format="%.2f 億"
                    ),
                    "連續買超天數": st.column_config.NumberColumn(
                        "連買天數", format="%d 天"
                    ),
                    "漲跌幅(%)": st.column_config.NumberColumn(
                        "漲跌幅", format="%.2f %%"
                    ),
                },
                use_container_width=True,
                hide_index=True,
                height=600,
            )

        with tab_top100:
            col_3, col_4 = st.columns([4, 1])
            with col_3:
                st.subheader(
                    "📋 全市場成交值前 100 名股票 (含外資籌碼與外本比對照)"
                )
            with col_4:
                export_100 = df_top100[
                    [
                        "成交值排名",
                        "代號",
                        "官方名稱",
                        "總成交金額(億)",
                        "外本比(%)",
                        "外資買賣超張數",
                        "成交均價",
                        "外資買賣超金額(億)",
                        "連續買超天數",
                        "漲跌幅(%)",
                    ]
                ]
                st.download_button(
                    label="📥 下載成交值Top100 CSV",
                    data=export_100.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"成交值Top100外本比_{latest_date}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            st.dataframe(
                export_100,
                column_config={
                    "成交值排名": "成交值排名",
                    "代號": "代號",
                    "官方名稱": "名稱",
                    "總成交金額(億)": st.column_config.NumberColumn(
                        "💰 總成交金額", format="%.2f 億"
                    ),
                    "外本比(%)": st.column_config.NumberColumn(
                        "🔥 外本比 (佔發行股數)", format="%.3f %%"
                    ),
                    "外資買賣超張數": st.column_config.NumberColumn(
                        "📈 外資買賣超張數 (可正負)", format="%d 張"
                    ),
                    "成交均價": st.column_config.NumberColumn(
                        "成交均價", format="%.2f"
                    ),
                    "外資買賣超金額(億)": st.column_config.NumberColumn(
                        "💵 買賣超金額", format="%.2f 億"
                    ),
                    "連續買超天數": st.column_config.NumberColumn(
                        "連買天數", format="%d 天"
                    ),
                    "漲跌幅(%)": st.column_config.NumberColumn(
                        "漲跌幅", format="%.2f %%"
                    ),
                },
                use_container_width=True,
                hide_index=True,
                height=600,
            )

    else:
        st.warning("無法解析出市場行情資料。")
else:
    st.warning(
        "目前無法取得證交所官方市場行情資料，請確認網路連線或是否為非交易日。"
    )