from datetime import datetime, timedelta
import io
import numpy as np
import pandas as pd
import requests
import streamlit as st

# ==================== 頁面設定 ====================
st.set_page_config(
    page_title="台股籌碼集中度 (外本比 + 投本比 + 千張大戶)",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("台股籌碼集中度 (外本比、投本比與千張大戶追蹤)")

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


@st.cache_data(ttl=86400)
def fetch_tdcc_data():
  """強健版集保 1-5 資料解析（支援多種編碼與容錯）"""
  tdcc_dict = {}
  url = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
  try:
    res = requests.get(url, timeout=20)
    if res.status_code == 200:
      df_tdcc = None
      for enc in ["utf-8-sig", "big5", "cp950"]:
        try:
          df_tdcc = pd.read_csv(
              io.BytesIO(res.content), encoding=enc, dtype=str
          )
          if df_tdcc is not None and len(df_tdcc.columns) >= 3:
            break
        except:
          continue

      if df_tdcc is not None:
        # 清理欄位名稱空白與 BOM
        df_tdcc.columns = [
            str(c).strip().replace("\ufeff", "") for c in df_tdcc.columns
        ]

        # 通常集保格式：第0欄是代號、中間是級距、最後一欄是百分比
        col_code = df_tdcc.columns[0]
        col_level = (
            df_tdcc.columns[2] if len(df_tdcc.columns) > 2 else df_tdcc.columns[1]
        )
        col_ratio = df_tdcc.columns[-1]

        # 整理代號與級距數值
        df_tdcc["clean_code"] = (
            df_tdcc[col_code]
            .astype(str)
            .str.replace(r"\D", "", regex=True)
            .str.zfill(4)
        )
        df_tdcc["level_num"] = pd.to_numeric(
            df_tdcc[col_level], errors="coerce"
        )
        df_tdcc["ratio_num"] = pd.to_numeric(
            df_tdcc[col_ratio].astype(str).str.replace(",", ""),
            errors="coerce",
        )

        # 篩選出 4 位數代號的資料
        df_tdcc = df_tdcc[
            df_tdcc["clean_code"].str.len() == 4
        ]  # 找出每一檔股票持股分級最高的那一列（即千張大戶級距）
        idx_max = df_tdcc.groupby("clean_code")["level_num"].idxmax()
        df_big = df_tdcc.loc[idx_max]

        for _, row in df_big.iterrows():
          c_4 = row["clean_code"]
          val = row["ratio_num"]
          if not pd.isna(val):
            tdcc_dict[c_4] = float(val)
  except Exception as e:
    print(f"TDCC error: {e}")

  return tdcc_dict


with st.spinner(
    "⏳ 正在同步證交所法人籌碼與集保中心【千張大戶持股比例】中..."
):
  (
      market_dict,
      latest_foreign_shares,
      latest_trust_shares,
      hist_foreign_shares,
      target_dates,
  ) = fetch_twse_data()
  tdcc_big_holders = fetch_tdcc_data()

latest_date = target_dates[0] if target_dates else ""

if latest_date:
  st.sidebar.success(
      f"📅 官方同步日：{latest_date[:4]}/{latest_date[4:6]}/{latest_date[6:]}"
  )
  st.sidebar.info(f"📊 集保大戶資料庫已載入：共對應 {len(tdcc_big_holders)} 檔")
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

    clean_c = str(code).strip().zfill(4)
    big_holder_pct = tdcc_big_holders.get(clean_c, 0.0)

    base_rows.append(
        {
            "代號": code,
            "官方名稱": info["官方名稱"],
            "發行總股數": shares,
            "收盤價": close_p,
            "市值(億)": round(market_cap_100m, 2),
            "千張大戶比例(%)": big_holder_pct,
            "外資買賣超股數": f_shares,
            "外資買賣超張數": f_shares / 1000,
            "投信買賣超股數": t_shares,
            "投信買賣超張數": t_shares / 1000,
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
        big_pct = row["千張大戶比例(%)"]

        tags = []
        if f_net > 0 and t_net > 0:
          tags.append("🔥 雙A合擊")
        elif f_net > 0:
          tags.append("外資獨買")
        elif t_net > 0:
          tags.append("投信獨買")

        # 大戶鎖碼註記
        if big_pct > 30.0:
          tags.append("💎 大戶鎖碼")

        if tags:
          return f"{name} [{' '.join(tags)}]"
        else:
          return name

      df["顯示名稱"] = df.apply(format_display_name, axis=1)
      return df

    df_all_enriched = enrich_data(df_market)

    # 1. 之外資買賣超 Top 50
    df_f_buy = (
        df_market[df_market["外資買賣超股數"] > 0]
        .sort_values(by="外資買賣超張數", ascending=False)
        .head(50)
    )
    df_top50 = enrich_data(df_f_buy)
    df_top50 = df_top50.sort_values(by="外本比(%)", ascending=False)
    df_top50.insert(0, "外本比排名", range(1, len(df_top50) + 1))

    # 2. 成交值 Top 100
    df_t_100 = df_market.sort_values(
        by="外資買賣超張數", ascending=False
    ).head(100)
    df_top100 = enrich_data(df_t_100)
    df_top100.insert(0, "排名", range(1, len(df_top100) + 1))

    # 3. 雙榜交叉比對
    top50_codes = set(df_top50["代號"])
    top100_codes = set(df_top100["代號"])
    cross_codes = top50_codes.intersection(top100_codes)

    df_cross = df_market[df_market["代號"].isin(cross_codes)].copy()
    df_cross = enrich_data(df_cross)
    df_cross = df_cross.sort_values(by="外本比(%)", ascending=False)
    df_cross.insert(0, "排序", range(1, len(df_cross) + 1))

    # 4. 千張大戶 Top 100（預設直接把大戶比例 > 0 的抓出來排序）
    df_tdcc_top100 = (
        df_market[df_market["千張大戶比例(%)"] > 0]
        .sort_values(by="千張大戶比例(%)", ascending=False)
        .head(100)
        .copy()
    )
    df_tdcc_top100 = enrich_data(df_tdcc_top100)
    df_tdcc_top100.insert(0, "大戶持股排名", range(1, len(df_tdcc_top100) + 1))

    # ==================== 頁面頂部：即時搜尋篩選面板 ====================
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
    tab_tdcc, tab_cross, tab_top50, tab_top100 = st.tabs(
        [
            "🐋 千張大戶 Top 100",
            "🎯 雙榜交叉比對",
            "🔥 外資買賣超 Top 50",
            "💰 成交值 Top 100",
        ]
    )

    with tab_tdcc:
      st.info(
          "💡 此表由集保中心 1-5 資料直接獨立計算，列出全台股 **【千張大戶持股比例(%)】** 最高的前 100 名！"
      )
      st.dataframe(
          df_tdcc_top100, use_container_width=True, hide_index=True, height=600
      )

    with tab_cross:
      st.info(
          "💡 此表呈現 **外本比(%)**、**投本比(%)** 以及集保中心 **【千張大戶比例(%)】**，並自動標註大戶鎖碼強勢股。"
      )
      st.dataframe(
          df_cross, use_container_width=True, hide_index=True, height=600
      )

    with tab_top50:
      st.dataframe(
          df_top50, use_container_width=True, hide_index=True, height=600
      )

    with tab_top100:
      st.dataframe(
          df_top100, use_container_width=True, hide_index=True, height=600
      )
else:
  st.info("💡 提示：請重新整理頁面以順利載入資料。")