from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="台股雙軌籌碼終端機 (互動K線與縮放版)",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚡ 台股雙軌籌碼透視終端機 (外本比核心 + 可縮放互動 K 線)")
st.caption(
    "🔄 100% 串接證交所官方資料 | 支援滑鼠滾輪縮放、局部框選與多空平衡線"
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
            "強勢籌碼集中度指標",
        )
        st.markdown("---")

        # ==================== 三頁籤分頁顯示（支援點擊選取） ====================
        tab_cross, tab_top50, tab_top100 = st.tabs(
            [
                "🎯 雙榜交叉比對",
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
                "🎯 雙榜交集強勢清單 (點選下方任一列即可查看可縮放 K 線與多空線)"
            )
            sel1 = render_interactive_table(df_cross, "table_cross")
            if sel1:
                selected_stock_code = sel1

        with tab_top50:
            st.subheader(
                "📋 外資買超 Top 50 完整排行 (點選下方任一列即可查看可縮放 K 線與多空線)"
            )
            sel2 = render_interactive_table(df_top50, "table_top50")
            if sel2:
                selected_stock_code = sel2

        with tab_top100:
            st.subheader(
                "📋 全市場成交值前 100 名股票 (點選下方任一列即可查看可縮放 K 線與多空線)"
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
                f"📈 股票即時走勢分析：{selected_stock_code} {stock_name}"
            )

            # 下載 yfinance 歷史資料 (.TW)
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
                # 處理 MultiIndex 欄位問題
                if isinstance(df_hist.columns, pd.MultiIndex):
                    df_hist.columns = df_hist.columns.droplevel(1)

                # 計算多空平均線：(最高價 + 最低價) / 2
                df_hist["HL_Avg"] = (df_hist["High"] + df_hist["Low"]) / 2

                # 切換日 K 與周 K 顯示
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
                                "HL_Avg": "mean",
                            }
                        )
                        .dropna()
                    )

                # 使用 Plotly 繪製紅綠 K 線與多空線
                fig = go.Figure()

                # 紅漲綠跌 K 線設定
                fig.add_trace(
                    go.Candlestick(
                        x=plot_df.index,
                        open=plot_df["Open"],
                        high=plot_df["High"],
                        low=plot_df["Low"],
                        close=plot_df["Close"],
                        name="K 線",
                        increasing_line_color="#FF4B4B",  # 紅色
                        decreasing_line_color="#00CC96",  # 綠色
                    )
                )

                # 多空平均線 (高低價平均)
                fig.add_trace(
                    go.Scatter(
                        x=plot_df.index,
                        y=plot_df["HL_Avg"],
                        mode="lines",
                        name="多空平衡線 (高低價平均)",
                        line=dict(color="#FFA15A", width=2),
                    )
                )

                fig.update_layout(
                    title=f"{selected_stock_code} {stock_name} - {chart_type} 與多空線",
                    xaxis_title="日期",
                    yaxis_title="價格 (TWD)",
                    xaxis_rangeslider_visible=False,
                    template="plotly_dark",
                    height=550,
                )

                # 支援滑鼠滾輪縮放與完整互動工具列設定
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={
                        "scrollZoom": True,
                        "displayModeBar": True,
                        "editable": False,
                    },
                )
            else:
                st.warning(
                    f"無法取得代號 {selected_stock_code} 的歷史 K 線數據。"
                )
    else:
        st.warning("無法解析出市場行情資料。")
else:
    st.warning("目前無法取得證交所官方市場行情資料。")