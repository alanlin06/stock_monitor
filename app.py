from datetime import datetime, timedelta
import json
import os
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="台股成交值百大新面孔與常客族群雷達",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🎯 台股成交值百大：漲勢新面孔與常客族群雷達（含雙法人集中度）")

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

search_query = st.sidebar.text_input(
    "🔍 側邊欄快速查找台股", placeholder="輸入代號或名稱 (例: 2330)"
)


@st.cache_data(ttl=600)
def fetch_top100_data():
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

  curr = datetime.now()
  dates = []
  for i in range(15):
    d_str = curr.strftime("%Y%m%d")
    test_url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999&date={d_str}"
    try:
      res = session.get(test_url, timeout=5)
      if res.status_code == 200:
        data = res.json()
        if data.get("stat") == "OK" and len(data.get("tables", [])) > 0:
          dates.append(d_str)
          if len(dates) >= 2:
            break
    except:
      pass
    curr -= timedelta(days=1)
    time.sleep(0.12)

  if len(dates) == 0:
    return {}, {}, {}, [], 48157.29, 0.0, 0.0

  latest_date = dates[0]
  prev_date = dates[1] if len(dates) > 1 else latest_date

  def get_t86_map(d_str):
    t_map = {}
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d_str}&selectType=ALLBUT0999"
    try:
      r = session.get(url, timeout=6)
      if r.status_code == 200:
        d = r.json()
        if d.get("stat") == "OK" and "data" in d:
          for row in d["data"]:
            if len(row) > 10:
              code = str(row[0]).strip()
              if len(code) == 4 and code.isdigit():
                try:
                  f_val = float(str(row[4]).replace(",", ""))
                  t_val = float(str(row[10]).replace(",", ""))
                  t_map[code] = {
                      "外資淨買超": f_val,
                      "投信淨買超": t_val,
                      "雙法人淨買超": f_val + t_val,
                  }
                except:
                  pass
    except:
      pass
    time.sleep(0.12)
    return t_map

  latest_inst = get_t86_map(latest_date)

  def get_day_market(d_str):
    m_dict = {}
    idx_close, idx_chg, idx_pct = 48157.29, 0.0, 0.0
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999&date={d_str}"
    try:
      res = session.get(url, timeout=8)
      if res.status_code == 200:
        data = res.json()
        if data.get("stat") == "OK":
          for table in data.get("tables", []):
            for row in table.get("data", []):
              row_str = "".join([str(c) for c in row])
              if "加權指數" in row_str and idx_close == 48157.29:
                for c in row:
                  cs = str(c).replace(",", "").strip()
                  try:
                    v = float(cs)
                    if v > 3000:
                      idx_close = v
                      break
                  except:
                    pass

          for table in data.get("tables", []):
            if "data" in table:
              for row in table["data"]:
                if len(row) >= 11:
                  code = str(row[0]).strip()
                  if len(code) == 4 and code.isdigit():
                    try:
                      name = str(row[1]).strip()
                      tv = 0.0
                      try:
                        tv = float(str(row[4]).replace(",", ""))
                      except:
                        try:
                          tv = float(str(row[5]).replace(",", ""))
                        except:
                          pass
                      close_raw = str(row[8]).replace(",", "").strip()
                      if close_raw in ["--", "-", ""]:
                        continue
                      close_p = float(close_raw)
                      sign = (
                          -1.0
                          if ("-" in str(row[9]) or "跌" in str(row[9]))
                          else 1.0
                      )
                      chg_raw = str(row[10]).replace(",", "").strip()
                      chg_val = (
                          (float(chg_raw) * sign)
                          if chg_raw not in ["--", "-", ""]
                          else 0.0
                      )
                      prev_p = close_p - chg_val
                      pct_val = (
                          (chg_val / prev_p) * 100 if prev_p > 0 else 0.0
                      )
                      m_dict[code] = {
                          "官方名稱": name,
                          "收盤價": close_p,
                          "漲跌幅(%)": round(pct_val, 2),
                          "成交金額": tv,
                      }
                    except:
                      continue
    except:
      pass
    return m_dict, idx_close, idx_chg, idx_pct

  today_dict, taiex_close, taiex_change, taiex_pct = get_day_market(latest_date)
  prev_dict, _, _, _ = get_day_market(prev_date)

  return (
      today_dict,
      prev_dict,
      latest_inst,
      dates,
      taiex_close,
      taiex_change,
      taiex_pct,
  )


