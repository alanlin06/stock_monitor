import streamlit as st
import yfinance as yf

# ==================== 頁面基本設定 ====================
st.set_page_config(page_title="台股強勢策略", layout="wide")

# ==================== 側邊欄 (Sidebar) ====================
with st.sidebar:
    st.subheader("🔍 側邊欄快速查找台股")
    stock_search = st.text_input("輸入代號或名稱", placeholder="例: 2330")

    st.markdown("---")
    st.subheader("📊 明細/族群表格排序依據")
    sort_metric = st.selectbox(
        "效率籌碼共振分", ["推薦：倍數大", "分數高", "成交量大"]
    )

    # [已完整刪除原本的勾選控制：show_filtered_only = st.checkbox(...)]

    # ==================== 新增：加權指數資訊區塊 ====================
    st.markdown("---")
    st.subheader("📈 加權指數即時/收盤資訊")

    try:
        twii = yf.Ticker("^TWII")
        hist = twii.history(period="2d")
        if len(hist) >= 2:
            current_price = hist["Close"].iloc[-1]
            prev_close = hist["Close"].iloc[-2]
            change_pts = current_price - prev_close
            change_pct = (change_pts / prev_close) * 100

            color = "#FF4B4B" if change_pts >= 0 else "#09AB3B"  # 紅漲綠跌
            sign = "+" if change_pts >= 0 else ""

            st.markdown(
                f"**目前價格**：`{current_price:,.2f}`", unsafe_allow_html=True
            )
            st.markdown(
                f"**漲跌點數**：<span style='color:{color}; font-weight:bold;'>{sign}{change_pts:,.2f} 點</span>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**漲跌幅**：<span style='color:{color}; font-weight:bold;'>{sign}{change_pct:.2f}%</span>",
                unsafe_allow_html=True,
            )
        else:
            st.warning("無法取得大盤歷史資料 (資料筆數不足)")
    except Exception as e:
        st.error(f"載入加權指數失敗: {e}")

    st.markdown("---")
    st.caption("官方同步日：20260923 (對比 20260922)")


# ==================== 主畫面 (Main Content) ====================
st.title("🔥 持續中強勢股")

tab1, tab2, tab3, tab4 = st.tabs(
    ["新進榜強勢股", "持續中強勢股", "雙法人Top100族群集中度比較", "全市場快速查>"]
)

with tab1:
    st.info("請點選分頁查看對應內容")

with tab2:
    col_left, col_right = st.columns([1, 1.2])

    with col_left:
        st.subheader("🟢 族群分布")
        st.dataframe(
            {
                "族群": [
                    "ASIC",
                    "硬板",
                    "晶圓代工",
                    "利基記憶體",
                    "矽晶圓",
                    "AI散熱",
                    "AI互連元件",
                    "封測",
                    "金融",
                    "高高速模組",
                ],
                "個股數": [3, 3, 2, 2, 2, 2, 2, 2, 2, 2],
                "總成交...": [
                    "2...",
                    "2...",
                    "1...",
                    "4...",
                    "...",
                    "1...",
                    "1...",
                    "...",
                    "...",
                    "...",
                ],
            },
            use_container_width=True,
        )

    with col_right:
        st.subheader("📊 強勢股分布 (45 檔)")
        st.dataframe(
            {
                "代號": [3443, 2379, 1560, 3037, 2330, 2317, 2337, 6770, 2408],
                "官方名稱": [
                    "創意",
                    "瑞昱",
                    "中砂",
                    "欣興",
                    "台積電",
                    "鴻海",
                    "旺宏",
                    "力積電",
                    "南亞科",
                ],
                "效率籌碼共振分": [
                    6.697,
                    2.895,
                    1.868,
                    1.167,
                    1.118,
                    1.006,
                    0.964,
                    0.922,
                    0.855,
                ],
            },
            use_container_width=True,
        )

with tab3:
    st.info("雙法人Top100族群集中度比較內容")

with tab4:
    st.info("全市場快速查詢內容")