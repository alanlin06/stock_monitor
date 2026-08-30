import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# 設定網頁版面
st.set_page_config(
    page_title="台股外資籌碼與專屬排行終端機", page_icon="📈", layout="wide"
)

st.title("🎯 雙榜交叉比對：外資本比 Top 50 ∩ 成交值 Top 100")
st.markdown(
    "💡 此處自動篩選同時名列「當日外本比 Top 50」與「全市場成交值 Top 100」的雙榜強勢個股，並依外本比由高低排序！名稱旁已自動轉為直覺的【週K/日K】雙 K 棒圖示。"
)


# --- 模擬或呼叫你原本計算資料的邏輯 ---
# （若你的環境中有真實的爬蟲與均價線計算，請確保回傳的欄位包含「官方名稱」與多空狀態）
@st.cache_data
def load_chip_terminal_data():
    # 這是對應你畫面截圖結構的範例資料
    data = {
        "交叉排行": [1, 2, 3, 4, 5, 6],
        "代號": ["2886", "2892", "0050", "2880", "0052", "6239"],
        "官方名稱": [
            "兆豐金",
            "第一金",
            "元大台灣50",
            "華南金",
            "富邦科技",
            "力成",
        ],
        "外本比(%)": [68.086, 63.488, 52.596, 46.627, 36.834, 34.072],
        "狀態": [
            "雙多",
            "雙多",
            "長多短空",
            "長多短空",
            "長多短空",
            "短多長空",
        ],
    }
    return pd.DataFrame(data)


df = load_chip_terminal_data()


# --- 轉換多空狀態為 K 棒視覺圖示的函式 ---
def convert_status_to_k_bars(status):
    """將文字多空狀態轉化為直覺的雙K棒符號

    左邊代表週K（長線），右邊代表日K（短線）
    🔴 = 紅K（多方）
    🟢 = 綠K（空方）
    """
    if "雙多" in status:
        return "🔴🔴 雙多"
    elif "雙空" in status:
        return "🟢🟢 雙空"
    elif "長多短空" in status:
        return "🔴🟢 長多短空"
    elif "長空短多" in status or "短多長空" in status:
        return "🟢🔴 長空短多"
    return status


# 將原本的「官方名稱 (狀態)」直接替換成帶有 K 棒的格式
df["官方名稱"] = df.apply(
    lambda row: f"{row['官方名稱']} ({convert_status_to_k_bars(row['狀態'])})",
    axis=1,
)

# 移除已經合併進名稱的暫存狀態欄位
df = df.drop(columns=["狀態"])


# --- 側邊欄設定 ---
st.sidebar.header("⚙️ 排序與檢視設定")
sort_option = st.sidebar.selectbox(
    "Top 50 主表格排序依據：",
    ["外本比 (外資買超股數佔發行總股數)"],
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 指標與 K 棒圖示說明：")
st.sidebar.markdown(
    "- **🔴🔴 雙多**：週K與日K皆站上多空成本均價線（強勢多頭）"
)
st.sidebar.markdown(
    "- **🟢🟢 雙空**：週K與日K皆跌破多空成本均價線（弱勢空頭）"
)
st.sidebar.markdown(
    "- **🔴🟢 長多短空**：週K長線偏多、日K短線回檔休息"
)
st.sidebar.markdown(
    "- **🟢🔴 長空短多**：週K長線偏空、日K短線反彈向上"
)
st.sidebar.markdown(
    "- **外本比 (%)**：(外資買超股數 ÷ 官方發行總股數) × 100%。"
)
st.sidebar.markdown("### 📅 官方同步交易日：")
st.sidebar.info("2026/08/28")


# --- 主畫面表格呈現 ---
st.subheader("📋 雙榜交叉比對 全部標的清單")
st.markdown(
    "📍 **提示**：點擊下方表格任一列，即可直接在下方載入該標的的日K/週K走勢圖！"
)

# 顯示互動表格
st.dataframe(df, use_container_width=True, hide_index=True)