with st.spinner("⏳ 正在取得今日與前日成交值百大與法人籌碼對應..."):
  (
      today_dict,
      prev_dict,
      latest_inst,
      target_dates,
      taiex_close,
      taiex_change,
      taiex_pct,
  ) = fetch_top100_data()

latest_date = target_dates[0] if target_dates else ""
prev_date = target_dates[1] if len(target_dates) > 1 else ""

if latest_date:
  st.sidebar.success(f"📅 官方同步日：{latest_date} (對比 {prev_date})")


def get_top_n_codes(m_dict, n=100):
  s = sorted(
      [(k, v["成交金額"]) for k, v in m_dict.items() if v["成交金額"] > 0],
      key=lambda x: x[1],
      reverse=True,
  )
  return set([item[0] for item in s[:n]])


today_top100 = get_top_n_codes(today_dict, 100)
prev_top100 = get_top_n_codes(prev_dict, 100)

newcomer_codes_up = [
    c
    for c in today_top100
    if c not in prev_top100 and today_dict[c]["漲跌幅(%)"] > 0
]

recurring_codes_up = [
    c
    for c in today_top100
    if c in prev_top100 and today_dict[c]["漲跌幅(%)"] > 0
]


def build_group_stats_with_inst(codes_list):
  rows = []
  for c in codes_list:
    if c in today_dict:
      info = today_dict[c]
      ind = st.session_state.user_industry_map.get(c, "未分類")
      turnover_amt = info["成交金額"]
      inst_info = latest_inst.get(
          c, {"外資淨買超": 0.0, "投信淨買超": 0.0, "雙法人淨買超": 0.0}
      )
      double_inst_amt = inst_info["雙法人淨買超"]
      conc_pct = (
          (double_inst_amt / turnover_amt) * 100 if turnover_amt > 0 else 0.0
      )

      rows.append({
          "代號": c,
          "官方名稱": info["官方名稱"],
          "收盤價": info["收盤價"],
          "漲跌幅(%)": info["漲跌幅(%)"],
          "成交值(億)": round(turnover_amt / 100000000, 2),
          "外資買超(億)": round(inst_info["外資淨買超"] / 100000000, 3),
          "投信買超(億)": round(inst_info["投信淨買超"] / 100000000, 3),
          "雙法人買超占比(%)": round(conc_pct, 2),
          "族群": ind,
      })
  df = pd.DataFrame(rows)
  if df.empty:
    return pd.DataFrame(), pd.DataFrame()

  total_count = len(df)
  group_summary = (
      df.groupby("族群")
      .agg(
          個股數=("代號", "count"),
          總成交值億=("成交值(億)", "sum"),
          平均雙法人集中度=("雙法人買超占比(%)", "mean"),
      )
      .reset_index()
  )
  group_summary["占比(%)"] = round(
      (group_summary["個股數"] / total_count) * 100, 2
  )
  group_summary["平均雙法人集中度"] = round(group_summary["平均雙法人集中度"], 2)
  group_summary = group_summary.sort_values(by="個股數", ascending=False)
  return df, group_summary


df_new_up, grp_new_up = build_group_stats_with_inst(newcomer_codes_up)
df_rec_up, grp_rec_up = build_group_stats_with_inst(recurring_codes_up)


