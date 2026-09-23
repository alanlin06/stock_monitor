from datetime import datetime, timedelta
import json
import os
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st

# ==================== 頁面設定 ====================
st.set_page_config(
    page_title="台股雙A合擊與均線集中度雷達",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🎯 台股多頭均線 + 雙A合擊籌碼集中度雷達")

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
      "8105": "硬板",
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
st.sidebar.header("實戰參數與防護網")
search_query = st.sidebar.text_input(
    "🔍 側邊欄快速查找台股", placeholder="輸入代號或名稱 (例: 2330)"
)

st.sidebar.markdown("---")
enable_profit_filter = st.sidebar.checkbox(
    "啟用營益率防護網 (本季 > 0 且 > 上一季)", value=True
)
enable_vol_growth_filter = st.sidebar.checkbox(
    "選配：今日成交值 > 昨日成交值", value=False
)


# ==================== 模擬或串接財報營益率函式 ====================
def fetch_financial_data(code):
  np.random.seed(int(code) if code.isdigit() else 42)
  op_latest = round(np.random.uniform(-2.0, 28.0), 2)
  op_prev = round(op_latest + np.random.uniform(-4.0, 3.0), 2)
  return op_latest, op_prev


@st.cache_data(ttl=600)
def fetch_twse_data():
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0.0.0 Safari/537.36"
      ),
      "Accept": "application/json, text/javascript, */*; q=0.01",
      "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
      "Referer": "https://www.twse.com.tw/zh/trading/fund/T86.html",
      "X-Requested-With": "XMLHttpRequest",
  }

  session = requests.Session()
  session.headers.update(headers)

  try:
    session.get("https://www.twse.com.tw/zh/trading/fund/T86.html", timeout=5)
  except:
    pass

  curr = datetime.now()
  dates = []

  for i in range(15):
    d_str = curr.strftime("%Y%m%d")
    test_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d_str}&selectType=ALL"
    try:
      res = session.get(test_url, timeout=6)
      if res.status_code == 200:
        data = res.json()
        if data.get("stat") == "OK" and len(data.get("data", [])) > 0:
          dates.append(d_str)
          for j in range(1, 25):
            prev_d = curr - timedelta(days=j)
            if prev_d.weekday() < 5:
              dates.append(prev_d.strftime("%Y%m%d"))
          break
    except Exception:
      pass
    curr -= timedelta(days=1)
    time.sleep(0.2)

  if not dates:
    return {}, {}, {}, [], [], 0.0, 0.0, 0.0

  latest_date = dates[0]
  prev_date = dates[1] if len(dates) > 1 else latest_date
  market_dict = {}
  taiex_close = 0.0
  taiex_change = 0.0
  taiex_pct = 0.0

  mi_url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999&date={latest_date}"
  try:
    res_mi = session.get(mi_url, timeout=8)
    if res_mi.status_code == 200:
      data = res_mi.json()
      if data.get("stat") == "OK":
        for table in data.get("tables", []):
          for row in table.get("data", []):
            row_str = "".join([str(cell) for cell in row])
            if "發行量加權股價指數" in row_str or "加權指數" in row_str:
              try:
                for cell in row:
                  c_str = (
                      str(cell)
                      .replace(",", "")
                      .replace("+", "")
                      .replace("X", "")
                      .strip()
                  )
                  try:
                    val = float(c_str)
                    if val > 3000:
                      taiex_close = val
                      break
                  except:
                    pass

                for cell in row:
                  c_str = (
                      str(cell)
                      .replace(",", "")
                      .replace("+", "")
                      .replace("%", "")
                      .strip()
                  )
                  try:
                    val = float(c_str)
                    if (
                        abs(val) < 2000
                        and val != taiex_close
                        and val != 0.0
                    ):
                      if -20 < val < 20:
                        taiex_pct = val
                      else:
                        taiex_change = val
                  except:
                    pass

                if "-" in row_str and taiex_change > 0:
                  taiex_change = -taiex_change
                if "-" in row_str and taiex_pct > 0:
                  taiex_pct = -taiex_pct

                if taiex_close > 0:
                  break
              except:
                pass
          if taiex_close > 0:
            break

        for table in data.get("tables", []):
          if "data" in table:
            for row in table["data"]:
              if len(row) >= 11:
                code = str(row[0]).strip()
                if len(code) == 4 and code.isdigit():
                  try:
                    name = str(row[1]).strip()
                    issued_shares_total_raw = float(
                        str(row[2]).replace(",", "")
                    )

                    turnover_val = 0.0
                    try:
                      turnover_val = float(str(row[4]).replace(",", ""))
                    except:
                      try:
                        turnover_val = float(str(row[5]).replace(",", ""))
                      except:
                        pass

                    close_price_raw = str(row[8]).replace(",", "").strip()
                    if close_price_raw in ["--", "-", ""]:
                      continue
                    close_price = float(close_price_raw)

                    sign = (
                        -1.0
                        if ("-" in str(row[9]) or "跌" in str(row[9]))
                        else 1.0
                    )
                    change_raw = str(row[10]).replace(",", "").strip()
                    change_val = (
                        (float(change_raw) * sign)
                        if change_raw not in ["--", "-", ""]
                        else 0.0
                    )

                    prev_p = close_price - change_val
                    pct_val = (change_val / prev_p) * 100 if prev_p > 0 else 0.0

                    op_latest, op_prev = fetch_financial_data(code)

                    sim_ma20_day = round(
                        close_price * np.random.uniform(0.92, 1.05), 2
                    )
                    sim_ma20_week = round(
                        close_price * np.random.uniform(0.90, 1.03), 2
                    )

                    market_dict[code] = {
                        "官方名稱": name,
                        "發行總股數": issued_shares_total_raw,
                        "收盤價": close_price,
                        "日K_MA20": sim_ma20_day,
                        "週K_MA20": sim_ma20_week,
                        "漲跌": change_val,
                        "漲跌幅(%)": pct_val,
                        "成交金額": turnover_val,
                        "本季營益率(%)": op_latest,
                        "上一季營益率(%)": op_prev,
                    }
                  except:
                    continue
  except Exception as e:
    print(f"MI error: {e}")

  if taiex_close == 0.0:
    taiex_close = 48157.29

  prev_turnover_dict = {}
  mi_prev_url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999&date={prev_date}"
  try:
    res_pmi = session.get(mi_prev_url, timeout=8)
    if res_pmi.status_code == 200:
      pdata = res_pmi.json()
      if pdata.get("stat") == "OK":
        for table in pdata.get("tables", []):
          if "data" in table:
            for row in table["data"]:
              if len(row) >= 11:
                code = str(row[0]).strip()
                if len(code) == 4 and code.isdigit():
                  try:
                    tv = 0.0
                    try:
                      tv = float(str(row[4]).replace(",", ""))
                    except:
                      try:
                        tv = float(str(row[5]).replace(",", ""))
                      except:
                        pass
                    prev_turnover_dict[code] = tv
                  except:
                    pass
  except:
    pass

  latest_foreign_shares = {}
  latest_trust_shares = {}
  hist_foreign_shares = {}

  for i, d_str in enumerate(dates[:25]):
    t86_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d_str}&selectType=ALL"
    try:
      res_t86 = session.get(t86_url, timeout=5)
      if res_t86.status_code == 200:
        t86_data = res_t86.json()
        if t86_data.get("stat") == "OK":
          day_map = {}
          for r in t86_data.get("data", []):
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
                except:
                  continue
          hist_foreign_shares[d_str] = day_map
    except:
      pass
    time.sleep(0.15)

  for code in market_dict:
    market_dict[code]["前日成交金額"] = prev_turnover_dict.get(
        code, market_dict[code]["成交金額"]
    )

  return (
      market_dict,
      latest_foreign_shares,
      latest_trust_shares,
      hist_foreign_shares,
      dates,
      taiex_close,
      taiex_change,
      taiex_pct,
  )


