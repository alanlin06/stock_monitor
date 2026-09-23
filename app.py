from datetime import datetime, timedelta
import json
import os
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st


# =========================================================
# 基本設定
# =========================================================

st.set_page_config(
    page_title="台股強勢策略",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🎯 台股強勢策略")

DB_FILE = "industry_db.json"


# =========================================================
# 族群資料庫
# =========================================================

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
            json.dump(
                db_data,
                f,
                ensure_ascii=False,
                indent=4,
            )
    except Exception as e:
        st.error(f"儲存檔案失敗: {e}")


if "user_industry_map" not in st.session_state:
    st.session_state.user_industry_map = load_db()


# =========================================================
# 搜尋
# =========================================================

search_query = st.sidebar.text_input(
    "🔍 側邊欄快速查找台股",
    placeholder="輸入代號或名稱 (例: 2330)",
)


# =========================================================
# 取得 TWSE 資料
# =========================================================

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

        test_url = (
            "https://www.twse.com.tw/rwd/zh/afterTrading/"
            f"MI_INDEX?response=json&type=ALLBUT0999&date={d_str}"
        )

        try:
            res = session.get(
                test_url,
                timeout=5,
            )

            if res.status_code == 200:

                data = res.json()

                if (
                    data.get("stat") == "OK"
                    and len(data.get("tables", [])) > 0
                ):
                    dates.append(d_str)

                    if len(dates) >= 2:
                        break

        except Exception:
            pass

        curr -= timedelta(days=1)
        time.sleep(0.12)

    if len(dates) == 0:
        return {}, {}, {}, []

    latest_date = dates[0]
    prev_date = dates[1] if len(dates) > 1 else latest_date


    # =====================================================
    # T86 法人資料
    # =====================================================

    def get_t86_map(d_str):

        t_map = {}

        url = (
            "https://www.twse.com.tw/rwd/zh/fund/"
            f"T86?response=json&date={d_str}&selectType=ALLBUT0999"
        )

        try:

            r = session.get(
                url,
                timeout=6,
            )

            if r.status_code == 200:

                d = r.json()

                if d.get("stat") == "OK" and "data" in d:

                    for row in d["data"]:

                        if len(row) > 10:

                            code = str(row[0]).strip()
                            name = str(row[1]).strip()

                            if len(code) == 4 and code.isdigit():

                                try:

                                    f_val = float(
                                        str(row[4]).replace(",", "")
                                    )

                                    t_val = float(
                                        str(row[10]).replace(",", "")
                                    )

                                    t_map[code] = {
                                        "官方名稱": name,
                                        "外資淨買超股數": f_val,
                                        "投信淨買超股數": t_val,
                                    }

                                except Exception:
                                    pass

        except Exception:
            pass

        time.sleep(0.12)

        return t_map


    latest_inst = get_t86_map(latest_date)


    # =====================================================
    # 每日市場資料
    # =====================================================

    def get_day_market(d_str):

        m_dict = {}

        url = (
            "https://www.twse.com.tw/rwd/zh/afterTrading/"
            f"MI_INDEX?response=json&type=ALLBUT0999&date={d_str}"
        )

        try:

            res = session.get(
                url,
                timeout=8,
            )

            if res.status_code == 200:

                data = res.json()

                if data.get("stat") == "OK":

                    for table in data.get("tables", []):

                        if "data" not in table:
                            continue

                        for row in table["data"]:

                            if len(row) < 11:
                                continue

                            code = str(row[0]).strip()

                            if not (
                                len(code) == 4
                                and code.isdigit()
                            ):
                                continue

                            try:

                                name = str(row[1]).strip()

                                # 成交金額
                                tv = 0.0

                                try:
                                    tv = float(
                                        str(row[4]).replace(",", "")
                                    )
                                except Exception:

                                    try:
                                        tv = float(
                                            str(row[5]).replace(",", "")
                                        )
                                    except Exception:
                                        pass

                                # 收盤價
                                close_raw = (
                                    str(row[8])
                                    .replace(",", "")
                                    .strip()
                                )

                                if close_raw in ["--", "-", ""]:
                                    continue

                                close_p = float(close_raw)

                                # 漲跌
                                sign = (
                                    -1.0
                                    if (
                                        "-"
                                        in str(row[9])
                                        or "跌"
                                        in str(row[9])
                                    )
                                    else 1.0
                                )

                                chg_raw = (
                                    str(row[10])
                                    .replace(",", "")
                                    .strip()
                                )

                                if chg_raw not in ["--", "-", ""]:
                                    chg_val = (
                                        float(chg_raw) * sign
                                    )
                                else:
                                    chg_val = 0.0

                                # 漲跌幅
                                prev_p = close_p - chg_val

                                if prev_p > 0:
                                    pct_val = (
                                        chg_val / prev_p
                                    ) * 100
                                else:
                                    pct_val = 0.0

                                m_dict[code] = {
                                    "官方名稱": name,
                                    "收盤價": close_p,
                                    "漲跌幅(%)": round(
                                        pct_val,
                                        2,
                                    ),
                                    "成交金額": tv,
                                }

                            except Exception:
                                continue

        except Exception:
            pass

        return m_dict


    today_dict = get_day_market(latest_date)
    prev_dict = get_day_market(prev_date)

    return (
        today_dict,
        prev_dict,
        latest_inst,
        dates,
    )


# =========================================================
# 取得資料
# =========================================================

with st.spinner(
    "⏳ 正在取得今日與前日成交值百大與法人籌碼對應..."
):

    (
        today_dict,
        prev_dict,
        latest_inst,
        target_dates,
    ) = fetch_top100_data()


latest_date = (
    target_dates[0]
    if target_dates
    else ""
)

prev_date = (
    target_dates[1]
    if len(target_dates) > 1
    else ""
)


if latest_date:

    st.sidebar.markdown("---")

    st.sidebar.success(
        f"📅 官方同步日：{latest_date} "
        f"(對比 {prev_date})"
    )


# =========================================================
# Top N
# =========================================================

def get_top_n_codes(
    m_dict,
    n=100,
):

    s = sorted(
        [
            (
                k,
                v["成交金額"],
            )
            for k, v in m_dict.items()
            if v["成交金額"] > 0
        ],
        key=lambda x: x[1],
        reverse=True,
    )

    return set(
        [
            item[0]
            for item in s[:n]
        ]
    )


today_top100 = get_top_n_codes(
    today_dict,
    100,
)

prev_top100 = get_top_n_codes(
    prev_dict,
    100,
)


# =========================================================
# 新進榜與持續強勢
# =========================================================

newcomer_codes_up = [
    c
    for c in today_top100
    if (
        c not in prev_top100
        and today_dict[c]["漲跌幅(%)"] > 0
    )
]

recurring_codes_up = [
    c
    for c in today_top100
    if (
        c in prev_top100
        and today_dict[c]["漲跌幅(%)"] > 0
    )
]


# =========================================================
# 法人資訊
# =========================================================

def get_inst_info(code):

    return latest_inst.get(
        code,
        {
            "外資淨買超股數": 0.0,
            "投信淨買超股數": 0.0,
        },
    )


# =========================================================
# 族群法人參與分析
# =========================================================

def get_industry_institution_stats(industry):

    industry_codes = [
        code
        for code, ind in st.session_state.user_industry_map.items()
        if ind == industry
    ]

    if not industry_codes:
        return {
            "外資參與檔數": 0,
            "投信參與檔數": 0,
            "雙法人參與檔數": 0,
            "法人參與檔數": 0,
            "Top100檔數": 0,
        }

    fii_count = 0
    sitc_count = 0
    both_count = 0
    institutional_count = 0
    top100_count = 0

    for code in industry_codes:

        inst = get_inst_info(code)

        fii = inst["外資淨買超股數"]
        sitc = inst["投信淨買超股數"]

        if fii > 0:
            fii_count += 1

        if sitc > 0:
            sitc_count += 1

        if fii > 0 and sitc > 0:
            both_count += 1

        if fii > 0 or sitc > 0:
            institutional_count += 1

        if code in today_top100:
            top100_count += 1

    return {
        "外資參與檔數": fii_count,
        "投信參與檔數": sitc_count,
        "雙法人參與檔數": both_count,
        "法人參與檔數": institutional_count,
        "Top100檔數": top100_count,
    }


# =========================================================
# 判斷族群狀態
# =========================================================

def classify_industry_state(
    target_code,
    industry_stats,
):

    top100_count = industry_stats["Top100檔數"]
    institutional_count = industry_stats["法人參與檔數"]

    if top100_count >= 2:
        return "🔥 族群擴散"

    if (
        target_code in today_top100
        and institutional_count >= 2
    ):
        return "🟡 族群醞釀"

    return "⚪ 單兵先行"


# =========================================================
# 建立強勢股資料
# =========================================================

def build_group_stats_with_inst(
    codes_list,
):

    rows = []

    for c in codes_list:

        if c not in today_dict:
            continue

        info = today_dict[c]

        prev_info = prev_dict.get(
            c,
            {
                "成交金額": 0.0
            },
        )

        amt_today = info["成交金額"]
        amt_yesterday = prev_info["成交金額"]

        multiplier = (
            round(
                amt_today / amt_yesterday,
                2,
            )
            if amt_yesterday > 0
            else 0.0
        )

        pct_chg = info["漲跌幅(%)"]

        ind = st.session_state.user_industry_map.get(
            c,
            "未分類",
        )

        close_p = info["收盤價"]

        inst_info = get_inst_info(c)

        fii_shares = inst_info[
            "外資淨買超股數"
        ]

        sitc_shares = inst_info[
            "投信淨買超股數"
        ]

        est_total_shares = (
            (amt_today / close_p) * 15
            if close_p > 0
            else 1e7
        )

        fii_ratio = (
            fii_shares
            / est_total_shares
        ) * 100

        sitc_ratio = (
            sitc_shares
            / est_total_shares
        ) * 100

        combined_ratio = (
            fii_ratio
            + sitc_ratio
        )

        eff_ratio_factor = (
            multiplier
            / max(
                abs(pct_chg),
                0.5,
            )
            if multiplier > 0
            else 0.0
        )

        resonance_score = round(
            combined_ratio
            * min(
                eff_ratio_factor,
                5.0,
            ),
            3,
        )

        is_qualified_efficient = (
            pct_chg <= multiplier
        ) and (
            combined_ratio > 0
        )

        industry_stats = get_industry_institution_stats(
            ind
        )

        industry_state = classify_industry_state(
            c,
            industry_stats,
        )

        rows.append(
            {
                "代號": c,
                "官方名稱": info["官方名稱"],
                "🔥 效率籌碼共振分": resonance_score,
                "成交值放大倍數": multiplier,
                "漲跌幅(%)": pct_chg,
                "雙法人合佔比(%)": round(
                    combined_ratio,
                    3,
                ),
                "符合量價/籌碼優選": (
                    "符合"
                    if is_qualified_efficient
                    else "一般"
                ),
                "外本比(%)": round(
                    fii_ratio,
                    3,
                ),
                "投本比(%)": round(
                    sitc_ratio,
                    3,
                ),
                "收盤價": close_p,
                "成交值(億)": round(
                    amt_today / 100000000,
                    2,
                ),
                "外資買超(張)": round(
                    fii_shares / 1000,
                    1,
                ),
                "投信買超(張)": round(
                    sitc_shares / 1000,
                    1,
                ),
                "族群": ind,
                "族群狀態": industry_state,
                "族群外資參與檔數": (
                    industry_stats[
                        "外資參與檔數"
                    ]
                ),
                "族群投信參與檔數": (
                    industry_stats[
                        "投信參與檔數"
                    ]
                ),
                "族群雙法人參與檔數": (
                    industry_stats[
                        "雙法人參與檔數"
                    ]
                ),
                "族群法人參與檔數": (
                    industry_stats[
                        "法人參與檔數"
                    ]
                ),
                "族群Top100檔數": (
                    industry_stats[
                        "Top100檔數"
                    ]
                ),
            }
        )

    df = pd.DataFrame(rows)

    if df.empty:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
        )

    df = df.sort_values(
        by="🔥 效率籌碼共振分",
        ascending=False,
    ).reset_index(
        drop=True
    )

    total_count = len(df)

    group_summary = (
        df.groupby("族群")
        .agg(
            個股數=("代號", "count"),
            總成交值億=("成交值(億)", "sum"),
            平均共振分=("🔥 效率籌碼共振分", "mean"),
            平均放大倍數=("成交值放大倍數", "mean"),
            平均漲跌幅=("漲跌幅(%)", "mean"),
            平均雙法人合佔比=("雙法人合佔比(%)", "mean"),
            族群外資參與檔數=(
                "族群外資參與檔數",
                "max",
            ),
            族群投信參與檔數=(
                "族群投信參與檔數",
                "max",
            ),
            族群雙法人參與檔數=(
                "族群雙法人參與檔數",
                "max",
            ),
            族群法人參與檔數=(
                "族群法人參與檔數",
                "max",
            ),
            族群Top100檔數=(
                "族群Top100檔數",
                "max",
            ),
        )
        .reset_index()
    )

    group_summary["占比(%)"] = round(
        (
            group_summary["個股數"]
            / total_count
        )
        * 100,
        2,
    )

    group_summary["平均共振分"] = round(
        group_summary["平均共振分"],
        3,
    )
    group_summary["平均放大倍數"] = round(
        group_summary["平均放大倍數"],
        2,
    )
    group_summary["平均漲跌幅"] = round(
        group_summary["平均漲跌幅"],
        2,
    )
    group_summary["平均雙法人合佔比"] = round(
        group_summary["平均雙法人合佔比"],
        3,
    )

    cols = [
        "族群",
        "個股數",
        "總成交值億",
        "平均共振分",
        "平均放大倍數",
        "平均漲跌幅",
        "平均雙法人合佔比",
        "族群外資參與檔數",
        "族群投信參與檔數",
        "族群雙法人參與檔數",
        "族群法人參與檔數",
        "族群Top100檔數",
        "占比(%)",
    ]

    group_summary = group_summary[
        [
            c
            for c in cols
            if c in group_summary.columns
        ]
    ]

    group_summary = group_summary.sort_values(
        by="平均共振分",
        ascending=False,
    ).reset_index(
        drop=True
    )

    return (
        df,
        group_summary,
    )


