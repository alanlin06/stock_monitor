import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta


# ============================================================
# 頁面設定
# ============================================================

st.set_page_config(
    page_title="台股外資籌碼與專屬排行終端機",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("⚡ 台股外資買超 Top 50 與籌碼專屬排行終端機")
st.caption(
    "🔄 100% 串接證交所官方 API | "
    "全面以『外本比』精準計算：買超 Top 50、外本比 Top 50、連續買超 Top 50、成交值 Top 100"
)


# ============================================================
# 側邊欄設定
# ============================================================

with st.sidebar:

    st.header("⚙️ 排序與檢視設定")

    sort_option = st.selectbox(
        "Top 50 主表格排序依據：",
        options=[
            "🔥 外本比 (外資買超股數佔發行總股數比例 - 優先)",
            "📈 外資買超張數 (與證交所官網預設一致)",
            "💰 外資買超金額 (資金砸最多優先)",
            "🎯 買超金額佔成交值比 (當日籌碼貢獻佔比)",
            "⏳ 連續買超天數 (連買最久優先)"
        ],
        index=0
    )

    st.markdown("---")

    st.markdown(
        """
        💡 **指標說明**：
        - **外本比 (%)**：(外資買超股數 ÷ 官方發行總股數) × 100%。全排行榜同步納入計算。
        - **外資買超金額**：買超張數 × 平均價格 (VWAP) × 1000。
        """
    )


# ============================================================
# 抓取證交所資料
# ============================================================

@st.cache_data(ttl=600)
def fetch_twse_data():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36"
        )
    }

    curr = datetime.now()
    dates = []

    while len(dates) < 10 and (datetime.now() - curr).days < 30:

        if curr.weekday() < 5:

            d_str = curr.strftime("%Y%m%d")

            test_url = (
                "https://www.twse.com.tw/rwd/zh/fund/T86"
                f"?response=json&date={d_str}&selectType=ALL"
            )

            try:
                res = requests.get(test_url, headers=headers, timeout=4)
                data = res.json()
                if data.get("stat") == "OK" and len(data.get("data", [])) > 0:
                    dates.append(d_str)
            except:
                pass

        curr -= timedelta(days=1)

    if not dates:
        return {}, {}, [], ""

    latest_date = dates[0]

    mi_url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        f"?response=json&type=ALLBUT0999&date={latest_date}"
    )

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
                                issued_shares_total_raw = float(row[2].replace(",", ""))
                                total_turnover = float(row[3].replace(",", ""))
                                trading_volume = float(row[4].replace(",", ""))
                                close_price = float(row[7].replace(",", ""))
                                change_pct = (
                                    float(row[10].replace(",", "").replace("%", ""))
                                    if len(row) > 10 and row[10] and row[10].strip() != ""
                                    else 0.0
                                )
                                vwap = total_turnover / trading_volume if trading_volume > 0 else close_price

                                market_dict[code] = {
                                    "官方名稱": name,
                                    "發行總股數": issued_shares_total_raw,
                                    "收盤價": close_price,
                                    "成交均價": round(vwap, 2),
                                    "總成交金額_元": total_turnover,
                                    "漲跌幅(%)": change_pct
                                }
                            except:
                                continue
    except Exception as e:
        print(f"MI_INDEX error: {e}")

    hist_foreign_shares = {}
    latest_foreign_shares = {}

    for i, d_str in enumerate(dates):
        t86_url = (
            "https://www.twse.com.tw/rwd/zh/fund/T86"
            f"?response=json&date={d_str}&selectType=ALL"
        )
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


# ============================================================
# 執行資料同步
# ============================================================

with st.spinner("⚡ 正在同步證交所官方市場資料與籌碼中..."):
    market_dict, latest_foreign_shares, hist_foreign_shares, target_dates, latest_date = fetch_twse_data()

if latest_date:
    st.sidebar.success(f"📅 官方同步交易日：{latest_date[:4]}/{latest_date[4:6]}/{latest_date[6:]}")


# ============================================================
# 建立資料表與全面外本比導向計算
# ============================================================