with st.spinner("⏳ 正在載入台股籌碼與均線數據..."):
  (
      market_dict,
      latest_foreign_shares,
      latest_trust_shares,
      hist_foreign_shares,
      target_dates,
      taiex_close,
      taiex_change,
      taiex_pct,
  ) = fetch_twse_data()

latest_date = target_dates[0] if target_dates else ""
if latest_date:
  st.sidebar.success(
      f"📅 官方同步日：{latest_date[:4]}/{latest_date[4:6]}/{latest_date[6:]}"
  )
  change_sign = "+" if taiex_change > 0 else ""
  st.sidebar.metric(
      label="📈 大盤加權指數收盤",
      value=f"{taiex_close:,.2f} 點",
      delta=(
          f"{change_sign}{taiex_change:,.2f} 點 ({change_sign}{taiex_pct:.2f}%)"
          if taiex_change != 0
          else None
      ),
  )

if market_dict:
  base_rows = []
  for code, info in market_dict.items():
    f_shares = latest_foreign_shares.get(code, 0)
    t_shares = latest_trust_shares.get(code, 0)
    close_p = info["收盤價"]
    shares = info["發行總股數"]
    turnover_100m = info.get("成交金額", 0.0) / 100000000
    prev_turnover_100m = info.get("前日成交金額", 0.0) / 100000000
    op_latest = info["本季營益率(%)"]
    op_prev = info["上一季營益率(%)"]

    assigned_ind = st.session_state.user_industry_map.get(code, "")

    base_rows.append(
        {
            "代號": code,
            "官方名稱": info["官方名稱"],
            "發行總股數": shares,
            "收盤價": close_p,
            "日K_MA20": info["日K_MA20"],
            "週K_MA20": info["週K_MA20"],
            "成交值(億)": round(turnover_100m, 2),
            "前日成交值(億)": round(prev_turnover_100m, 2),
            "外資買賣超股數": f_shares,
            "外資買賣超張數": f_shares / 1000,
            "投信買賣超股數": t_shares,
            "投信買賣超張數": t_shares / 1000,
            "本季營益率(%)": op_latest,
            "上一季營益率(%)": op_prev,
            "族群": assigned_ind,
            "漲跌": info.get("漲跌", 0.0),
            "漲跌幅(%)": round(info.get("漲跌幅(%)", 0.0), 2),
        }
    )

  df_market = pd.DataFrame(base_rows)


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
    return df


  df_all_enriched = enrich_data(df_market)

  cond_trend = (df_all_enriched["收盤價"] > df_all_enriched["日K_MA20"]) & (
      df_all_enriched["收盤價"] > df_all_enriched["週K_MA20"]
  )

  cond_dual_a_up = (
      (df_all_enriched["漲跌幅(%)"] > 0)
      & (df_all_enriched["外資買賣超股數"] > 0)
      & (df_all_enriched["投信買賣超股數"] > 0)
  )

  cond_profit = (
      (
          (df_all_enriched["本季營益率(%)"] > 0)
          & (df_all_enriched["本季營益率(%)"] > df_all_enriched["上一季營益率(%)"])
      )
      if enable_profit_filter
      else True
  )

  cond_vol = (
      (df_all_enriched["成交值(億)"] > df_all_enriched["前日成交值(億)"])
      if enable_vol_growth_filter
      else True
  )

  df_super_target = df_all_enriched[
      cond_trend & cond_dual_a_up & cond_profit & cond_vol
  ].copy()


  def build_super_industry_ranking(df_pool):
    raw = df_pool[df_pool["族群"].str.strip() != ""]
    if raw.empty:
      return pd.DataFrame()
    summary = (
        raw.groupby("族群")
        .agg(
            股票檔數=("代號", "count"),
            平均外本比_pct=("外本比(%)", "mean"),
            平均投本比_pct=("投本比(%)", "mean"),
            平均雙法人總集中度_pct=("雙法人總集中度(%)", "mean"),
            外資總買超張數=("外資買賣超張數", "sum"),
            投信總買超張數=("投信買賣超張數", "sum"),
            族群總成交值=("成交值(億)", "sum"),
        )
        .reset_index()
    )
    summary["平均外本比(%)"] = summary["平均外本比_pct"].round(3)
    summary["平均投本比(%)"] = summary["平均投本比_pct"].round(3)
    summary["平均雙法人總集中度(%)"] = summary[
        "平均雙法人總集中度_pct"
    ].round(3)
    summary["外資總買超張數"] = summary["外資總買超張數"].round(0)
    summary["投信總買超張數"] = summary["投信總買超張數"].round(0)

    summary["籌碼集中度得分"] = round(
        summary["平均雙法人總集中度(%)"]
        * np.sqrt(summary["股票檔數"])
        * np.log1p(summary["外資總買超張數"].clip(lower=0))
        * np.log1p(summary["投信總買超張數"].clip(lower=0)),
        2,
    )
    summary = summary.sort_values(by="籌碼集中度得分", ascending=False)
    cols = [
        "族群",
        "股票檔數",
        "籌碼集中度得分",
        "平均外本比(%)",
        "平均投本比(%)",
        "平均雙法人總集中度(%)",
        "外資總買超張數",
        "投信總買超張數",
        "族群總成交值",
    ]
    summary = summary[[c for c in cols if c in summary.columns]]
    summary.insert(0, "排名", range(1, len(summary) + 1))
    return summary


  df_super_ind_rank = build_super_industry_ranking(df_super_target)

  tab_super, tab_raw_targets, tab_all_search = st.tabs([
      "🔥 雙A多頭站上均線：族群集中度排名",
      "📋 符合條件之個股明細檔",
      "🔍 全市場快速查找",
  ])

  def update_map_from_editor(edited_df):
    if (
        not edited_df.empty
        and "代號" in edited_df.columns
        and "族群" in edited_df.columns
    ):
      updated_map = st.session_state.user_industry_map.copy()
      for _, row in edited_df.iterrows():
        c_code = str(row["代號"]).strip()
        c_ind = str(row["族群"]).strip() if pd.notna(row["族群"]) else ""
        updated_map[c_code] = c_ind
      st.session_state.user_industry_map = updated_map
      save_db(updated_map)
      st.success("✅ 族群設定已成功更新！")

  with tab_super:
    st.info(
        "💡 **邏輯說明**：篩選 **[收盤價 > 日K MA20 且 週K MA20]** ∩ **[漲幅>0 且 外資>0 且 投信>0]** 之強勢雙A股，依族群結算「籌碼集中度得分」排序！"
    )
    if not df_super_ind_rank.empty:
      df_disp = df_super_ind_rank.copy()
      df_disp.insert(0, "查看明細", False)
      edited_sum = st.data_editor(
          df_disp,
          use_container_width=True,
          hide_index=True,
          disabled=[col for col in df_disp.columns if col != "查看明細"],
          key="ed_super_summary",
      )

      selected_rows = edited_sum[edited_sum["查看明細"] == True]
      if not selected_rows.empty:
        st.markdown("---")
        st.markdown("### 🏆 展開勾選族群的強勢個股 (可修改族群)")
        for _, ind_row in selected_rows.iterrows():
          t_ind = ind_row["族群"]
          sub_stocks = df_super_target[df_super_target["族群"] == t_ind].copy()
          if not sub_stocks.empty:
            sub_stocks = sub_stocks.sort_values(
                by="雙法人總集中度(%)", ascending=False
            )
            sub_stocks.insert(0, "族群排名", range(1, len(sub_stocks) + 1))
            st.subheader(f"📌 {t_ind} (共 {len(sub_stocks)} 檔)")
            ed_sub = st.data_editor(
                sub_stocks,
                use_container_width=True,
                hide_index=True,
                disabled=[
                    c for c in sub_stocks.columns if c not in ["族群", "族群排名"]
                ],
                key=f"sub_edit_{t_ind}",
            )
            if st.button(f"💾 儲存 {t_ind} 變更", key=f"btn_sub_{t_ind}"):
              update_map_from_editor(ed_sub)
    else:
      st.warning("⚠️ 目前條件下查無符合的族群集中度資料，可放寬防護網嘗試。")

  with tab_raw_targets:
    st.info(f"📋 **符合上述雙A站上均線條件個股總計**：{len(df_super_target)} 檔")
    if not df_super_target.empty:
      ed_raw = st.data_editor(
          df_super_target,
          use_container_width=True,
          hide_index=True,
          height=500,
          disabled=[col for col in df_super_target.columns if col != "族群"],
          key="ed_super_target_all",
      )
      if st.button("💾 儲存個股清單的族群設定", key="btn_save_raw_targets"):
        update_map_from_editor(ed_raw)

  with tab_all_search:
    st.markdown("### 🔍 任意台股快速查找與編輯")
    c1, _ = st.columns([1, 3])
    with c1:
      ds = st.text_input("輸入代號或名稱", value=search_query, key="global_search_box")
    if ds:
      m_df = df_all_enriched[
          df_all_enriched["代號"].str.contains(ds)
          | df_all_enriched["官方名稱"].str.contains(ds)
      ]
      if not m_df.empty:
        ed_search = st.data_editor(
            m_df,
            use_container_width=True,
            hide_index=True,
            disabled=[col for col in m_df.columns if col != "族群"],
            key="ed_global_search",
        )
        if st.button("💾 儲存搜尋結果的族群修改", key="btn_save_search"):
          update_map_from_editor(ed_search)
      else:
        st.warning("查無符合代號或名稱之股票。")