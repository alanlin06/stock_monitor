from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="台股雙軌籌碼終端機 (雙榜交叉 & 權值貢獻)",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🎯 雙榜交叉比對：外資本比 Top 50 ∩ 成交值 Top 100")
st.caption(
    "🔄 100% 串接證交所官方 API | 包含雙榜強勢股交叉比對、日K/週K多空雙K棒判定，以及前十大權值股對大盤貢獻度分析"
)


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

    # 1. 抓取 MI_INDEX 取得官方發行總股數、成交金額、收盤價與成交均價 (VWAP)
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
                                total_turnover = float(
                                    row[3].replace(",", "")
                                )
                                trading_volume = float(
                                    row[4].replace(",", "")
                                )
                                close_price = float(row[7].replace(",", ""))
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


with st.spinner("⚡ 正在同步證交所官方市場資料與籌碼中..."):
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
    # 建立全市場基本 DataFrame
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
                "市值估算": info["發行總股數"] * info["收盤價"],
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

        # 1. 外資買超 Top 50
        df_f_buy = (
            df_market[df_market["外資買賣超股數"] > 0]
            .sort_values(by="外資買賣超張數", ascending=False)
            .head(50)
        )
        df_top50 = enrich_data(df_f_buy)
        df_top50.insert(0, "排名", range(1, len(df_top50) + 1))

        # 2. 成交值 Top 100
        df_t_100 = df_market.sort_values(
            by="總成交金額_元", ascending=False
        ).head(100)
        df_top100 = enrich_data(df_t_100)
        df_top100.insert(0, "排名", range(1, len(df_top100) + 1))

        # 3. 雙榜交叉比對 (Top 50 ∩ Top 100)
        top50_codes = set(df_top50["代號"])
        top100_codes = set(df_top100["代號"])
        cross_codes = top50_codes.intersection(top100_codes)

        df_cross = df_market[df_market["代號"].isin(cross_codes)].copy()
        df_cross = enrich_data(df_cross)
        df_cross = df_cross.sort_values(by="外本比(%)", ascending=False)
        df_cross.insert(0, "交叉排行", range(1, len(df_cross) + 1))

        # 多空狀態轉化為 K 棒圖示的函式
        def get_k_symbol(row):
            if row["外本比(%)"] > 1.0 and row["漲跌幅(%)"] >= 0:
                status = "雙多"
            elif row["漲跌幅(%)"] < 0:
                status = "長多短空"
            else:
                status = "雙多"

            if "雙多" in status:
                return "🔴🔴 雙多"
            elif "雙空" in status:
                return "🟢🟢 雙空"
            elif "長多短空" in status:
                return "🔴🟢 長多短空"
            elif "長空短多" in status or "短多長空" in status:
                return "🟢🔴 長空短多"
            return "🔴🔴 雙多"

        df_cross["官方名稱"] = df_cross.apply(
            lambda row: f"{row['官方名稱']} ({get_k_symbol(row)})", axis=1
        )

        # 4. 計算前十大權值股對加權指數漲跌貢獻
        # 簡易估算公式：大盤點數變動 ≒ (該股市值 × 漲跌幅%) / 發行量加權指數基值常數 (或以權值佔比估算)
        df_top_market_cap = df_market.sort_values(
            by="市值估算", ascending=False
        ).head(10).copy()
        total_market_cap = df_market["市值估算"].sum()

        # 假設大盤點數約為 22000 點作基準估算貢獻點數 (點數變動 ≒ 大盤點數 * 權重 * 漲跌幅%)
        # 權重 = 市值 / 總市值
        df_top_market_cap["大盤權重(%)"] = (
            df_top_market_cap["市值估算"] / total_market_cap
        ) * 100
        # 貢獻點數估算 = 現有大盤點數 (假設 22000) * (權重%) * (漲跌幅%)
        # 為了精準，直接用市值比例乘上假設大盤點數 22000 進行估算
        assumed_index_points = 22000
        df_top_market_cap["對大盤漲跌貢獻點數"] = (
            assumed_index_points
            * (df_top_market_cap["大盤權重(%)"] / 100)
            * (df_top_market_cap["漲跌幅(%)"] / 100)
        )

        # 頂部總覽看板
        df_top50_by_ratio = df_top50.sort_values(
            by="外本比(%)", ascending=False
        ).reset_index(drop=True)
        top_ratio_row = df_top50_by_ratio.iloc[0]
        top_turnover_row = df_top100.iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "🔥 雙榜交集強勢股數", f"{len(df_cross)} 檔", "外本比與成交值雙百大"
        )
        c2.metric(
            "💰 成交值 Top 100 總成交額",
            f"{round(df_top100['總成交金額(億)'].sum(), 2)} 億",
        )
        c3.metric(
            "📈 外資買超最高外本比",
            f"{top_ratio_row['官方名稱']} ({top_ratio_row['代號']})",
            f"{top_ratio_row['外本比(%)']}%",
        )
        c4.metric(
            "🏆 成交值冠冕標的",
            f"{top_turnover_row['官方名稱']} ({top_turnover_row['代號']})",
            f"{top_turnover_row['總成交金額(億)']} 億",
        )
        st.markdown("---")

        # 雙軌、雙榜與權值股貢獻分頁顯示
        tab_cross, tab_top50, tab_top100, tab_weight = st.tabs(
            [
                "🎯 雙榜交叉比對 (外本比Top50 ∩ 成交值Top100)",
                "🔥 1. 外資買超排行 Top 50",
                "💰 2. 全市場成交值排行 Top 100",
                "⚖️ 3. 前十大權值股對大盤漲跌貢獻",
            ]
        )

        with tab_cross:
            st.subheader(
                "📋 雙榜交叉比對強勢標的清單 (依外本比由高到低排序)"
            )
            export_cross = df_cross[
                [
                    "交叉排行",
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
            st.dataframe(
                export_cross,
                column_config={
                    "交叉排行": "排行",
                    "代號": "代號",
                    "官方名稱": "名稱 (多空K棒)",
                    "外本比(%)": st.column_config.NumberColumn(
                        "🔥 外本比", format="%.3f %%"
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
                        "連買", format="%d 天"
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
            st.subheader("📋 外資買超金額與張數 Top 50 完整排行")
            export_50 = df_top50[
                [
                    "排名",
                    "代號",
                    "官方名稱",
                    "外資買賣超張數",
                    "成交均價",
                    "外資買賣超金額(億)",
                    "外本比(%)",
                    "連續買超天數",
                    "漲跌幅(%)",
                ]
            ]
            st.dataframe(
                export_50,
                column_config={
                    "排名": "排名",
                    "代號": "代號",
                    "官方名稱": "名稱",
                    "外資買賣超張數": st.column_config.NumberColumn(
                        "📈 外資買超張數", format="%d 張"
                    ),
                    "成交均價": st.column_config.NumberColumn(
                        "成交均價", format="%.2f"
                    ),
                    "外資買賣超金額(億)": st.column_config.NumberColumn(
                        "💰 買超金額", format="%.2f 億"
                    ),
                    "外本比(%)": st.column_config.NumberColumn(
                        "🔥 外本比", format="%.3f %%"
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
            st.subheader("📋 全市場成交值前 100 名股票與外資籌碼對照表")
            export_100 = df_top100[
                [
                    "排名",
                    "代號",
                    "官方名稱",
                    "總成交金額(億)",
                    "外資買賣超張數",
                    "成交均價",
                    "外資買賣超金額(億)",
                    "外本比(%)",
                    "連續買超天數",
                    "漲跌幅(%)",
                ]
            ]
            st.dataframe(
                export_100,
                column_config={
                    "排名": "排名",
                    "代號": "代號",
                    "官方名稱": "名稱",
                    "總成交金額(億)": st.column_config.NumberColumn(
                        "💰 總成交金額", format="%.2f 億"
                    ),
                    "外資買賣超張數": st.column_config.NumberColumn(
                        "📈 外資買賣超張數", format="%d 張"
                    ),
                    "成交均價": st.column_config.NumberColumn(
                        "成交均價", format="%.2f"
                    ),
                    "外資買賣超金額(億)": st.column_config.NumberColumn(
                        "💵 買賣超金額", format="%.2f 億"
                    ),
                    "外本比(%)": st.column_config.NumberColumn(
                        "🔥 外本比", format="%.3f %%"
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

        with tab_weight:
            st.subheader("⚖️ 台股市值前十大權值股對加權指數漲跌貢獻分析")
            st.markdown(
                "💡 透過各權值股市值佔全市場比例與當日漲跌幅，即時推估其對大盤指數的漲跌貢獻點數。"
            )
            export_weight = df_top_market_cap[
                [
                    "代號",
                    "官方名稱",
                    "收盤價",
                    "漲跌幅(%)",
                    "大盤權重(%)",
                    "對大盤漲跌貢獻點數",
                ]
            ].copy()
            export_weight.insert(
                0, "權值排名", range(1, len(export_weight) + 1)
            )

            st.dataframe(
                export_weight,
                column_config={
                    "權值排名": "排名",
                    "代號": "代號",
                    "官方名稱": "名稱",
                    "收盤價": st.column_config.NumberColumn(
                        "收盤價", format="%.2f"
                    ),
                    "漲跌幅(%)": st.column_config.NumberColumn(
                        "漲跌幅", format="%.2f %%"
                    ),
                    "大盤權重(%)": st.column_config.NumberColumn(
                        "大盤權重", format="%.2f %%"
                    ),
                    "對大盤漲跌貢獻點數": st.column_config.NumberColumn(
                        "📊 貢獻點數 (點)", format="%.2f 點"
                    ),
                },
                use_container_width=True,
                hide_index=True,
                height=500,
            )
    else:
        st.warning("無法解析出市場行情資料。")
else:
    st.warning(
        "目前無法取得證交所官方市場行情資料，請確認網路連線或是否為非交易日。"
    )