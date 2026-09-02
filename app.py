from datetime import datetime, timedelta
import json
import os
import pandas as pd
import requests
import streamlit as st

# ==================== 頁面設定 ====================
st.set_page_config(
    page_title="台股籌碼集中度 (外本比 + 投本比)",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("台股籌碼集中度 (外本比、投本比與強勢股追蹤)")

# ==================== 本地 JSON 檔案持久化記憶功能 ====================
DB_FILE = "industry_db.json"


def load_db():
  if os.path.exists(DB_FILE):
    try:
      with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      pass
  return {
      "2330": "半導體(晶圓代工)",
      "3711": "半導體(封測)",
      "2449": "半導體(封測)",
      "2382": "AI伺服器",
      "3231": "AI伺服器",
      "2356": "AI伺服器",
      "6669": "AI伺服器/矽智財",
  }


def save_db(db_data):
  try:
    with open(DB_FILE, "w", encoding="utf-8") as f:
      json.dump(db_data, f, ensure_ascii=False, indent=4)
  except Exception as e:
    st.error(f"儲存檔案失敗: {e}")


if "user_industry_map" not in st.session_state:
  st.session_state.user_industry_map = load_db()

# ==================== 側邊欄參數與即時搜尋 ====================
st.sidebar.header("實戰參數與查找")
search_query = st.sidebar.text_input(
    "🔍 側邊欄快速查找台股", placeholder="輸入代號或名稱 (例: 2330)"
)


@st.cache_data(ttl=600)
def fetch_twse_data():
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept": "application/json, text/javascript, */*; q=0.01",
      "Accept-Language": "zh-TW,zh;q=0.09,en-US;q=0.8,en;q=0.7",
      "Referer": "https://www.twse.com.tw/",
  }

  curr = datetime.now()
  dates = []

  while len(dates) < 25 and (datetime.now() - curr).days < 60:
    if curr.weekday() < 5:
      d_str = curr.strftime("%Y%m%d")
      test_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d_str}&selectType=ALL"
      try:
        res = requests.get(test_url, headers=headers, timeout=5)
        if res.status_code == 200:
          data = res.json()
          if data.get("stat") == "OK" and len(data.get("data", [])) > 0:
            dates.append(d_str)
      except Exception:
        pass
    curr -= timedelta(days=1)

  if not dates:
    return {}, {}, {}, [], []

  latest_date = dates[0]
  mi_url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999&date={latest_date}"
  market_dict = {}

  try:
    res = requests.get(mi_url, headers=headers, timeout=8)
    if res.status_code == 200:
      data = res.json()
      if data.get("stat") == "OK":
        for table in data.get("tables", []):
          if "data" in table:
            for row in table["data"]:
              if len(row) > 10:
                code = row[0].strip()
                if len(code) == 4 and code.isdigit():
                  try:
                    name = row[1].strip()
                    issued_shares_total_raw = float(
                        row[2].replace(",", "")
                    )
                    close_price = float(row[8].replace(",", ""))

                    market_dict[code] = {
                        "官方名稱": name,
                        "發行總股數": issued_shares_total_raw,
                        "收盤價": close_price,
                    }
                  except Exception:
                    continue
  except Exception as e:
    print(f"MI_INDEX error: {e}")

  latest_foreign_shares = {}
  latest_trust_shares = {}
  hist_foreign_shares = {}
  for i, d_str in enumerate(dates):
    t86_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d_str}&selectType=ALL"
    try:
      res = requests.get(t86_url, headers=headers, timeout=5)
      if res.status_code == 200:
        data = res.json()
        if data.get("stat") == "OK":
          raw_rows = data.get("data", [])
          day_map = {}
          for r in raw_rows:
            if len(r) > 10:
              code = r[0].strip()
              if len(code) == 4 and code.isdigit():
                try:
                  net_foreign = int(r[4].replace(",", ""))
                  net_trust = int(r[10].replace(",", ""))

                  day_map[code] = net_foreign
                  if i == 0:
                    latest_foreign_shares[code] = net_foreign
                    latest_trust_shares[code] = net_trust
                except Exception:
                  continue
          hist_foreign_shares[d_str] = day_map
    except Exception:
      continue

  return (
      market_dict,
      latest_foreign_shares,
      latest_trust_shares,
      hist_foreign_shares,
      dates,
  )


with st.spinner("⏳ 正在載入台股籌碼與您的專屬族群資料..."):
  (
      market_dict,
      latest_foreign_shares,
      latest_trust_shares,
      hist_foreign_shares,
      target_dates,
  ) = fetch_twse_data()

latest_date = target_dates[0] if target_dates else ""

if latest_date:
  st.sidebar.success(
      f"📅 官方同步日：{latest_date[:4]}/{latest_date[4:6]}/{latest_date[6:]}"
  )
else:
  st.error("⚠️ 無法取得證交所官方資料，請重新整理頁面。")

if market_dict:
  base_rows = []
  for code, info in market_dict.items():
    f_shares = latest_foreign_shares.get(code, 0)
    t_shares = latest_trust_shares.get(code, 0)
    close_p = info["收盤價"]
    shares = info["發行總股數"]
    market_cap_100m = (close_p * shares) / 100000000

    assigned_ind = st.session_state.user_industry_map.get(code, "")

    base_rows.append(
        {
            "代號": code,
            "官方名稱": info["官方名稱"],
            "發行總股數": shares,
            "收盤價": close_p,
            "市值(億)": round(market_cap_100m, 2),
            "外資買賣超股數": f_shares,
            "外資買賣超張數": f_shares / 1000,
            "投信買賣超股數": t_shares,
            "投信買賣超張數": t_shares / 1000,
            "族群": assigned_ind,
        }
    )

  df_market = pd.DataFrame(base_rows)

  if not df_market.empty:

    def enrich_data(df):
      df = df.copy()
      df["外本比(%)"] = df.apply(
          lambda row: round((row["外資買賣超股數"] / row["發行總股數"]) * 100, 3)
          if row["發行總股數"] > 0
          else 0.0,
          axis=1,
      )
      df["投本比(%)"] = df.apply(
          lambda row: round((row["投信買賣超股數"] / row["發行總股數"]) * 100, 3)
          if row["發行總股數"] > 0
          else 0.0,
          axis=1,
      )

      df["雙法人總集中度(%)"] = round(df["外本比(%)"] + df["投本比(%)"], 3)

      def calc_20d_metrics(code):
        active_streak = 0
        for d_str in target_dates:
          if (
              code in hist_foreign_shares.get(d_str, {})
              and hist_foreign_shares[d_str][code] > 0
          ):
            active_streak += 1
          else:
            break
        return active_streak

      df["連續買超天數"] = df["代號"].apply(calc_20d_metrics)

      def format_display_name(row):
        name = row["官方名稱"]
        f_net = row["外資買賣超股數"]
        t_net = row["投信買賣超股數"]

        tags = []
        if f_net > 0 and t_net > 0:
          tags.append("🔥 雙A合擊")
        elif f_net > 0:
          tags.append("外資獨買")
        elif t_net > 0:
          tags.append("投信獨買")

        if tags:
          return f"{name} [{' '.join(tags)}]"
        else:
          return name

      df["顯示名稱"] = df.apply(format_display_name, axis=1)

      cols = list(df.columns)
      if "雙法人總集中度(%)" in cols:
        cols.remove("雙法人總集中度(%)")
        idx = cols.index("外本比(%)") if "外本比(%)" in cols else 0
        cols.insert(idx, "雙法人總集中度(%)")

      if "族群" in cols:
        cols.remove("族群")
        cols.append("族群")

      df = df[cols]
      return df

    df_all_enriched = enrich_data(df_market)

    # 1. 外資買賣超 Top 100
    df_f_buy = (
        df_market[df_market["外資買賣超股數"] > 0]
        .sort_values(by="外資買賣超張數", ascending=False)
        .head(100)
    )
    df_top100_foreign = enrich_data(df_f_buy)
    df_top100_foreign = df_top100_foreign.sort_values(
        by="雙法人總集中度(%)", ascending=False
    )
    df_top100_foreign.insert(
        0, "排名", range(1, len(df_top100_foreign) + 1)
    )

    # 2. 成交值 / 市值 Top 100
    df_v_100 = df_market.sort_values(by="市值(億)", ascending=False).head(100)
    df_top100 = enrich_data(df_v_100)
    df_top100.insert(0, "排名", range(1, len(df_top100) + 1))

    # 3. 雙榜交叉比對 (外資 Top 100 ∩ 成交值 Top 100)
    top_foreign_codes = set(df_top100_foreign["代號"])
    top100_codes = set(df_top100["代號"])
    cross_codes = top_foreign_codes.intersection(top100_codes)

    df_cross = df_market[df_market["代號"].isin(cross_codes)].copy()
    df_cross = enrich_data(df_cross)
    df_cross = df_cross.sort_values(by="雙法人總集中度(%)", ascending=False)
    df_cross.insert(0, "排序", range(1, len(df_cross) + 1))

    # ==================== 計算族群平均集中度統計 ====================
    df_all_calculated = enrich_data(df_market)
    df_grouped_raw = df_all_calculated[
        df_all_calculated["族群"].str.strip() != ""
    ]

    if not df_grouped_raw.empty:
      df_industry_summary = (
          df_grouped_raw.groupby("族群")
          .agg(
              股票檔數=("代號", "count"),
              平均外本比_pct=("外本比(%)", "mean"),
              平均投本比_pct=("投本比(%)", "mean"),
              平均雙法人總集中度_pct=("雙法人總集中度(%)", "mean"),
          )
          .reset_index()
      )

      df_industry_summary["平均外本比_pct"] = df_industry_summary[
          "平均外本比_pct"
      ].round(3)
      df_industry_summary["平均投本比_pct"] = df_industry_summary[
          "平均投本比_pct"
      ].round(3)
      df_industry_summary["平均雙法人總集中度_pct"] = df_industry_summary[
          "平均雙法人總集中度_pct"
      ].round(3)

      df_industry_summary = df_industry_summary.rename(
          columns={
              "平均外本比_pct": "平均外本比(%)",
              "平均投本比_pct": "平均投本比(%)",
              "平均雙法人總集中度_pct": "平均雙法人總集中度(%)",
          }
      )

      # 💡 新增過濾邏輯：
      # 1. 平均雙法人總集中度必須 > 0
      # 2. 平均外本比必須 >= 0 (排除負數)
      # 3. 平均投本比必須 >= 0 (排除負數)
      df_industry_summary = df_industry_summary[
          (df_industry_summary["平均雙法人總集中度(%)"] > 0)
          & (df_industry_summary["平均外本比(%)"] >= 0)
          & (df_industry_summary["平均投本比(%)"] >= 0)
      ]

      df_industry_summary = df_industry_summary.sort_values(
          by="平均雙法人總集中度(%)", ascending=False
      )
      
      # 重新編排排名序號
      if not df_industry_summary.empty:
        df_industry_summary.insert(0, "排名", range(1, len(df_industry_summary) + 1))
      else:
        df_industry_summary.insert(0, "排名", [])
    else:
      df_industry_summary = pd.DataFrame(
          columns=[
              "排名",
              "族群",
              "股票檔數",
              "平均外本比(%)",
              "平均投本比(%)",
              "平均雙法人總集中度(%)",
          ]
      )

    # ==================== 搜尋與過濾面板 ====================
    st.markdown("### 🔍 任意台股快速查找與篩選")
    col_input, _ = st.columns([1, 3])
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
        st.success(f"找到符合「{direct_search}」的股票：")
        st.dataframe(matched_df, use_container_width=True, hide_index=True)
      else:
        st.warning("查無此台股代號或名稱，請確認輸入是否正確。")
      st.markdown("---")

    # ==================== 分頁顯示排行榜 ====================
    tab_ind_summary, tab_cross, tab_top100_f, tab_top100_v = st.tabs(
        [
            "📈 族群籌碼平均排行",
            "🎯 雙榜交叉比對",
            "🔥 外資買賣超 Top 100",
            "💰 成交值 Top 100",
        ]
    )

    with tab_ind_summary:
      st.info(
          "💡 **族群平均分析說明**：系統會自動計算各族群平均，並**已自動過濾掉總集中度 ≤ 0、或是平均外本比/投本比任一項為負數**的族群，確保留下的都是雙多方齊心強勢的產業！"
      )
      if not df_industry_summary.empty:
        st.dataframe(
            df_industry_summary,
            use_container_width=True,
            hide_index=True,
            height=500,
        )
      else:
        st.warning(
            "目前沒有符合條件的族群（外本比與投本比皆須非負數，且總集中度須大於0）。"
        )

    with tab_cross:
      st.info(
          "💡 **操作說明**：此頁面顯示 **外資買超 Top 100** 與 **成交值 Top 100** 的交集個股。在表格最後一欄的「族群」打字後，點擊下方的**「💾 儲存並寫入永久檔案」**，資料就會寫入電腦硬碟中！"
      )

      edited_df_cross = st.data_editor(
          df_cross,
          use_container_width=True,
          hide_index=True,
          height=500,
          disabled=[
              col
              for col in df_cross.columns
              if col != "族群" and col != "排序"
          ],
          key="editor_cross",
      )

      if st.button("💾 儲存並寫入永久檔案 (交叉比對)", type="primary"):
        for _, row in edited_df_cross.iterrows():
          c = row["代號"]
          ind = row["族群"]
          if pd.notna(ind) and str(ind).strip() != "":
            st.session_state.user_industry_map[c] = str(ind).strip()
          else:
            if c in st.session_state.user_industry_map:
              del st.session_state.user_industry_map[c]
        save_db(st.session_state.user_industry_map)
        st.success(
            "🎉 族群資料已成功寫入硬碟檔案！重新整理或重開程式都會完美記憶！"
        )
        st.rerun()

    with tab_top100_f:
      edited_df_top100_f = st.data_editor(
          df_top100_foreign,
          use_container_width=True,
          hide_index=True,
          height=500,
          disabled=[
              col
              for col in df_top100_foreign.columns
              if col != "族群" and col != "排名"
          ],
          key="editor_top100_f",
      )
      if st.button("💾 儲存並寫入永久檔案 (外資 Top 100)", type="secondary"):
        for _, row in edited_df_top100_f.iterrows():
          c = row["代號"]
          ind = row["族群"]
          if pd.notna(ind) and str(ind).strip() != "":
            st.session_state.user_industry_map[c] = str(ind).strip()
          else:
            if c in st.session_state.user_industry_map:
              del st.session_state.user_industry_map[c]
        save_db(st.session_state.user_industry_map)
        st.success("🎉 族群資料已成功寫入硬碟檔案！")
        st.rerun()

    with tab_top100_v:
      edited_df_top100 = st.data_editor(
          df_top100,
          use_container_width=True,
          hide_index=True,
          height=500,
          disabled=[
              col
              for col in df_top100.columns
              if col != "族群" and col != "排名"
          ],
          key="editor_top100",
      )
      if st.button("💾 儲存並寫入永久檔案 (成交值 Top 100)", type="secondary"):
        for _, row in edited_df_top100.iterrows():
          c = row["代號"]
          ind = row["族群"]
          if pd.notna(ind) and str(ind).strip() != "":
            st.session_state.user_industry_map[c] = str(ind).strip()
          else:
            if c in st.session_state.user_industry_map:
              del st.session_state.user_industry_map[c]
        save_db(st.session_state.user_industry_map)
        st.success("🎉 族群資料已成功寫入硬碟檔案！")
        st.rerun()

else:
  st.info("💡 提示：請重新整理頁面以順利載入資料。")