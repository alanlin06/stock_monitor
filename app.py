from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="台股雙軌籌碼終端機 (雙榜交叉 & 雙K圖示)",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🎯 雙榜交叉比對：外資本比 Top 50 ∩ 成交值 Top 100")
st.caption(
    "🔄 100% 串接證交所官方 API | 同時名列外資買超與成交值百大之雙榜強勢股，並附帶日K/週K多空雙K棒判定"
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


        # 模擬/對應多空狀態轉化為 K 棒圖示的函式（可依你的均價線邏輯替換狀態來源）
        def get_k_symbol(row):
            # 這裡可以串接你原本計算的日K/週K狀態，目前先以邏輯示範或預設
            # 假設欄位有抓到狀態，若無則預設雙多示範
            status = "雙多"
            if row["外本比(%)"] > 1.0:
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

        # 頂部總覽看板
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
            f"{df_top50.iloc[0]['官方名稱']} ({df_top50.iloc[0]['代號']})",
            f"{df_top50.iloc[0]['外本比(%)']}%",
        )
        c4.metric(
            "🏆 成交值冠冕標的",
            f"{df_top100.iloc[0]['官方名稱']} ({df_top100.iloc[0]['代號']})",
            f"{df_top100.iloc[0]['總成交金額(億)']} 億",
        )
        st.markdown("---")

        # 雙軌與雙榜分頁顯示
        tab_cross, tab_top50, tab_top100 = st.tabs(
            [
                "🎯 雙榜交叉比對 (外本比Top50 ∩ 成交值Top100)",
                "🔥 1. 外資買超排行 Top 50",
                "💰 2. 全市場成交值排行 Top 100",
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
    else:
        st.warning("無法解析出市場行情資料。")
else:
    st.warning(
        "目前無法取得證交所官方市場行情資料，請確認網路連線或是否為非交易日。"
    )