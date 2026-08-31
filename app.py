from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# ==================== 頁面設定 ====================
st.set_page_config(
    page_title="台股籌碼資金集中度",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("台股籌碼資金集中度")
st.caption(
    "🔄 100% 串接證交所官方資料 | 結合 20日波段外資主導、外本比雙榜交集與盤中即時盯盤"
)

# ==================== 側邊欄參數設定 ====================
st.sidebar.header("實戰參數設定")
bias_limit = st.sidebar.slider("MA20 乖離過熱警戒 (%)", 5.0, 15.0, 8.0, 0.5)


@st.cache_data(ttl=600)
def fetch_twse_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    curr = datetime.now()
    dates = []

    # 為了計算 20 日累積波段，抓取近 25 個交易日
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
                                total_turnover = float(
                                    row[3].replace(",", "")
                                )
                                trading_volume = float(
                                    row[4].replace(",", "")
                                )
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


with st.spinner("⏳ 正在同步證交所官方市場資料與計算 20 日波段籌碼中..."):
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

            # 1. 20日波段指標計算 (累積買超與連續天數)
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

            # 2. 單日資金攻擊效率計算 (漲跌幅 / 外本比)
            def calc_efficiency(row):
                f_ratio = row["外本比(%)"]
                pct = row["漲跌幅(%)"]
                if f_ratio > 0:
                    return round(pct / f_ratio, 2)
                return 0.0

            df["單日資金攻擊效率"] = df.apply(calc_efficiency, axis=1)

            # 3. 燈號判定 (結合 20日波段、效率與乖離過熱防護)
            def get_swing_signal(row):
                f_ratio = row["外本比(%)"]
                accum_20d = row["近20日外資累積買超(張)"]
                streak = row["連續買超天數"]
                efficiency = row["單日資金攻擊效率"]
                pct = row["漲跌幅(%)"]

                # 第一層濾網：20日波段必須是多頭
                if accum_20d > 0 and (streak >= 2 or f_ratio > 0.02):
                    if efficiency > 0.5 and pct > 0:
                        return "🔴 波段主升(高效攻擊)"
                    else:
                        return "🟡 波段穩健(蓄勢中)"
                else:
                    return "🟢 籌碼鬆動/非波段"

            df["波段攻擊燈號"] = df.apply(get_swing_signal, axis=1)
            df["顯示名稱"] = df["官方名稱"] + " " + df["波段攻擊燈號"]
            return df

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
            by="總成交金額_元", ascending=False
        ).head(100)
        df_top100 = enrich_data(df_t_100)
        df_top100.insert(0, "成交值排名", range(1, len(df_top100) + 1))

        # 3. 雙榜交叉比對 (外資Top50 與 成交值Top100)
        top50_codes = set(df_top50["代號"])
        top100_codes = set(df_top100["代號"])
        cross_codes = top50_codes.intersection(top100_codes)

        df_cross = df_market[df_market["代號"].isin(cross_codes)].copy()
        df_cross = enrich_data(df_cross)
        df_cross = df_cross.sort_values(by="外本比(%)", ascending=False)
        df_cross.insert(0, "外本比排序", range(1, len(df_cross) + 1))

        # ==================== 頂部總覽看板 ====================
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
            "籌碼集中度指標",
        )
        st.markdown("---")

        # ==================== 分頁顯示 ====================
        tab_cross, tab_top50, tab_top100 = st.tabs(
            [
                "🎯 雙榜交叉比對 (外資Top50 × 成交值Top100)",
                "🔥 1. 外資買超 Top 50",
                "💰 2. 全市場成交值 Top 100",
            ]
        )

        selected_stock_code = None

        def render_interactive_table(df, key_name):
            export_df = df.copy()
            event = st.dataframe(
                export_df,
                use_container_width=True,
                hide_index=True,
                height=450,
                on_select="rerun",
                selection_mode="single-row",
                key=key_name,
            )
            selected_rows = event.selection.rows
            if selected_rows:
                idx = selected_rows[0]
                return str(export_df.iloc[idx]["代號"])
            return None

        with tab_cross:
            st.subheader(
                "🎯 雙榜交集強勢清單 (點選下方任一列即可查看 K 線與 20 日多空線)"
            )
            sel1 = render_interactive_table(df_cross, "table_cross")
            if sel1:
                selected_stock_code = sel1

        with tab_top50:
            st.subheader(
                "📋 外資買超 Top 50 完整排行 (點選下方任一列即可查看 K 線與 20 日多空線)"
            )
            sel2 = render_interactive_table(df_top50, "table_top50")
            if sel2:
                selected_stock_code = sel2

        with tab_top100:
            st.subheader(
                "📋 全市場成交值前 100 名股票 (點選下方任一列即可查看 K 線與 20 日多空線)"
            )
            sel3 = render_interactive_table(df_top100, "table_top100")
            if sel3:
                selected_stock_code = sel3

        # ==================== 互動 K 線與多空線繪製區 ====================
        if selected_stock_code:
            st.markdown("---")
            stock_info = df_market[df_market["代號"] == selected_stock_code]
            stock_name = (
                stock_info.iloc[0]["官方名稱"]
                if not stock_info.empty
                else ""
            )

            st.subheader(
                f"📈 股票即時走勢與波段分析：{selected_stock_code} {stock_name}"
            )

            ticker_symbol = f"{selected_stock_code}.TW"
            df_hist = yf.download(
                ticker_symbol, period="6mo", interval="1d", progress=False
            )

            if df_hist.empty:
                ticker_symbol = f"{selected_stock_code}.TWO"
                df_hist = yf.download(
                    ticker_symbol, period="6mo", interval="1d", progress=False
                )

            if not df_hist.empty:
                if isinstance(df_hist.columns, pd.MultiIndex):
                    df_hist.columns = df_hist.columns.droplevel(1)

                df_hist["HLC3"] = (
                    df_hist["High"] + df_hist["Low"] + df_hist["Close"]
                ) / 3
                df_hist["Trend_Line"] = (
                    df_hist["HLC3"].rolling(window=20).mean()
                )

                # 計算最新乖離率以供參考
                latest_close = df_hist["Close"].iloc[-1]
                latest_ma20 = df_hist["Trend_Line"].iloc[-1]
                bias_val = round(
                    ((latest_close - latest_ma20) / latest_ma20) * 100, 2
                )

                if bias_val > bias_limit:
                    st.warning(
                        f"⚠️ **乖離過熱警示**：目前 MA20 乖離率為 **{bias_val}%**（超過您設定的 {bias_limit}% 警戒值）。短線漲幅較大，切勿直接追高，建議等待拉回至均線附近再行觀察！"
                    )
                else:
                    st.success(
                        f"✅ **乖離安全區間**：目前 MA20 乖離率為 **{bias_val}%**（小於警戒值 {bias_limit}%），短線技術面相對健康。"
                    )

                chart_type = st.radio(
                    "選擇 K 線週期", ["日 K 線", "周 K 線"], horizontal=True
                )

                plot_df = df_hist.copy()
                if chart_type == "周 K 線":
                    plot_df = (
                        df_hist.resample("W")
                        .agg(
                            {
                                "Open": "first",
                                "High": "max",
                                "Low": "min",
                                "Close": "last",
                                "Volume": "sum",
                                "Trend_Line": "mean",
                            }
                        )
                        .dropna()
                    )

                fig = go.Figure()

                fig.add_trace(
                    go.Candlestick(
                        x=plot_df.index,
                        open=plot_df["Open"],
                        high=plot_df["High"],
                        low=plot_df["Low"],
                        close=plot_df["Close"],
                        name="K 線",
                        increasing_line_color="#FF4B4B",
                        decreasing_line_color="#00CC96",
                    )
                )

                fig.add_trace(
                    go.Scatter(
                        x=plot_df.index,
                        y=plot_df["Trend_Line"],
                        mode="lines",
                        name="多空趨勢平衡線 (HLC3 MA20)",
                        line=dict(color="#FFA15A", width=2.5),
                    )
                )

                fig.update_layout(
                    title=f"{selected_stock_code} {stock_name} - {chart_type} 與 20日多空線",
                    xaxis_title="日期",
                    yaxis_title="價格 (TWD)",
                    xaxis_rangeslider_visible=False,
                    template="plotly_dark",
                    height=550,
                    dragmode="pan",
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={
                        "scrollZoom": True,
                        "displayModeBar": True,
                        "editable": False,
                    },
                )

                # ==================== 盤中即時 5 分鐘走勢監控 ====================
                st.markdown("---")
                st.subheader(
                    f"⚡ {selected_stock_code} {stock_name} 盤中即時 5 分鐘走勢監控"
                )
                df_intraday = yf.download(
                    ticker_symbol, period="1d", interval="5m", progress=False
                )
                if not df_intraday.empty:
                    if isinstance(df_intraday.columns, pd.MultiIndex):
                        df_intraday.columns = df_intraday.columns.droplevel(1)
                    st.line_chart(df_intraday["Close"])
                    st.caption(
                        "💡 盤中可觀察此 5 分鐘即時走勢，若該檔潛力股在平盤附近或小幅拉回時有大單支撐，即可考慮切入。"
                    )
                else:
                    st.info(
                        "目前非開盤時段，盤中 5 分鐘即時走勢僅在開盤期間顯示。"
                    )
            else:
                st.warning(
                    f"無法取得代號 {selected_stock_code} 的歷史 K 線數據。"
                )
    else:
        st.warning("無法解析出市場行情資料。")
else:
    st.warning("目前無法取得證交所官方市場行情資料。")