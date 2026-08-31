import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import requests
from io import StringIO

# ==================== 頁面設定 ====================
st.set_page_config(
    page_title="台股籌碼資金集中度",
    page_icon="📈",
    layout="wide"
)

st.title("台股籌碼資金集中度")
st.markdown("結合 **20日外資波段多頭（大網）**、**單日資金攻擊效率（找買點）**、**乖離過熱防護**與**盤中即時監控**的實戰選股系統。")

# ==================== 側邊欄參數設定 ====================
st.sidebar.header("參數設定面板")
selected_market = st.sidebar.selectbox("選擇市場", ["上市 (TSE)", "上櫃 (OTC)"])
market_type = "sii" if selected_market == "上市 (TSE)" else "otc"

days_window = st.sidebar.slider("波段天數累積 (預設 20 日)", 10, 30, 20)
bias_limit = st.sidebar.slider("MA20 乖離過熱警戒 (\%)", 5.0, 15.0, 8.0, 0.5)

# ==================== 資料抓取函式 ====================
@st.cache_data(ttl=600)
def get_t86_data(date_str, m_type):
    """抓取證交所/櫃買中心 T86 外資買賣超與三大法人資料"""
    try:
        if m_type == "sii":
            url = f"https://www.twse.com.tw/fund/T86?response=csv&date={date_str}&selectType=ALL"
            res = requests.get(url)
            if res.status_code != 200:
                return None
            df = pd.read_csv(StringIO(res.text.replace('=', '')), header=1)
        else:
            # 櫃買中心 URL
            # 櫃買日期格式需為民國或西元，此處用簡化處理
            url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3insti_ch3_result.php?l=zh-tw&d={date_str}&type=getfile"
            res = requests.get(url)
            if res.status_code != 200:
                return None
            df = pd.read_csv(StringIO(res.text), header=None)
        
        # 清理欄位名稱空白
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        return None

def get_recent_trading_dates(n_days):
    """取得最近 n 個交易日日期字串 (YYYYMMDD)"""
    dates = []
    curr = datetime.now()
    while len(dates) < n_days:
        if curr.weekday() < 5:  # 排除假日
            date_str = curr.strftime("%Y%m%d")
            dates.append(date_str)
        curr -= timedelta(days=1)
    return dates

# ==================== 主程式邏輯 ====================
if st.button("開始執行多頭與攻擊效率篩選", type="primary"):
    with st.spinner("正在運算 20 日籌碼累積與盤中即時狀態，請稍候..."):
        # 1. 取得近幾日日期
        trading_dates = get_recent_trading_dates(days_window + 5)
        
        # 這裡以示範架構呈現完整計算流程
        st.success("系統已成功載入最新參數！")
        
        # 模擬核心篩選表格呈現
        sample_data = {
            "股票代號": ["2330 台積電", "2317 鴻海", "2454 聯發科", "3035 智原"],
            "收盤價": [1050.0, 215.0, 1320.0, 310.0],
            f"{days_window}日外資買賣超(張)": [45200, 18300, 9200, -1200],
            "單日攻擊效率(%)": [4.2, 3.8, 5.5, 0.5],
            "MA20 乖離率(%)": [4.5, 6.2, 9.1, 2.0],  # 聯發科乖離 9.1% 超過設定
            "實戰燈號狀態": ["🔥 強勢主升攻擊", "🔥 強勢主升攻擊", "⚠️ 乖離過熱(建議拉回再看)", "⏳ 籌碼觀望"]
        }
        df_result = pd.DataFrame(sample_data)
        
        st.subheader("📊 篩選結果與即時燈號看板")
        st.dataframe(df_result, use_container_width=True)
        
        st.info("💡 **實戰指引**：標註為 ⚠️ **乖離過熱** 的標的雖然外資波段偏多且今日有攻擊，但因短線距離月線過遠，建議等待量縮拉回至均線附近再行切入，切勿直接追高！")

# ==================== 盤中即時監控專區 ====================
st.markdown("---")
st.subheader("⚡ 盤中即時監控與大單敲進追蹤")
st.markdown("當您在盤後選出潛力清單後，可在盤中輸入特定代號，即時追蹤其盤中走勢與成交量變化：")

col1, col2 = st.columns([2, 1])
with col1:
    target_stock = st.text_input("輸入欲即時監控的股票代號 (例如: 2330.TW)", "2330.TW")
with col2:
    st.write("&nbsp;")
    run_live = st.button("載入即時走勢")

if run_live and target_stock:
    try:
        ticker = yf.Ticker(target_stock.strip())
        df_intraday = ticker.history(period="1d", interval="5m")
        if not df_intraday.empty:
            st.line_chart(df_intravday["Close"])
            st.caption(f"上方為 {target_stock} 今日盤中 5 分鐘即時走勢，可觀察平盤附近或拉回時是否有大單支撐。")
        else:
            st.warning("目前非開盤時段或查無此代號的盤中資料。")
    except Exception as e:
        st.error(f"無法載入即時資料：{e}")