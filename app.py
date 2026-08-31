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

            # 1. 20日波段累積與連續天數
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

            # 2. 單日資金攻擊效率計算
            def calc_efficiency(row):
                f_ratio = row["外本比(%)"]
                pct = row["漲跌幅(%)"]
                if f_ratio > 0:
                    return round(pct / f_ratio, 2)
                return 0.0

            df["單日資金攻擊效率"] = df.apply(calc_efficiency, axis=1)

            # 3. 日K與週K多空平均價格線狀態判斷
            def get_multi_timeframe_status(code):
                try:
                    ticker_symbol = f"{code}.TW"
                    df_hist = yf.download(
                        ticker_symbol,
                        period="6mo",
                        interval="1d",
                        progress=False,
                    )
                    if df_hist.empty:
                        ticker_symbol = f"{code}.TWO"
                        df_hist = yf.download(
                            ticker_symbol,
                            period="6mo",
                            interval="1d",
                            progress=False,
                        )

                    if not df_hist.empty:
                        if isinstance(df_hist.columns, pd.MultiIndex):
                            df_hist.columns = df_hist.columns.droplevel(1)

                        # 計算日K HLC3 MA20
                        df_hist["HLC3"] = (
                            df_hist["High"]
                            + df_hist["Low"]
                            + df_hist["Close"]
                        ) / 3
                        df_hist["MA20"] = (
                            df_hist["HLC3"].rolling(window=20).mean()
                        )

                        last_row = df_hist.iloc[-1]
                        day_above = (
                            last_row["Close"] >= last_row["MA20"]
                            if pd.notna(last_row["MA20"])
                            else False
                        )

                        # 計算週K HLC3 MA20
                        df_weekly = (
                            df_hist.resample("W")
                            .agg(
                                {
                                    "High": "max",
                                    "Low": "min",
                                    "Close": "last",
                                }
                            )
                            .dropna()
                        )
                        if len(df_weekly) >= 20:
                            df_weekly["W_HLC3"] = (
                                df_weekly["High"]
                                + df_weekly["Low"]
                                + df_weekly["Close"]
                            ) / 3
                            df_weekly["W_MA20"] = (
                                df_weekly["W_HLC3"].rolling(window=20).mean()
                            )
                            w_last = df_weekly.iloc[-1]
                            week_above = (
                                w_last["Close"] >= w_last["W_MA20"]
                                if pd.notna(w_last["W_MA20"])
                                else False
                            )
                        else:
                            week_above = day_above

                        return day_above, week_above
                except:
                    pass
                return False, False

            res_status = df["代號"].apply(get_multi_timeframe_status)
            df["_日K站上"] = [r[0] for r in res_status]
            df["_週K站上"] = [r[1] for r in res_status]

            def format_display_name(row):
                name = row["官方名稱"]
                d_up = row["_日K站上"]
                w_up = row["_週K站上"]

                if d_up and w_up:
                    status_text = "🟢 雙多"
                elif not d_up and w_up:
                    status_text = "🟡 長多短空"
                elif d_up and not w_up:
                    status_text = "🟠 短多長空"
                else:
                    status_text = "🔴 雙空"

                return f"{name} | {status_text}"

            df["顯示名稱"] = df.apply(format_display_name, axis=1)
            return df

        # 完整市場enrich，方便隨時查找全市場任何一家
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
            by="總成交金額_元", ascending=False
        ).head(100)
        df_top100 = enrich_data(df_t_100)
        df_top100.insert(0, "成交值排名", range(1, len(df_top100) + 1))

        # 3. 雙榜交叉比對
        top50_codes = set(df_top50["代號"])
        top100_codes = set(df_top100["代號"])
        cross_codes = top50_codes.intersection(top100_codes)

        df_cross = df_market[df_market["代號"].isin(cross_codes)].copy()
        df_cross = enrich_data(df_cross)
        df_cross = df_cross.sort_values(by="外本比(%)", ascending=False)
        df_cross.insert(0, "外本比排序", range(1, len(df_cross) + 1))

        # ==================== 頁面最左方/頂部：即時查找獨立面板 ====================
        st.markdown("### 🔍 任意台股快速查找")
        col_input, col_info = st.columns([1, 3])
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
                m_row = matched_df.iloc[0]
                m_code = m_row["代號"]
                m_name = m_row["官方名稱"]
                m_disp = m_row["顯示名稱"]
                m_eff = m_row["單日資金攻擊效率"]
                m_ratio = m_row["外本比(%)"]
                m_streak = m_row["連續買超天數"]
                m_accum = m_row["近20日外資累積買超(張)"]

                with col_info:
                    st.success(
                        f"🎯 **[{m_code}] {m_disp}** | 外本比: **{m_ratio}%** | "
                        f"攻擊效率: **{m_eff}** | 20日累積買超: **{m_accum}張** (連買 {m_streak}天)"
                    )
                # 自動指定帶入下方圖表
                selected_stock_code = m_code
            else:
                with col_info:
                    st.warning("查無此台股代號或名稱，請確認輸入是否正確。")
                selected_stock_code = None
        else:
            selected_stock_code = None

        st.markdown("---")

        # ==================== 分頁顯示 ====================
        tab_cross, tab_top50, tab_top100 = st.tabs(
            [
                "🎯 雙榜交叉比對",
                "🔥 1. 外資買超 Top 50",
                "💰 2. 成交值 Top 100",
            ]
        )

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
            sel1 = render_interactive_table(df_cross, "table_cross")
            if sel1:
                selected_stock_code = sel1

        with tab_top50:
            sel2 = render_interactive_table(df_top50, "table_top50")
            if sel2:
                selected_stock_code = sel2

        with tab_top100:
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

            st.subheader(f"📈 查閱股票走勢與波段：{selected_stock_code} {stock_name}")

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

                chart_type = st.radio(
                    "K線週期", ["日 K 線", "周 K 線"], horizontal=True
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
                        name="K線",
                        increasing_line_color="#FF4B4B",
                        decreasing_line_color="#00CC96",
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=plot_df.index,
                        y=plot_df["Trend_Line"],
                        mode="lines",
                        name="HLC3 MA20",
                        line=dict(color="#FFA15A", width=2.5),
                    )
                )
                fig.update_layout(
                    xaxis_title="日期",
                    yaxis_title="價格",
                    xaxis_rangeslider_visible=False,
                    template="plotly_dark",
                    height=500,
                )
                st.plotly_chart(fig, use_container_width=True)

                # 盤中即時 5 分鐘走勢
                st.markdown("---")
                st.subheader("⚡ 盤中 5 分鐘即時走勢")
                df_intraday = yf.download(
                    ticker_symbol, period="1d", interval="5m", progress=False
                )
                if not df_intraday.empty:
                    if isinstance(df_intraday.columns, pd.MultiIndex):
                        df_intraday.columns = df_intraday.columns.droplevel(1)
                    st.line_chart(df_intraday["Close"])
                else:
                    st.info("目前非開盤時段。")