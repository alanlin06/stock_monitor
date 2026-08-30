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
    "精準股數外本比、連買天數與成交值佔比追蹤，支援點擊排行即時檢視 10/20 日均價走勢"
)


# ============================================================
# 側邊欄設定 (保留您的排序與指標說明)
# ============================================================

with st.sidebar:

    st.header("⚙️ 排序與檢視設定")

    sort_option = st.selectbox(
        "Top 50 主表格排序依據：",
        options=[
            "📈 外資買超張數 (與證交所官網預設一致)",
            "💰 外資買超金額 (資金砸最多優先)",
            "🔥 外本比 (外資買超股數佔發行總股數比例)",
            "🎯 買超金額佔成交值比 (當日籌碼貢獻佔比)",
            "⏳ 連續買超天數 (連買最久優先)"
        ],
        index=0
    )

    st.markdown("---")

    st.markdown(
        """
        💡 **指標說明**：

        - **外資買超金額**：買超張數 × 平均價格 (VWAP) × 1000。
        - **外本比 (%)**：(外資買超股數 ÷ 官方發行總股數) × 100%。
        - **買超佔成交值比 (%)**：今日買超金額佔該股總成交金額比例。
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

    while len(dates) < 5 and (datetime.now() - curr).days < 20:

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
# 建立資料表
# ============================================================

if market_dict and latest_foreign_shares:
    combined_rows = []

    for code, f_shares in latest_foreign_shares.items():
        if f_shares > 0 and code in market_dict:
            m_info = market_dict[code]
            combined_rows.append({
                "代號": code,
                "官方名稱": m_info["官方名稱"],
                "發行總股數": m_info["發行總股數"],
                "外資買超股數": f_shares,
                "外資買超張數": f_shares / 1000,
                "收盤價": m_info["收盤價"],
                "成交均價": m_info["成交均價"],
                "總成交金額_元": m_info["總成交金額_元"],
                "漲跌幅(%)": m_info["漲跌幅(%)"]
            })

    df_all = pd.DataFrame(combined_rows)

    if not df_all.empty:
        df_top50 = df_all.sort_values(by="外資買超張數", ascending=False).head(50).copy()

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

        df_top50["連續買超天數"] = df_top50["代號"].apply(calc_streak)
        df_top50["外資買超金額_元"] = df_top50["外資買超張數"] * 1000 * df_top50["成交均價"]
        df_top50["外資買超金額(億)"] = round(df_top50["外資買超金額_元"] / 1e8, 2)
        df_top50["外本比(%)"] = df_top50.apply(
            lambda row: round((row["外資買超股數"] / row["發行總股數"]) * 100, 3) if row["發行總股數"] > 0 else 0.0,
            axis=1
        )
        df_top50["買超金額佔成交值比(%)"] = df_top50.apply(
            lambda row: round((row["外資買超金額_元"] / row["總成交金額_元"]) * 100, 2) if row["總成交金額_元"] > 0 else 0.0,
            axis=1
        )

        if "買超張數" in sort_option:
            df_top50 = df_top50.sort_values(by="外資買超張數", ascending=False)
        elif "買超金額" in sort_option:
            df_top50 = df_top50.sort_values(by="外資買超金額(億)", ascending=False)
        elif "外本比" in sort_option:
            df_top50 = df_top50.sort_values(by="外本比(%)", ascending=False)
        elif "佔成交值比" in sort_option:
            df_top50 = df_top50.sort_values(by="買超金額佔成交值比(%)", ascending=False)
        else:
            df_top50 = df_top50.sort_values(by="連續買超天數", ascending=False)

        df_top50.insert(0, "集中排序", range(1, len(df_top50) + 1))

        # 頂部看板
        total_foreign_amount = round(df_top50["外資買超金額(億)"].sum(), 2)
        most_concentrated = df_top50.sort_values(by="外本比(%)", ascending=False).iloc[0]
        top_amount_stock = df_top50.sort_values(by="外資買超金額(億)", ascending=False).iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📊 Top 50 總買超金額", f"{total_foreign_amount} 億")
        c2.metric("🎯 監控標的檔數", f"{len(df_top50)} 檔")
        c3.metric("🔥 股本外本比最高", f"{most_concentrated['官方名稱']} ({most_concentrated['代號']})", f"外本比 {most_concentrated['外本比(%)']}%")
        c4.metric("💰 砸錢最多之冠", f"{top_amount_stock['官方名稱']} ({top_amount_stock['代號']})", f"+{top_amount_stock['外資買超金額(億)']} 億")

        st.markdown("---")

        # ====================================================
        # 互動點擊叫出走勢圖區塊 (從排行榜點選代號)
        # ====================================================
        st.subheader("📈 個股技術分析與 10/20 日均價走勢檢視")
        
        # 製作一個選單，列出 Top 50 所有股票供點選
        stock_options = [f"{row['代號']} {row['官方名稱']}" for _, row in df_top50.iterrows()]
        selected_stock_str = st.selectbox("👉 請從下方下拉選單（或點選）想查看走勢的標的：", options=stock_options, index=0)
        
        if selected_stock_str:
            target_code = selected_stock_str.split(" ")[0]
            target_name = selected_stock_str.split(" ")[1]
            
            with st.spinner(f"正在載入 {target_code} {target_name} 的歷史走勢與均價線..."):
                try:
                    df_stock = yf.download(f"{target_code}.TW", period="6mo", interval="1d", progress=False)
                    if df_stock.empty:
                        df_stock = yf.download(f"{target_code}.TWO", period="6mo", interval="1d", progress=False)
                        
                    if not df_stock.empty:
                        if isinstance(df_stock.columns, pd.MultiIndex):
                            df_stock.columns = df_stock.columns.get_level_values(0)
                            
                        df_stock['MA10'] = df_stock['Close'].rolling(window=10).mean()
                        df_stock['MA20'] = df_stock['Close'].rolling(window=20).mean()
                        
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(
                            x=df_stock.index, open=df_stock['Open'], high=df_stock['High'],
                            low=df_stock['Low'], close=df_stock['Close'], name='日K線'
                        ))
                        fig.add_trace(go.Scatter(
                            x=df_stock.index, y=df_stock['MA10'], mode='lines', 
                            name='10日均價線', line=dict(color='orange', width=1.5)
                        ))
                        fig.add_trace(go.Scatter(
                            x=df_stock.index, y=df_stock['MA20'], mode='lines', 
                            name='20日均價線', line=dict(color='deepskyblue', width=1.5)
                        ))
                        
                        fig.update_layout(
                            title=f"{target_code} {target_name} - 10/20日均價走勢圖 (可縮放/平移)",
                            yaxis_title="股價 (TWD)", xaxis_title="日期",
                            template="plotly_dark", height=480,
                            margin=dict(l=10, r=10, t=40, b=10)
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("查無此標的股價歷史資料。")
                except Exception as e:
                    st.error(f"載入發生錯誤: {e}")

        st.markdown("---")

        # 分頁
        tab_rank, tab_special_rank = st.tabs([
            "🔥 Top 50 外資買超完整排行",
            "🏆 兩大專屬籌碼排行 (股數外本比 / 連買天數)"
        ])

        with tab_rank:
            col_t1, col_t2 = st.columns([4, 1])
            with col_t1:
                st.subheader("📋 外資買超 Top 50 全部標的完整清單")
            with col_t2:
                export_df = df_top50[[
                    "集中排序", "代號", "官方名稱", "外資買超張數",
                    "成交均價", "外資買超金額(億)", "外本比(%)",
                    "買超金額佔成交值比(%)", "連續買超天數", "漲跌幅(%)"
                ]]
                csv_data = export_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 下載完整 CSV",
                    data=csv_data,
                    file_name=f"外資買超Top50_{latest_date}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            st.dataframe(
                export_df,
                column_config={
                    "集中排序": "排名",
                    "代號": "代號",
                    "官方名稱": "名稱",
                    "外資買超張數": st.column_config.NumberColumn("📈 買超張數", format="%d 張"),
                    "成交均價": st.column_config.NumberColumn("成交均價", format="%.2f"),
                    "外資買超金額(億)": st.column_config.NumberColumn("💰 買超金額", format="%.2f 億"),
                    "外本比(%)": st.column_config.NumberColumn("🔥 外本比 (股數佔比)", format="%.3f %%"),
                    "買超金額佔成交值比(%)": st.column_config.NumberColumn("🎯 買超佔成交值比", format="%.2f %%"),
                    "連續買超天數": st.column_config.NumberColumn("連買天數", format="%d 天"),
                    "漲跌幅(%)": st.column_config.NumberColumn("漲跌幅", format="%.2f %%")
                },
                use_container_width=True,
                hide_index=True,
                height=650
            )

        with tab_special_rank:
            st.subheader("🏆 兩大焦點籌碼專屬排行")
            c_s1, c_s2 = st.columns(2)

            with c_s1:
                st.markdown("### 🔥 1. 當日外本比最高排行 Top 15")
                df_r1 = df_top50.sort_values(by="外本比(%)", ascending=False).head(15)
                st.dataframe(
                    df_r1[["代號", "官方名稱", "外本比(%)", "外資買超張數"]],
                    column_config={
                        "代號": "代號",
                        "官方名稱": "名稱",
                        "外本比(%)": st.column_config.NumberColumn("外本比", format="%.3f %%"),
                        "外資買超張數": st.column_config.NumberColumn("買超張數", format="%d 張")
                    },
                    use_container_width=True, hide_index=True, height=500
                )

            with c_s2:
                st.markdown("### ⏳ 2. 連續買超天數最多排行 Top 15")
                df_r2 = df_top50.sort_values(by=["連續買超天數", "外本比(%)"], ascending=[False, False]).head(15)
                st.dataframe(
                    df_r2[["代號", "官方名稱", "連續買超天數", "外本比(%)"]],
                    column_config={
                        "代號": "代號",
                        "官方名稱": "名稱",
                        "連續買超天數": st.column_config.NumberColumn("連買天數", format="%d 天"),
                        "外本比(%)": st.column_config.NumberColumn("外本比", format="%.3f %%")
                    },
                    use_container_width=True, hide_index=True, height=500
                )
    else:
        st.warning("無法解析出外資買超資料。")
else:
    st.warning("目前無法取得證交所官方市場行情資料，請確認網路連線或是否為非交易日。")