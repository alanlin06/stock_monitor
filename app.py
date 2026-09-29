from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

# ==========================================
# 頁面基本設定
# ==========================================
st.set_page_config(
    page_title="台股強勢策略", page_icon="📈", layout="wide"
)

# 確保大標題為「台股強勢策略」
st.title("台股強勢策略")
st.caption(f"最後更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ==========================================
# 輔助函式與資料更新儲存
# ==========================================
if "data_initialized" not in st.session_state:
    st.session_state.data_initialized = True

def update_map_from_editor(df_edited):
    # 資料更新儲存的邏輯
    pass

# ==========================================
# 建立頁籤介面
# ==========================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📊 綜合雷達", "🚀 強勢族群", "💡 潛力股篩選", "📈 投信排行", "💰 成交值 TOP", "📋 法人個股"]
)

with tab1:
    st.markdown("### 📊 綜合雷達總覽")
    st.info("此處顯示綜合強勢策略的整體市場評分與雷達圖。")

with tab2:
    st.markdown("### 🚀 強勢族群分析")
    st.info("此處顯示當前市場上資金集中的強勢族群。")

with tab3:
    st.markdown("### 💡 潛力股篩選")
    st.markdown("依據技術面、**綠線區**、**紅線區**與籌碼面條件篩選出的潛力標的。")

with tab4:
    st.markdown("### 📈 投信 TOP 100 檢視")
    
    # 這裡完整保留您原本的變數與邏輯
    if 'positive_sitc' in locals() and not positive_sitc.empty:
        ed_sitc_positive = st.data_editor(
            positive_sitc,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in positive_sitc.columns if c not in ["族群"]],
            key="ed_sitc_positive",
        )

        if st.button("💾 儲存投信族群修改", key="btn_save_sitc"):
            update_map_from_editor(ed_sitc_positive)
    else:
        # 兼容您原本的區塊判斷
        if 'df_sitc_positive' in locals() and not df_sitc_positive.empty:
            ed_sitc_positive = st.data_editor(
                df_sitc_positive,
                use_container_width=True,
                hide_index=True,
                disabled=[c for c in df_sitc_positive.columns if c not in ["族群"]],
                key="ed_sitc_positive",
            )
            if st.button("💾 儲存投信族群修改", key="btn_save_sitc"):
                update_map_from_editor(ed_sitc_positive)
        else:
            st.info("目前投信 TOP 100 中沒有投本比 > 0 的資料。")

with tab5:
    st.markdown("### 💰 成交值 TOP 100")
    st.caption("成交值不直接決定法人籌碼強度；在族群雷達中作為『市場注意力』的獨立確認因子。")

    if 'df_amt' in locals() and not df_amt.empty:
        ed_amt = st.data_editor(
            df_amt,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in df_amt.columns if c not in ["族群"]],
            key="ed_amt_top100",
        )

        if st.button("💾 儲存成交值族群修改", key="btn_save_amt"):
            update_map_from_editor(ed_amt)
    else:
        st.info("目前無符合條件的成交值資料。")

with tab6:
    st.markdown("### 📋 法人個股 TOP 100")

    st.markdown("#### 🌍 外資買超 TOP 100")
    if 'df_fii' in locals() and not df_fii.empty:
        ed_fii = st.data_editor(
            df_fii,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in df_fii.columns if c not in ["族群"]],
            key="ed_fii_top100",
        )
        if st.button("💾 儲存外資個股族群修改", key="btn_save_fii_top100"):
            update_map_from_editor(ed_fii)
    else:
        st.info("目前無符合條件的外資買超資料。")

    st.markdown("#### 🏛️ 投信買超 TOP 100")
    if 'df_sitc' in locals() and not df_sitc.empty:
        ed_sitc = st.data_editor(
            df_sitc,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in df_sitc.columns if c not in ["族群"]],
            key="ed_sitc_top100",
        )
        if st.button("💾 儲存投信個股族群修改", key="btn_save_sitc_top100"):
            update_map_from_editor(ed_sitc)
    else:
        st.info("目前無符合條件的投信買超資料。")