# =========================================================
# 建立新進榜 / 持續強勢
# =========================================================

df_new_up, grp_new_up = (
    build_group_stats_with_inst(
        newcomer_codes_up
    )
)

df_rec_up, grp_rec_up = (
    build_group_stats_with_inst(
        recurring_codes_up
    )
)


# =========================================================
# 外資 / 投信 Top100 族群集中度
# =========================================================

def build_top100_institutional_concentration():

    fii_sorted = sorted(
        [
            (
                code,
                d["外資淨買超股數"],
            )
            for code, d in latest_inst.items()
            if d["外資淨買超股數"] > 0
        ],
        key=lambda x: x[1],
        reverse=True,
    )[:100]

    sitc_sorted = sorted(
        [
            (
                code,
                d["投信淨買超股數"],
            )
            for code, d in latest_inst.items()
            if d["投信淨買超股數"] > 0
        ],
        key=lambda x: x[1],
        reverse=True,
    )[:100]

    def process_inst_top100(lst):

        rows = []

        for code, shrs in lst:

            info = today_dict.get(
                code,
                {},
            )

            name = info.get(
                "官方名稱",
                latest_inst.get(
                    code,
                    {},
                ).get(
                    "官方名稱",
                    code,
                ),
            )

            close_p = info.get(
                "收盤價",
                100.0,
            )

            amt_today = info.get(
                "成交金額",
                close_p * shrs,
            )

            est_total_shares = (
                (
                    amt_today
                    / close_p
                )
                * 15
                if close_p > 0
                else 1e7
            )

            ratio = (
                shrs
                / est_total_shares
            ) * 100

            ind = (
                st.session_state
                .user_industry_map
                .get(
                    code,
                    "未分類",
                )
            )

            rows.append(
                {
                    "代號": code,
                    "官方名稱": name,
                    "買超股數": int(shrs),
                    "本比(%)": round(
                        ratio,
                        3,
                    ),
                    "族群": ind,
                }
            )

        df_temp = pd.DataFrame(rows)

        if df_temp.empty:
            return (
                pd.DataFrame(),
                pd.DataFrame(),
            )

        grp = (
            df_temp.groupby("族群")
            .agg(
                家數=("代號", "count"),
                總買超股數=(
                    "買超股數",
                    "sum",
                ),
                平均本比=(
                    "本比(%)",
                    "mean",
                ),
            )
            .reset_index()
        )

        grp["平均本比"] = round(
            grp["平均本比"],
            3,
        )

        grp["籌碼集中強度"] = round(
            grp["平均本比"]
            * np.sqrt(
                grp["家數"]
            ),
            3,
        )

        grp = grp.sort_values(
            by="總買超股數",
            ascending=False,
        ).reset_index(
            drop=True
        )

        return (
            df_temp,
            grp,
        )

    (
        df_fii_top,
        grp_fii_top,
    ) = process_inst_top100(
        fii_sorted
    )

    (
        df_sitc_top,
        grp_sitc_top,
    ) = process_inst_top100(
        sitc_sorted
    )

    if (
        not df_fii_top.empty
        and not df_sitc_top.empty
    ):

        common_industries = set(
            df_fii_top["族群"]
        ).intersection(
            set(
                df_sitc_top["族群"]
            )
        )

        common_industries.discard(
            "未分類"
        )

        overlap_rows = []

        for ind in common_industries:

            sub_fii = df_fii_top[
                df_fii_top["族群"] == ind
            ]

            sub_sitc = df_sitc_top[
                df_sitc_top["族群"] == ind
            ]

            fii_cnt = len(sub_fii)
            sitc_cnt = len(sub_sitc)

            total_cnt = (
                fii_cnt
                + sitc_cnt
            )

            fii_sum_shrs = (
                sub_fii[
                    "買超股數"
                ].sum()
            )

            sitc_sum_shrs = (
                sub_sitc[
                    "買超股數"
                ].sum()
            )

            fii_avg_ratio = (
                sub_fii[
                    "本比(%)"
                ].mean()
                if fii_cnt > 0
                else 0.0
            )

            sitc_avg_ratio = (
                sub_sitc[
                    "本比(%)"
                ].mean()
                if sitc_cnt > 0
                else 0.0
            )

            combined_avg_ratio = round(
                (
                    fii_avg_ratio
                    + sitc_avg_ratio
                )
                / 2.0,
                3,
            )

            double_inst_concentration = round(
                (
                    fii_avg_ratio
                    + sitc_avg_ratio
                )
                * np.sqrt(
                    total_cnt
                ),
                3,
            )

            overlap_rows.append(
                {
                    "重複族群": ind,
                    "外資家數": fii_cnt,
                    "外資買超股數": int(
                        fii_sum_shrs
                    ),
                    "投信家數": sitc_cnt,
                    "投信買超股數": int(
                        sitc_sum_shrs
                    ),
                    "雙法人合計股數": int(
                        fii_sum_shrs
                        + sitc_sum_shrs
                    ),
                    "入選合計家數": total_cnt,
                    "雙法人合佔比平均(%)": (
                        combined_avg_ratio
                    ),
                    "雙法人籌碼集中度(%)": (
                        double_inst_concentration
                    ),
                }
            )

        df_overlap = pd.DataFrame(
            overlap_rows
        )

        if not df_overlap.empty:

            df_overlap = df_overlap.sort_values(
                by="雙法人籌碼集中度(%)",
                ascending=False,
            ).reset_index(
                drop=True
            )

        else:
            df_overlap = pd.DataFrame()

    else:
        df_overlap = pd.DataFrame()

    return (
        df_fii_top,
        grp_fii_top,
        df_sitc_top,
        grp_sitc_top,
        df_overlap,
    )


