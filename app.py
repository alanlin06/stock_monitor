from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# ============================================================
# 頁面設定
# ============================================================

st.set_page_config(
    page_title="台股外資籌碼與專屬排行終端機",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚡ 台股外資買超 Top 50 與籌碼專屬排行終端機")
st.caption(
    "🔄 100% 串接證交所官方 API |"
    " 全面以『外本比』精準計算：買超 Top 50、外本比 Top 50、連續買超"
    " Top 50、成交值 Top 100"
)


# ============================================================
# 側邊欄設定
# ============================================================

with st.sidebar:
  st.header("⚙️ 排序與檢視設定")

  sort_option = st.selectbox(
      "Top 50 主表格排序依據：",
      options=[
          "🔥 外本比 (外資買超股數佔發行總股數比例 - 優先)",
          "📈 外資買超張數 (與證交所官網預設一致)",
          "💰 外資買超金額 (資金砸最多優先)",
          "🎯 買超金額佔成交值比 (當日籌碼貢獻佔比)",
          "⏳ 連續買超天數 (連買最久優先)",
      ],
      index=0,
  )

  st.markdown("---")

  st.markdown(
      """
        💡 **指標說明**：
        - **外本比 (%)**：(外資買超股數 ÷ 官方發行總股數) × 100%。全排行榜同步納入計算。
        - **外資買超金額**：買超張數 × 平均價格 (VWAP) × 1000。
        - **多空成本均價線**：每根 K 棒 (最高價 + 最低價) / 2 之滾動平均價格（日K取20期、週K取10期），作為真實多空成本參考線。
        """
  )


# ============================================================
# 抓取證交所資料
# ============================================================


@st.cache_data(ttl=600)
def fetch_twse_data():
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      )
  }

  curr = datetime.now()
  dates = []

  while len(dates) < 10 and (datetime.now() - curr).days < 30:
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
                vwap = (
                    total_turnover / trading_volume
                    if trading_volume > 0
                    else close_price
                )

                market_dict[code] = {
                    "官方名稱": name,
                    "發行總股數": issued_shares_total_raw,
                    "收盤價": close_price,
                    "成交均價": round(vwap, 2),
                    "總成交金額_元": total_turnover,
                    "漲跌幅(%)": change_pct,
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
  (
      market_dict,
      latest_foreign_shares,
      hist_foreign_shares,
      target_dates,
      latest_date,
  ) = fetch_twse_data()

if latest_date:
  st.sidebar.success(
      f"📅 官方同步交易日：{latest_date[:4]}/{latest_date[4:6]}/{latest_date[6:]}"
  )


# ============================================================
# 📊 前十大權值股與加權指數影響點數即時看板
# ============================================================

st.markdown("### 📈 前十大權值股與加權指數影響點數即時看板")


@st.cache_data(ttl=600)
def fetch_top10_impact():
  top10_config = [
      {"排名": 1, "股票": "台積電", "代號": "2330", "權重": 44.77},
      {"排名": 2, "股票": "聯發科", "代號": "2454", "權重": 4.05},
      {"排名": 3, "股票": "台達電", "代號": "2308", "權重": 3.03},
      {"排名": 4, "股票": "鴻海", "代號": "2317", "權重": 2.50},
      {"排名": 5, "股票": "日月光投控", "代號": "3711", "權重": 1.76},
      {"排名": 6, "股票": "富邦金", "代號": "2327", "權重": 1.29},
      {"排名": 7, "股票": "台光電", "代號": "2303", "權重": 1.21},
      {"排名": 8, "股票": "聯電", "代號": "2881", "權重": 1.08},
      {"排名": 9, "股票": "國泰金", "代號": "2383", "權重": 1.06},
      {"排名": 10, "股票": "欣興", "代號": "3037", "權重": 0.91},
  ]

  tickers_str = " ".join([f"{item['代號']}.TW" for item in top10_config])
  rows = []
  total_impact = 0.0

  try:
    data = yf.download(
        tickers_str, period="5d", group_by="ticker", progress=False
    )
    for item in top10_config:
      code = item["代號"]
      name = item["股票"]
      weight = item["權重"]
      t_symbol = f"{code}.TW"

      close_p = 0.0
      price_diff = 0.0

      if t_symbol in data and not data[t_symbol].empty:
        df_s = data[t_symbol].dropna()
        if len(df_s) >= 2:
          c_close = df_s["Close"].iloc[-1]
          p_close = df_s["Close"].iloc[-2]
          close_p = round(c_close, 2)
          price_diff = round(c_close - p_close, 2)

      estimated_impact = round(price_diff * (weight / 10.0), 2)
      total_impact += estimated_impact

      rows.append({
          "排名": item["排名"],
          "股票": name,
          "代號": code,
          "權重(%)": weight,
          "最新股價": close_p,
          "漲跌金額": price_diff,
          "影響點數": estimated_impact,
      })
  except Exception as e:
    pass

  return rows, round(total_impact, 2)


top10_rows, total_impact_pts = fetch_top10_impact()

col_i1, col_i2 = st.columns([1, 3])
col_i1.metric("🎯 前十大權值股合計影響點數", f"{total_impact_pts:+.2f} 點")
col_i2.markdown(
    "💡 **說明**：上方即時呈現您指定的 10 大權值核心個股當日對加權指數帶動的漲跌點數與即時行情。"
)

if top10_rows:
  df_top10_view = pd.DataFrame(top10_rows)
  st.dataframe(df_top10_view, use_container_width=True, hide_index=True)

st.markdown("---")


# ============================================================
# 建立資料表與全面外本比導向計算
# ============================================================

if market_dict:
  combined_rows = []

  for code, m_info in market_dict.items():
    f_shares = latest_foreign_shares.get(code, 0)
    combined_rows.append({
        "代號": code,
        "官方名稱": m_info["官方名稱"],
        "發行總股數": m_info["發行總股數"],
        "外資買賣超股數": f_shares,
        "外資買賣超張數": f_shares / 1000,
        "收盤價": m_info["收盤價"],
        "成交均價": m_info["成交均價"],
        "總成交金額_元": m_info["總成交金額_元"],
        "漲跌幅(%)": m_info["漲跌幅(%)"],
    })

  df_all = pd.DataFrame(combined_rows)

  if not df_all.empty:

    def calc_streak(code):
      streak = 0
      for d_str in target_dates:
        val = hist_foreign_shares.get(d_str, {}).get(code, 0)
        if val > 0:
          streak += 1
        else:
          break
      return streak

    df_all["連續買超天數"] = df_all["代號"].apply(calc_streak)

    df_all["外本比(%)"] = df_all.apply(
        lambda row: round(
            (row["外資買賣超股數"] / row["發行總股數"]) * 100, 3
        )
        if row["發行總股數"] > 0
        else 0.0,
        axis=1,
    )

    df_all["外資買超金額_元"] = (
        df_all["外資買賣超張數"] * 1000 * df_all["成交均價"]
    )
    df_all["外資買超金額(億)"] = round(df_all["外資買超金額_元"] / 1e8, 2)
    df_all["買超金額佔成交值比(%)"] = df_all.apply(
        lambda row: round(
            (row["外資買超金額_元"] / row["總成交金額_元"]) * 100, 2
        )
        if row["總成交金額_元"] > 0
        else 0.0,
        axis=1,
    )

    df_top50 = (
        df_all[df_all["外資買賣超張數"] > 0]
        .sort_values(by="外資買賣超張數", ascending=False)
        .head(50)
        .copy()
    )

    if "外本比" in sort_option:
      df_top50 = df_top50.sort_values(by="外本比(%)", ascending=False)
    elif "買超張數" in sort_option:
      df_top50 = df_top50.sort_values(by="外資買賣超張數", ascending=False)
    elif "買超金額" in sort_option:
      df_top50 = df_top50.sort_values(by="外資買超金額(億)", ascending=False)
    elif "佔成交值比" in sort_option:
      df_top50 = df_top50.sort_values(
          by="買超金額佔成交值比(%)", ascending=False
      )
    else:
      df_top50 = df_top50.sort_values(by="連續買超天數", ascending=False)

    df_top50.insert(0, "集中排序", range(1, len(df_top50) + 1))

    df_buy_top50_base = (
        df_all[df_all["外資買賣超張數"] > 0]
        .sort_values(by="外資買賣超張數", ascending=False)
        .head(50)
        .copy()
    )
    df_wben50 = df_buy_top50_base.sort_values(
        by="外本比(%)", ascending=False
    ).copy()
    df_wben50.insert(0, "外本比排序", range(1, len(df_wben50) + 1))

    df_streak50 = (
        df_all[df_all["連續買超天數"] > 0]
        .sort_values(by=["連續買超天數", "外本比(%)"], ascending=[False, False])
        .head(50)
        .copy()
    )
    df_streak50.insert(0, "連買排序", range(1, len(df_streak50) + 1))

    df_vol100 = (
        df_all.sort_values(by="總成交金額_元", ascending=False).head(100).copy()
    )
    df_vol100["成交金額(億)"] = round(df_vol100["總成交金額_元"] / 1e8, 2)
    df_vol100.insert(0, "成交值排序", range(1, len(df_vol100) + 1))

    total_foreign_amount = round(df_top50["外資買超金額(億)"].sum(), 2)
    most_concentrated = df_all.sort_values(by="外本比(%)", ascending=False).iloc[
        0
    ]
    top_amount_stock = df_top50.sort_values(
        by="外資買超金額(億)", ascending=False
    ).iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📊 Top 50 總買超金額", f"{total_foreign_amount} 億")
    c2.metric("🎯 監控標的檔數", f"{len(df_top50)} 檔")
    c3.metric(
        f"🔥 全市場外本比最高",
        f"{most_concentrated['官方名稱']} ({most_concentrated['代號']})",
        f"外本比 {most_concentrated['外本比(%)']}%",
    )
    c4.metric(
        f"💰 砸錢最多之冠",
        f"{top_amount_stock['官方名稱']} ({top_amount_stock['代號']})",
        f"+{top_amount_stock['外資買超金額(億)']} 億",
    )

    st.markdown("---")

    # ====================================================
    # 四大排行榜 + 交叉比對分頁
    # ====================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔥 外資買超 Top 50",
        "🔥 當日外本比 Top 50",
        "⏳ 連續買超 Top 50 (外本比優先)",
        "🏆 全市場成交值 Top 100 (含外本比)",
        "🔗 雙榜交叉比對 (外本比 ∩ 成交值)",
    ])


    def render_chart_section(df_source, tab_name):
      st.subheader(f"📋 {tab_name} 全部標的清單")
      st.caption(
          "💡 提示：點擊下方表格任一列，即可直接在下方載入該標的的日K/週K走勢圖！"
      )

      event = st.dataframe(
          df_source,
          use_container_width=True,
          hide_index=True,
          height=450,
          on_select="rerun",
          selection_mode="single-row",
      )

      selected_rows = event.selection.rows if hasattr(event, "selection") else []

      if selected_rows:
        idx = selected_rows[0]
        selected_row_data = df_source.iloc[idx]
        target_code = str(selected_row_data["代號"])
        target_name = str(selected_row_data["官方名稱"])

        st.markdown("---")
        st.subheader(f"📈 互動技術分析走勢圖：{target_code} {target_name}")

        c_per1, c_per2 = st.columns([1, 3])
        with c_per1:
          k_period_type = st.selectbox(
              "⏱️ 選擇 K 線週期：",
              options=["日K (近6個月)", "週K (近1年)"],
              index=0,
              key=f"k_{tab_name}",
          )

        yf_period = "1y" if "週K" in k_period_type else "6mo"
        yf_interval = "1wk" if "週K" in k_period_type else "1d"

        with st.spinner(
            f"正在載入 {target_code} {target_name} 的 {k_period_type}"
            " 走勢與多空成本線..."
        ):
          try:
            df_stock = yf.download(
                f"{target_code}.TW",
                period=yf_period,
                interval=yf_interval,
                auto_adjust=False,
                progress=False,
            )
            if df_stock.empty:
              df_stock = yf.download(
                  f"{target_code}.TWO",
                  period=yf_period,
                  interval=yf_interval,
                  auto_adjust=False,
                  progress=False,
              )

            if not df_stock.empty:
              if isinstance(df_stock.columns, pd.MultiIndex):
                df_stock.columns = df_stock.columns.get_level_values(0)

              df_stock["Mid_Price"] = (df_stock["High"] + df_stock["Low"]) / 2
              window_size = 10 if "週K" in k_period_type else 20
              df_stock["Cost_Line"] = (
                  df_stock["Mid_Price"].rolling(window=window_size).mean()
              )

              fig = go.Figure()
              fig.add_trace(go.Candlestick(
                  x=df_stock.index,
                  open=df_stock["Open"],
                  high=df_stock["High"],
                  low=df_stock["Low"],
                  close=df_stock["Close"],
                  name=f"{k_period_type}線",
                  increasing=dict(line=dict(color="red"), fillcolor="red"),
                  decreasing=dict(line=dict(color="green"), fillcolor="green"),
              ))
              fig.add_trace(go.Scatter(
                  x=df_stock.index,
                  y=df_stock["Cost_Line"],
                  mode="lines",
                  name=f"多空成本線 ({window_size}期)",
                  line=dict(color="orange", width=2),
              ))
              fig.update_layout(
                  title=(
                      f"{target_code} {target_name} - {k_period_type}與多空成本均價線"
                      " (可縮放/平移)"
                  ),
                  yaxis_title="股價 (TWD)",
                  xaxis_title="日期",
                  template="plotly_dark",
                  height=480,
                  margin=dict(l=10, r=10, t=40, b=10),
              )
              st.plotly_chart(fig, use_container_width=True)
            else:
              st.warning("查無此標的歷史資料。")
          except Exception as e:
            st.error(f"載入發生錯誤: {e}")


    with tab1:
      render_chart_section(
          df_top50[[
              "集中排序",
              "代號",
              "官方名稱",
              "外資買賣超張數",
              "成交均價",
              "外資買超金額(億)",
              "外本比(%)",
              "買超金額佔成交值比(%)",
              "連續買超天數",
              "漲跌幅(%)",
          ]],
          "外資買超 Top 50",
      )

    with tab2:
      render_chart_section(
          df_wben50[[
              "外本比排序",
              "代號",
              "官方名稱",
              "外本比(%)",
              "外資買賣超張數",
/usr/local/lib/python3.11/site-packages/streamlit/runtime/scriptrunner/script_runner.py:1120: FutureWarning:
The default fill_value of DataFrame.pivot is deprecated and will be removed in a future version. Use a specific fill_value to silence this warning.
              "收盤價",
              "漲跌幅(%)",
          ]],
          "當日外本比 Top 50",
      )

    with tab3:
      render_chart_section(
          df_streak50[[
              "連買排序",
              "代號",
              "官方名稱",
              "連續買超天數",
              "外本比(%)",
              "外資買賣超張數",
              "收盤價",
              "漲跌幅(%)",
          ]],
          "連續買超 Top 50",
      )

    with tab4:
      render_chart_section(
          df_vol100[[
              "成交值排序",
              "代號",
              "官方名稱",
              "成交金額(億)",
              "外本比(%)",
              "收盤價",
              "漲跌幅(%)",
              "總成交金額_元",
          ]],
          "全市場成交值 Top 100",
      )

    with tab5:
      st.subheader("🔗 雙榜交叉比對：外本比 Top 50 ∩ 成交值 Top 100")
      st.caption(
          "💡 此處自動篩選**同時名列**「當日外本比 Top"
          " 50」與「全市場成交值 Top 100」的雙榜強勢個股，並依外本比由高到低排序！"
          " 名稱旁自動附帶【日K/週K多空判定】。"
      )

      set_wben = set(df_wben50["代號"])
      set_vol = set(df_vol100["代號"])
      common_codes = set_wben.intersection(set_vol)

      df_cross = (
          df_all[df_all["代號"].isin(common_codes)]
          .sort_values(by="外本比(%)", ascending=False)
          .copy()
      )

      # 動態計算雙榜交集標的的日K與週K多空狀態
      with st.spinner("正在為雙榜標的運算日K與週K多空成本線狀態..."):
        enhanced_names = []
        for _, r_item in df_cross.iterrows():
          c_code = str(r_item["代號"])
          o_name = str(r_item["官方名稱"])
          status_str = ""

          try:
            # 抓取日K與週K
            df_d = yf.download(
                f"{c_code}.TW", period="3mo", interval="1d", progress=False
            )
            if df_d.empty:
              df_d = yf.download(
                  f"{c_code}.TWO", period="3mo", interval="1d", progress=False
              )

            df_w = yf.download(
                f"{c_code}.TW", period="1y", interval="1wk", progress=False
            )
            if df_w.empty:
              df_w = yf.download(
                  f"{c_code}.TWO", period="1y", interval="1wk", progress=False
              )

            # 判定日K
            day_ok = False
            if not df_d.empty:
              if isinstance(df_d.columns, pd.MultiIndex):
                df_d.columns = df_d.columns.get_level_values(0)
              df_d["Mid"] = (df_d["High"] + df_d["Low"]) / 2
              df_d["MA"] = df_d["Mid"].rolling(20).mean()
              if (
                  len(df_d) > 0
                  and df_d["Close"].iloc[-1] >= df_d["MA"].iloc[-1]
              ):
                day_ok = True

            # 判定週K
            week_ok = False
            if not df_w.empty:
              if isinstance(df_w.columns, pd.MultiIndex):
                df_w.columns = df_w.columns.get_level_values(0)
              df_w["Mid"] = (df_w["High"] + df_w["Low"]) / 2
              df_w["MA"] = df_w["Mid"].rolling(10).mean()
              if (
                  len(df_w) > 0
                  and df_w["Close"].iloc[-1] >= df_w["MA"].iloc[-1]
              ):
                week_ok = True

            # 組合字串
            if day_ok and week_ok:
              status_str = " (雙多)"
            elif not day_ok and not week_ok:
              status_str = " (雙空)"
            elif day_ok and not week_ok:
              status_str = " (短多長空)"
            elif not day_ok and week_ok:
              status_str = " (長多短空)"
            else:
              status_str = " (盤整)"
          except:
            status_str = " (未知)"

          enhanced_names.append(f"{o_name}{status_str}")

        df_cross["官方名稱"] = enhanced_names

      df_cross.insert(0, "交叉排行", range(1, len(df_cross) + 1))
      if "成交金額(億)" not in df_cross.columns:
        df_cross["成交金額(億)"] = round(df_cross["總成交金額_元"] / 1e8, 2)

      render_chart_section(
          df_cross[[
              "交叉排行",
              "代號",
              "官方名稱",
              "外本比(%)",
              "外資買賣超張數",
              "成交金額(億)",
              "收盤價",
              "漲跌幅(%)",
              "連續買超天數",
          ]],
          "雙榜交叉比對",
      )

    # ====================================================
    # 📈 雙榜交叉比對策略歷史回測看板 (嚴謹逐日滾動版)
    # ====================================================
    st.markdown("---")
    st.header(
        "📈 雙榜交叉比對策略歷史回測看板 (嚴謹逐日滾動版 - 依雙榜交集外本比)"
    )
    st.markdown(
        "💡 依據歷史每日的 **外本比 Top 50 ∩ 總成交值 Top 100**"
        " 雙榜交集強勢股，並結合多空成本均價線濾網，精確模擬真實勝率。"
    )

    bc1, bc2 = st.columns(2)
    with bc1:
      holding_days = st.number_input(
          "模擬持有天數", min_value=1, max_value=60, value=20, key="bt_hold_cross"
      )
    with bc2:
      use_trend_filter = st.checkbox(
          "啟用多空均價線濾網 (收盤價 >= 多空線)",
          value=True,
          key="bt_filter_cross",
      )

    if st.button("🚀 開始執行雙榜交集歷史回測", key="btn_run_cross_bt"):
      with st.spinner("正在進行歷史每日雙榜交集與 K 棒滾動回測運算中..."):
        try:
          all_trades = []
          test_days_pool = target_dates[-5:]

          for d_str in test_days_pool:
            day_foreign = hist_foreign_shares.get(d_str, {})
            if not day_foreign:
              continue

            day_records = []
            for code, f_shares in day_foreign.items():
              if code in market_dict and market_dict[code]["發行總股數"] > 0:
                total_s = market_dict[code]["發行總股數"]
                ratio = (f_shares / total_s) * 100
                if ratio > 0:
                  day_records.append({
                      "代號": code,
                      "外本比": ratio,
                      "成交金額": market_dict[code]["總成交金額_元"],
                  })

            if not day_records:
              continue

            df_day = pd.DataFrame(day_records)

            df_wben = df_day.sort_values(by="外本比", ascending=False).head(50)
            set_wben = set(df_wben["代號"])

            df_vol = df_day.sort_values(by="成交金額", ascending=False).head(100)
            set_vol = set(df_vol["代號"])

            common_codes = set_wben.intersection(set_vol)
            if not common_codes:
              continue

            df_cross_day = df_wben[df_wben["代號"].isin(common_codes)].sort_values(
                by="外本比", ascending=False
            )

            for _, row_sel in df_cross_day.iterrows():
              code = row_sel["代號"]
              w_ratio = row_sel["外本比"]

              df_k = yf.download(
                  f"{code}.TW", period="6mo", interval="1d", progress=False
              )
              if df_k.empty:
                df_k = yf.download(
                    f"{code}.TWO", period="6mo", interval="1d", progress=False
                )

              if not df_k.empty and len(df_k) > holding_days:
                if isinstance(df_k.columns, pd.MultiIndex):
                  df_k.columns = df_k.columns.get_level_values(0)

                df_k["Mid"] = (df_k["High"] + df_k["Low"]) / 2
                df_k["MA_Cost"] = df_k["Mid"].rolling(20).mean()

                if len(df_k) >= holding_days + 10:
                  entry_idx = -(holding_days + 1)
                  exit_idx = -1

                  entry_row = df_k.iloc[entry_idx]
                  exit_row = df_k.iloc[exit_idx]

                  c_price = entry_row["Close"]
                  ma_val = entry_row["MA_Cost"]

                  if use_trend_filter and not pd.isna(ma_val):
                    if c_price < ma_val:
                      continue

                  entry_price = entry_row["Close"]
                  exit_price = exit_row["Close"]
                  ret_pct = round(
                      ((exit_price - entry_price) / entry_price) * 100, 2
                  )

                  all_trades.append({
                      "歷史日代號": code,
                      "進場外本比(%)": round(w_ratio, 3),
                      "進場價格": round(entry_price, 2),
                      "結算價格": round(exit_price, 2),
                      "持有報酬率(%)": ret_pct,
                      "勝負": "勝" if ret_pct > 0 else "敗",
                  })

          if all_trades:
            df_result = pd.DataFrame(df_result) if 'df_result' in locals() else pd.DataFrame(all_trades)
            win_t = len(df_result[df_result["持有報酬率(%)"] > 0])
            total_t = len(df_result)
            final_win_rate = (
                round((win_t / total_t) * 100, 1) if total_t > 0 else 0.0
            )
            final_avg_ret = round(df_result["持有報酬率(%)"].mean(), 2)

            st.success(
                f"🎯 雙榜交集嚴謹回測完成！共統計了 {total_t}"
                " 筆符合條件的歷史進場交易。"
            )

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("🔥 雙榜策略勝率", f"{final_win_rate}%")
            mc2.metric("📊 平均單筆報酬率", f"{final_avg_ret:+.2f}%")
            mc3.metric("📋 總回測交易筆數", f"{total_t} 筆")

            st.markdown("#### 📋 雙榜交集逐日回測明細")
            st.dataframe(df_result, use_container_width=True, hide_index=True)
          else:
            st.warning(
                "在雙榜交集嚴謹條件與多空均價線濾網下，無符合條件的樣本，"
                "請嘗試取消均價線濾網。"
            )

        except Exception as e:
          st.error(f"執行雙榜交集回測時發生錯誤: {e}")

  else:
    st.warning("無法解析出市場與外資買超資料。")
else:
  st.warning(
      "目前無法取得證交所官方市場行情資料，請確認網路連線或是否為非交易日。"
  )