import streamlit as st
import pandas as pd
import numpy as np

# 頁面基本設定
st.set_page_config(page_title="台股強勢策略分析系統", layout="wide")

st.title("🚀 台股多維度強勢策略與資金鎖定系統")
st.markdown("---")

# ==========================================
# 模擬資料生成與核心篩選邏輯（可在此處對接真實 API 或爬蟲）
# ==========================================
@st.cache_data
def load_market_data():
    # 模擬全市場股票資料
    np.random.seed(42)
    stock_count = 300
    
    codes = [str(i) for i in range(1101, 1101 + stock_count)]
    names = [f"股票_{i}" for i in codes]
    # 塞入一些常見標的方便對照
    names[0] = "台積電"
    codes[0] = "2330"
    names[1] = "鴻海"
    codes[1] = "2317"
    names[2] = "聯發科"
    codes[2] = "2454"
    names[3] = "台塑"
    codes[3] = "1301"
    names[4] = "台化"
    codes[4] = "1326"

    sectors = ["半導體", "AI伺服器", "IC載板", "石化塑膠", "金融保險", "航運", "汽車零組件", "通訊網路"]
    
    df = pd.DataFrame({
        "代號": codes,
        "官方名稱": names,
        "族群": np.random.choice(sectors, stock_count),
        "收盤價": np.random.uniform(20, 1000, stock_count).round(2),
        "漲跌幅(%)": np.random.uniform(-3.5, 7.5, stock_count).round(2),
        "成交值(億)": np.random.uniform(0.5, 120, stock_count).round(2),
        "外資買超(張)": np.random.randint(-5000, 12000, stock_count),
        "投信買超(張)": np.random.randint(-2000, 6000, stock_count),
    })
    
    # 計算 AI 20日通道模型 (模擬 MA20 與標準差)
    df["MA20"] = (df["收盤價"] * np.random.uniform(0.95, 1.05, stock_count)).round(2)
    df["通道標準差"] = df["收盤價"] * 0.05
    df["上軌"] = df["MA20"] + (2.0 * df["通道標準差"])
    df["下軌"] = df["MA20"] - (2.0 * df["通道標準差"])
    
    # AI 訊號狀態判定
    def get_ai_signal(row):
        if row["收盤價"] >= row["上軌"]:
            return "🔴 處於高檔區"
        elif row["收盤價"] <= row["下軌"]:
            return "🟢 處於低檔區"
        else:
            return "⚪ 盤整區間"
            
    df["🤖 AI訊號狀態"] = df.apply(get_ai_signal, axis=1)
    return df

raw_df = load_market_data()

# ==========================================
# 嚴格條件篩選 (僅限上漲: 漲跌幅 > 0)
# ==========================================
up_df = raw_df[raw_df["漲跌幅(%)"] > 0].copy()

# 1. 成交值排行 TOP 100 (且上漲)
top_value_100 = up_df.nlargest(100, "成交值(億)")

# 2. 外資買超 TOP 100 (且上漲)
top_foreign_100 = up_df.nlargest(100, "外資買超(張)")

# 3. 投信買超 TOP 100 (且上漲)
top_trust_100 = up_df.nlargest(100, "投信買超(張)")

# 4. 同步鎖定：同時名列成交值、外資、投信前段班，或雙法人同步大買且上漲的強勢股
sync_locked_df = up_df[
    (up_df["外資買超(張)"] > 1000) & 
    (up_df["投信買超(張)"] > 500) & 
    (up_df["成交值(億)"] > 10)
].copy()

# ==========================================
# 介面分頁建構 (最左側開始：族群集中、同步鎖定、三大排行榜)
# ==========================================
tab_sector, tab_sync, tab_value, tab_foreign, tab_trust = st.tabs([
    "📊 族群集中", 
    "🔥 同步鎖定", 
    "💰 成交值排行 TOP 100", 
    "🌍 外資買超 TOP 100", 
    "🏛️ 投信買超 TOP 100"
])

# --- 分頁 1：族群集中 ---
with tab_sector:
    st.subheader("📊 當前上漲強勢股之族群集中度分析")
    st.markdown("統計目前符合上漲條件的標的中，各大產業族群分佈與家數狀況。")
    
    if not up_df.empty:
        sector_summary = up_df.groupby("族群").agg(
            上漲家數=("代號", "count"),
            平均漲幅=("漲跌幅(%)", "mean"),
            總成交值_億=("成交值(億)", "sum")
        ).reset_index().sort_values(by="上漲家數", ascending=False)
        
        sector_summary["平均漲幅"] = sector_summary["平均漲幅"].round(2)
        sector_summary["總成交值_億"] = sector_summary["總成交值_億"].round(2)
        
        col1, col2 = st.columns([1, 1])
        with col1:
            st.dataframe(sector_summary, use_container_width=True, hide_index=True)
        with col2:
            st.bar_chart(sector_summary.set_index("族群")["上漲家數"])
    else:
        st.warning("目前沒有符合上漲條件的標的。")

# --- 分頁 2：同步鎖定 ---
with tab_sync:
    st.subheader("🔥 雙法人同步鎖定與主力資金點名")
    st.markdown("篩選條件：**今日股價上漲** 且 **外資買超 > 1000張、投信買超 > 500張、成交值 > 10億** 的核心強勢股。")
    
    if not sync_locked_df.empty:
        display_cols = ["代號", "官方名稱", "族群", "收盤價", "漲跌幅(%)", "成交值(億)", "外資買超(張)", "投信買超(張)", "🤖 AI訊號狀態"]
        st.dataframe(sync_locked_df[display_cols], use_container_width=True, hide_index=True)
    else:
        st.info("今日目前無同時符合雙法人高度鎖定且上漲的標的。")

# --- 分頁 3：成交值排行 TOP 100 ---
with tab_value:
    st.subheader("💰 成交值排行 TOP 100 (僅顯示上漲)")
    st.markdown("全市場成交金額最高的前 100 名，且**排除下跌股票**，確保資金動能強勁。")
    display_cols = ["代號", "官方名稱", "族群", "收盤價", "漲跌幅(%)", "成交值(億)", "外資買超(張)", "投信買超(張)", "🤖 AI訊號狀態"]
    st.dataframe(top_value_100[display_cols], use_container_width=True, hide_index=True)

# --- 分頁 4：外資買超 TOP 100 ---
with tab_foreign:
    st.subheader("🌍 外資買超 TOP 100 (僅顯示上漲)")
    st.markdown("外資單日買超張數最多的前 100 名，且今日股價呈現上漲的強勢標的。")
    display_cols = ["代號", "官方名稱", "族群", "收盤價", "漲跌幅(%)", "成交值(億)", "外資買超(張)", "投信買超(張)", "🤖 AI訊號狀態"]
    st.dataframe(top_foreign_100[display_cols], use_container_width=True, hide_index=True)

# --- 分頁 5：投信買超 TOP 100 ---
with tab_trust:
    st.subheader("🏛️ 投信買超 TOP 100 (僅顯示上漲)")
    st.markdown("投信（內資主力）積極認養、買超張數最多的前 100 名上漲強勢股。")
    display_cols = ["代號", "官方名稱", "族群", "收盤價", "漲跌幅(%)", "成交值(億)", "外資買超(張)", "投信買超(張)", "🤖 AI訊號狀態"]
    st.dataframe(top_trust_100[display_cols], use_container_width=True, hide_index=True)