(
    df_fii_top100,
    grp_fii_top100,
    df_sitc_top100,
    grp_sitc_top100,
    df_overlap_top100,
) = build_top100_institutional_concentration()


# =========================================================
# 編輯族群
# =========================================================

def update_map_from_editor(
    edited_df,
):

    if (
        not edited_df.empty
        and "代號" in edited_df.columns
        and "族群" in edited_df.columns
    ):

        updated_map = (
            st.session_state
            .user_industry_map
            .copy()
        )

        for _, row in edited_df.iterrows():

            c_code = str(
                row["代號"]
            ).strip()

            c_ind = (
                str(
                    row["族群"]
                ).strip()
                if pd.notna(
                    row["族群"]
                )
                else ""
            )

            updated_map[c_code] = c_ind

        st.session_state.user_industry_map = (
            updated_map
        )

        save_db(
            updated_map
        )

        st.success(
            "✅ 族群設定已成功更新！"
        )


# =========================================================
# 頁籤
# =========================================================

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "新進榜強勢股",
        "持續中強勢股",
        "雙法人Top100族群集中度比較",
        "全市場快速查找與歸類",
    ]
)


# =========================================================
# TAB 1
# =========================================================

with tab1:

    st.subheader(
        "🚀 新進榜強勢股"
    )

    if not grp_new_up.empty:

        c1, c2 = st.columns(
            [
                1.1,
                1.4,
            ]
        )

        with c1:

            st.markdown(
                "### 📊 族群分布"
            )

            st.dataframe(
                grp_new_up,
                use_container_width=True,
                hide_index=True,
            )

        with c2:

            st.markdown(
                f"### 📋 強勢股分布 ({len(df_new_up)}檔)"
            )

            ed_new = st.data_editor(
                df_new_up,
                use_container_width=True,
                hide_index=True,
                disabled=[
                    c
                    for c in df_new_up.columns
                    if c not in ["族群"]
                ],
                key="ed_new_up",
            )

            if st.button(
                "💾 儲存新面孔族群修改",
                key="btn_save_new",
            ):

                update_map_from_editor(
                    ed_new
                )

    else:

        st.info(
            "今日無符合條件的新進榜標的。"
        )