if market_dict:
    combined_rows = []

    for code, m_info in market_dict.items():
        f_shares = latest_foreign_shares.get(code, 0)
        combined_rows.append({
            "代號": code,
            "官方名稱": m_info["官方名稱"],
            "發行總股數": m_info["發行總股數"],
            "外資買賣超股數": f_shares,
            "外資買賣超張數": f_shares / 1000,
            "收盤價": m_info["收盤價"],
            "成交均價": m_info["成交均價"],
            "總成交金額_元": m_info["總成交金額_元"],
            "漲跌幅(%)": m_info["漲跌幅(%)"]
        })

    df_all = pd.DataFrame(combined_rows)

    if not df_all.empty:
        
        def calc_streak(code):
            streak = 0
            for d_str in target_dates:
                val = hist_foreign_shares.get(d_str, {}).get(code, 0)
                if val > 0:
                    streak += 1
                else:
                    break
            return streak

        df_all["連續買超天數"] = df_all["代號"].apply(calc_streak)
        
        df_all["外本比(%)"] = df_all.apply(
            lambda row: round((row["外資買賣超股數"] / row["發行總股數"]) * 100, 3) if row["發行總股數"] > 0 else 0.0,
            axis=1
        )
        
        df_all["外資買超金額_元"] = df_all["外資買賣超張數"] * 1000 * df_all["成交均價"]
        df_all["外資買超金額(億)"] = round(df_all["外資買超金額_元"] / 1e8, 2)
        df_all["買超金額佔成交值比(%)"] = df_all.apply(
            lambda row: round((row["外資買超金額_元"] / row["總成交金額_元"]) * 100, 2) if row["總成交金額_元"] > 0 else 0.0,
            axis=1
        )

        df_top50 = df_all[df_all["外資買賣超張數"] > 0].sort_values(by="外資買賣超張數", ascending=False).head(50).copy()

        if "外本比" in sort_option:
            df_top50 = df_top50.sort_values(by="外本比(%)", ascending=False)
        elif "買超張數" in sort_option:
            df_top50 = df_top50.sort_values(by="外資買賣超張數", ascending=False)
        elif "買超金額" in sort_option:
            df_top50 = df_top50.sort_values(by="外資買超金額(億)", ascending=False)
        elif "佔成交值比" in sort_option:
            df_top50 = df_top50.sort_values(by="買超金額佔成交值比(%)", ascending=False)
        else:
            df_top50 = df_top50.sort_values(by="連續買超天數", ascending=False)

        df_top50.insert(0, "集中排序", range(1, len(df_top50) + 1))

        df_wben50 = df_all[df_all["外本比(%)"] > 0].sort_values(
            by=["外本比(%)", "外資買賣超張數"], ascending=[False, False]
        ).head(50).copy()
        df_wben50.insert(0, "外本比排序", range(1, len(df_wben50) + 1))

        df_streak50 = df_all[df_all["連續買超天數"] > 0].sort_values(
            by=["連續買超天數", "外本比(%)"], ascending=[False, False]
        ).head(50).copy()
        df_streak50.insert(0, "連買排序", range(1, len(df_streak50) + 1))

        df_vol100 = df_all.sort_values(by="總成交金額_元", ascending=False).head(100).copy()
        df_vol100["成交金額(億)"] = round(df_vol100["總成交金額_元"] / 1e8, 2)
        df_vol100.insert(0, "成交值排序", range(1, len(df_vol100) + 1))

        total_foreign_amount = round(df_top50["外資買超金額(億)"].sum(), 2)
        most_concentrated = df_all.sort_values(by="外本比(%)", ascending=False).iloc[0]
        top_amount_stock = df_top50.sort_values(by="外資買超金額(億)", ascending=False).iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📊 Top 50 總買超金額", f"{total_foreign_amount} 億")
        c2.metric("🎯 監控標的檔數", f"{len(df_top50)} 檔")
        c3.metric("🔥 全市場外本比最高", f"{most_concentrated['官方名稱']} ({most_concentrated['代號']})", f"外本比 {most_concentrated['外本比(%)']}%")
        c4.metric("💰 砸錢最多之冠", f"{top_amount_stock['官方名稱']} ({top_amount_stock['代號']})", f"+{top_amount_stock['外資買超金額(億)']} 億")

        st.markdown("---")

        # ====================================================
        # 個股互動技術分析與 K線週期切換 (日K / 週K)
        # ====================================================
        st.subheader("📈 個股技術分析與均價走勢檢視 (支援日K / 週K)")
        
        col_sel1, col_sel2 = st.columns([3, 1])
        with col_sel1:
            all_stock_options = [f"{row['代號']} {row['官方名稱']}" for _, row in df_all.sort_values(by="代號").iterrows()]
            selected_stock_str = st.selectbox("👉 請從下拉選單選擇（或輸入）標的：", options=all_stock_options, index=0)
        with col_sel2:
            k_period_type = st.selectbox("⏱️ 選擇 K 線週期：", options=["日K (近6個月)", "週K (近1年)"], index=0)
        
        if selected_stock_str:
            target_code = selected_stock_str.split(" ")[0]
            target_name = selected_stock_str.split(" ")[1]
            
            # 根據選擇載入對應區間與頻率
            yf_period = "1y" if "週K" in k_period_type else "6mo"
            yf_interval = "1wk" if "週K" in k_period_type else "1d"
            
            with st.spinner(f"正在載入 {target_code} {target_name} 的 {k_period_type} 走勢與均價線..."):
                try:
                    df_stock = yf.download(f"{target_code}.TW", period=yf_period, interval=yf_interval, progress=False)
                    if df_stock.empty:
                        df_stock = yf.download(f"{target_code}.TWO", period=yf_period, interval=yf_interval, progress=False)
                        
                    if not df_stock.empty:
                        if isinstance(df_stock.columns, pd.MultiIndex):
                            df_stock.columns = df_stock.columns.get_level_values(0)
                            
                        df_stock['MA10'] = df_stock['Close'].rolling(window=10).mean()
                        df_stock['MA20'] = df_stock['Close'].rolling(window=20).mean()
                        
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(
                            x=df_stock.index, open=df_stock['Open'], high=df_stock['High'],
                            low=df_stock['Low'], close=df_stock['Close'], name=f'{k_period_type}線'
                        ))
                        fig.add_trace(go.Scatter(
                            x=df_stock.index, y=df_stock['MA10'], mode='lines', 
                            name='10日/週均價線', line=dict(color='orange', width=1.5)
                        ))
                        fig.add_trace(go.Scatter(
                            x=df_stock.index, y=df_stock['MA20'], mode='lines', 
                            name='20日/週均價線', line=dict(color='deepskyblue', width=1.5)
                        ))
                        
                        fig.update_layout(
                            title=f"{target_code} {target_name} - {k_period_type}與均價走勢圖 (可縮放/平移)",
                            yaxis_title="股價 (TWD)", xaxis_title="日期",
                            template="plotly_dark", height=480,
                            margin=dict(l=10, r=10, t=40, b=10)
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("查無此標的歷史資料。")
                except Exception as e:
                    st.error(f"載入發生錯誤: {e}")

        st.markdown("---")

        # ====================================================
        # 四大外本比與成交值專屬排行榜分頁
        # ====================================================
        tab1, tab2, tab3, tab4 = st.tabs([
            "🔥 外資買超 Top 50", 
            "🔥 當日外本比 Top 50", 
            "⏳ 連續買超 Top 50 (外本比優先)", 
            "🏆 全市場成交值 Top 100 (含外本比)"
        ])

        # TAB 1: 外資買超 Top 50
        with tab1:
            st.subheader("📋 外資買超 Top 50 全部標的完整清單")
            export_df1 = df_top50[[
                "集中排序", "代號", "官方名稱", "外資買賣超張數",
                "成交均價", "外資買超金額(億)", "外本比(%)",
                "買超金額佔成交值比(%)", "連續買超天數", "漲跌幅(%)"
            ]]
            st.dataframe(
                export_df1,
                column_config={
                    "集中排序": "排名", "代號": "代號", "官方名稱": "名稱",
                    "外資買賣超張數": st.column_config.NumberColumn("📈 買超張數", format="%d 張"),
                    "成交均價": st.column_config.NumberColumn("成交均價", format="%.2f"),
                    "外資買超金額(億)": st.column_config.NumberColumn("💰 買超金額", format="%.2f 億"),
                    "外本比(%)": st.column_config.NumberColumn("🔥 外本比 (股數佔比)", format="%.3f %%"),
                    "買超金額佔成交值比(%)": st.column_config.NumberColumn("🎯 買超佔成交值比", format="%.2f %%"),
                    "連續買超天數": st.column_config.NumberColumn("連買天數", format="%d 天"),
                    "漲跌幅(%)": st.column_config.NumberColumn("漲跌幅", format="%.2f %%")
                },
                use_container_width=True, hide_index=True, height=600
            )

        # TAB 2: 當日外本比 Top 50
        with tab2:
            st.subheader("🔥 當日外本比最高排行 Top 50")
            export_df2 = df_wben50[[
                "外本比排序", "代號", "官方名稱", "外本比(%)",
                "外資買賣超張數", "收盤價", "漲跌幅(%)"
            ]]
            st.dataframe(
                export_df2,
                column_config={
                    "外本比排序": "排名", "代號": "代號", "官方名稱": "名稱",
                    "外本比(%)": st.column_config.NumberColumn("🔥 外本比", format="%.3f %%"),
                    "外資買賣超張數": st.column_config.NumberColumn("買賣超張數", format="%d 張"),
                    "收盤價": st.column_config.NumberColumn("收盤價", format="%.2f"),
                    "漲跌幅(%)": st.column_config.NumberColumn("漲跌幅", format="%.2f %%")
                },
                use_container_width=True, hide_index=True, height=600
            )

        # TAB 3: 連續買超 Top 50
        with tab3:
            st.subheader("⏳ 連續買超天數最多排行 Top 50")
            export_df3 = df_streak50[[
                "連買排序", "代號", "官方名稱", "連續買超天數",
                "外本比(%)", "外資買賣超張數", "收盤價", "漲跌幅(%)"
            ]]
            st.dataframe(
                export_df3,
                column_config={
                    "連買排序": "排名", "代號": "代號", "官方名稱": "名稱",
                    "連續買超天數": st.column_config.NumberColumn("⏳ 連買天數", format="%d 天"),
                    "外本比(%)": st.column_config.NumberColumn("🔥 外本比", format="%.3f %%"),
                    "外資買賣超張數": st.column_config.NumberColumn("最新買超張數", format="%d 張"),
                    "收盤價": st.column_config.NumberColumn("收盤價", format="%.2f"),
                    "漲跌幅(%)": st.column_config.NumberColumn("漲跌幅", format="%.2f %%")
                },
                use_container_width=True, hide_index=True, height=600
            )

        # TAB 4: 全市場成交值 Top 100 (外本比已加入)
        with tab4:
            st.subheader("🏆 全市場成交金額百大焦點排行 Top 100 (已納入外本比計算)")
            export_df4 = df_vol100[[
                "成交值排序", "代號", "官方名稱", "成交金額(億)",
                "外本比(%)", "收盤價", "漲跌幅(%)", "總成交金額_元"
            ]]
            st.dataframe(
                export_df4,
                column_config={
                    "成交值排序": "排名", "代號": "代號", "官方名稱": "名稱",
                    "成交金額(億)": st.column_config.NumberColumn("💰 成交金額", format="%.2f 億"),
                    "外本比(%)": st.column_config.NumberColumn("🔥 外本比 (股數佔比)", format="%.3f %%"),
                    "收盤價": st.column_config.NumberColumn("收盤價", format="%.2f"),
                    "漲跌幅(%)": st.column_config.NumberColumn("漲跌幅", format="%.2f %%"),
                    "總成交金額_元": None
                },
                use_container_width=True, hide_index=True, height=600
            )

    else:
        st.warning("無法解析出市場與外資買超資料。")
else:
    st.warning("目前無法取得證交所官方市場行情資料，請確認網路連線或是否為非交易日。")