def update_map_from_editor(edited_df):
  if not edited_df.empty and "代號" in edited_df.columns and "族群" in edited_df.columns:
    updated_map = st.session_state.user_industry_map.copy()
    for _, row in edited_df.iterrows():
      c_code = str(row["代號"]).strip()
      c_ind = str(row["族群"]).strip() if pd.notna(row["族群"]) else ""
      updated_map[c_code] = c_ind
    st.session_state.user_industry_map = updated_map
    save_db(updated_map)
    st.success("✅ 族群設定已成功更新！")


tab1, tab2, tab3 = st.tabs([
    "🚀 百大新面孔（上漲）與族群占比 / 雙法人集中度",
    "📌 百大常駐重複（上漲）族群分佈 / 雙法人集中度",
    "🔍 全市場快速查找與歸類",
])

with tab1:
  st.subheader("🔥 成交值百大「今日突然擠進來且上漲」的新面孔與籌碼集中度")
  if not grp_new_up.empty:
    c1, c2 = st.columns([1, 1.2])
    with c1:
      st.markdown("### 📊 新面孔族群占比與平均集中度")
      st.dataframe(grp_new_up, use_container_width=True, hide_index=True)
    with c2:
      st.markdown(f"### 📋 符合的強勢新面孔明細 ({len(df_new_up)}檔)")
      ed_new = st.data_editor(
          df_new_up,
          use_container_width=True,
          hide_index=True,
          disabled=[
              c for c in df_new_up.columns if c not in ["族群"]
          ],
          key="ed_new_up",
      )
      if st.button("💾 儲存新面孔族群修改", key="btn_save_new"):
        update_map_from_editor(ed_new)
  else:
    st.info("今日無符合「擠入百大且收紅」的新面孔。")

with tab2:
  st.subheader("🔁 成交值百大「重複常客且今天上漲」之族群分佈與集中度")
  if not grp_rec_up.empty:
    c1, c2 = st.columns([1, 1.2])
    with c1:
      st.markdown("### 📊 常客上漲族群占比與平均集中度")
      st.dataframe(grp_rec_up, use_container_width=True, hide_index=True)
    with c2:
      st.markdown(f"### 📋 常駐上漲個股明細 ({len(df_rec_up)}檔)")
      ed_rec = st.data_editor(
          df_rec_up,
          use_container_width=True,
          hide_index=True,
          disabled=[
              c for c in df_rec_up.columns if c not in ["族群"]
          ],
          key="ed_rec_up",
      )
      if st.button("💾 儲存常客族群修改", key="btn_save_rec"):
        update_map_from_editor(ed_rec)
  else:
    st.info("目前無符合條件的常客上漲標的。")

with tab3:
  st.subheader("🔍 全市場代號/名稱快速檢索與族群標註")
  all_rows = []
  for code, info in today_dict.items():
    inst_info = latest_inst.get(
        code, {"外資淨買超": 0.0, "投信淨買超": 0.0, "雙法人淨買超": 0.0}
    )
    all_rows.append({
        "代號": code,
        "官方名稱": info["官方名稱"],
        "收盤價": info["收盤價"],
        "漲跌幅(%)": info["漲跌幅(%)"],
        "成交值(億)": round(info["成交金額"] / 100000000, 2),
        "外資買超(億)": round(inst_info["外資淨買超"] / 100000000, 3),
        "投信買超(億)": round(inst_info["投信淨買超"] / 100000000, 3),
        "族群": st.session_state.user_industry_map.get(code, ""),
    })
  df_all = pd.DataFrame(all_rows)
  if search_query:
    df_all = df_all[
        df_all["代號"].str.contains(search_query)
        | df_all["官方名稱"].str.contains(search_query)
    ]
  ed_all = st.data_editor(
      df_all,
      use_container_width=True,
      hide_index=True,
      disabled=[c for c in df_all.columns if c != "族群"],
      key="ed_all_search",
  )
  if st.button("💾 儲存全市場族群修改", key="btn_save_all"):
    update_map_from_editor(ed_all)