# =========================================================
# TAB 2
# =========================================================

with tab2:

    st.subheader(
        "📌 持續中強勢股"
    )

    if not grp_rec_up.empty:

        c1, c2 = st.columns(
            [
                1.1,
                1.4,
            ]
        )

        with c1:

            st.markdown(
                "### 📊 族群分布"
            )

            st.dataframe(
                grp_rec_up,
                use_container_width=True,
                hide_index=True,
            )

        with c2:

            st.markdown(
                f"### 📋 強勢股分布 ({len(df_rec_up)}檔)"
            )

            ed_rec = st.data_editor(
                df_rec_up,
                use_container_width=True,
                hide_index=True,
                disabled=[
                    c
                    for c in df_rec_up.columns
                    if c not in ["族群"]
                ],
                key="ed_rec_up",
            )

            if st.button(
                "💾 儲存常客族群修改",
                key="btn_save_rec",
            ):

                update_map_from_editor(
                    ed_rec
                )

    else:

        st.info(
            "目前無符合條件的持續中標的。"
        )


# =========================================================
# TAB 3
# =========================================================

with tab3:

    col_f, col_s = st.columns(
        2
    )

    with col_f:

        st.markdown(
            "### 🌐 外資 Top100 族群集中度"
        )

        st.dataframe(
            grp_fii_top100,
            use_container_width=True,
            hide_index=True,
        )

        with st.expander(
            "查看外資 Top100 個股明細"
        ):

            st.dataframe(
                df_fii_top100,
                use_container_width=True,
                hide_index=True,
            )

    with col_s:

        st.markdown(
            "### 🎯 投信 Top100 族群集中度"
        )

        st.dataframe(
            grp_sitc_top100,
            use_container_width=True,
            hide_index=True,
        )

        with st.expander(
            "查看投信 Top100 個股明細"
        ):

            st.dataframe(
                df_sitc_top100,
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("---")

    st.subheader(
        "🔥 雙法人重複族群集中度重算"
    )

    if not df_overlap_top100.empty:

        st.dataframe(
            df_overlap_top100,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "目前外資與投信 Top100 名單中無高度重疊之同一族群。"
        )


# =========================================================
# TAB 4
# =========================================================

with tab4:

    st.subheader(
        "🔍 全市場代號/名稱快速檢索與族群標註"
    )

    all_rows = []

    for code, info in today_dict.items():

        prev_info = prev_dict.get(
            code,
            {
                "成交金額": 0.0
            },
        )

        amt_today = info[
            "成交金額"
        ]

        amt_yesterday = prev_info[
            "成交金額"
        ]

        multiplier = (
            round(
                amt_today
                / amt_yesterday,
                2,
            )
            if amt_yesterday > 0
            else 0.0
        )

        pct_chg = info[
            "漲跌幅(%)"
        ]

        inst_info = get_inst_info(
            code
        )

        est_total_shares = (
            (
                amt_today
                / info["收盤價"]
            )
            * 15
            if info["收盤價"] > 0
            else 1e7
        )

        fii_ratio = (
            inst_info[
                "外資淨買超股數"
            ]
            / est_total_shares
        ) * 100

        sitc_ratio = (
            inst_info[
                "投信淨買超股數"
            ]
            / est_total_shares
        ) * 100

        combined_ratio = (
            fii_ratio
            + sitc_ratio
        )

        eff_ratio_factor = (
            multiplier
            / max(
                abs(pct_chg),
                0.5,
            )
            if multiplier > 0
            else 0.0
        )

        resonance_score = round(
            combined_ratio
            * min(
                eff_ratio_factor,
                5.0,
            ),
            3,
        )

        ind = (
            st.session_state
            .user_industry_map
            .get(
                code,
                "",
            )
        )

        if ind:

            industry_stats = (
                get_industry_institution_stats(
                    ind
                )
            )

            industry_state = (
                classify_industry_state(
                    code,
                    industry_stats,
                )
            )

        else:

            industry_stats = {
                "外資參與檔數": 0,
                "投信參與檔數": 0,
                "雙法人參與檔數": 0,
                "法人參與檔數": 0,
                "Top100檔數": 0,
            }

            industry_state = (
                "⚪ 未分類"
            )

        all_rows.append(
            {
                "代號": code,
                "官方名稱": info["官方名稱"],
                "🔥 效率籌碼共振分": resonance_score,
                "成交值放大倍數": multiplier,
                "漲跌幅(%)": pct_chg,
                "雙法人合佔比(%)": round(
                    combined_ratio,
                    3,
                ),
                "符合量價/籌碼優選": (
                    "符合"
                    if (
                        pct_chg <= multiplier
                        and combined_ratio > 0
                    )
                    else "一般"
                ),
                "外本比(%)": round(
                    fii_ratio,
                    3,
                ),
                "投本比(%)": round(
                    sitc_ratio,
                    3,
                ),
                "收盤價": info[
                    "收盤價"
                ],
                "成交值(億)": round(
                    amt_today
                    / 100000000,
                    2,
                ),
                "外資買超(張)": round(
                    inst_info[
                        "外資淨買超股數"
                    ]
                    / 1000,
                    1,
                ),
                "投信買超(張)": round(
                    inst_info[
                        "投信淨買超股數"
                    ]
                    / 1000,
                    1,
                ),
                "族群": ind,
                "族群狀態": industry_state,
                "族群外資參與檔數": (
                    industry_stats[
                        "外資參與檔數"
                    ]
                ),
                "族群投信參與檔數": (
                    industry_stats[
                        "投信參與檔數"
                    ]
                ),
                "族群雙法人參與檔數": (
                    industry_stats[
                        "雙法人參與檔數"
                    ]
                ),
                "族群法人參與檔數": (
                    industry_stats[
                        "法人參與檔數"
                    ]
                ),
                "族群Top100檔數": (
                    industry_stats[
                        "Top100檔數"
                    ]
                ),
            }
        )

    df_all = pd.DataFrame(
        all_rows
    )

    if search_query:

        df_all = df_all[
            df_all["代號"].str.contains(
                search_query
            )
            |
            df_all["官方名稱"].str.contains(
                search_query
            )
        ]

    ed_all = st.data_editor(
        df_all,
        use_container_width=True,
        hide_index=True,
        disabled=[
            c
            for c in df_all.columns
            if c != "族群"
        ],
        key="ed_all_search",
    )

    if st.button(
        "💾 儲存全市場族群修改",
        key="btn_save_all",
    ):

        update_map_from_editor(
            ed_all
        )