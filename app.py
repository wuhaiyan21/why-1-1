import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from db import init_db, CATEGORIES, BASE_CURRENCY
from exchange_rates import seed_exchange_rates
from services import (
    get_year_month,
    get_month_totals,
    get_all_budgets,
    get_budget_warnings,
    get_over_expenses_with_cumulative,
    get_last_six_months,
    get_trend_data,
    check_and_clear_prev_month_budget,
)

st.set_page_config(page_title="家庭与个人开支看板", page_icon="💰", layout="wide")

init_db()
seed_exchange_rates()
check_and_clear_prev_month_budget()

st.title("💰 家庭与个人开支看板")

today = date.today()
current_ym = get_year_month(today)

warnings = get_budget_warnings(current_ym)
if warnings:
    for w in warnings:
        if w["level"] == "over":
            st.error(
                f"⚠️ 超支提醒：【{w['category']}】本月已消费 {w['spent']:.2f} {BASE_CURRENCY}，超过预算 {w['budget']:.2f} {BASE_CURRENCY}！"
            )
        else:
            st.warning(
                f"⚡ 预算提醒：【{w['category']}】本月已消费 {w['spent']:.2f} {BASE_CURRENCY}，达到预算的 {w['ratio']*100:.1f}%（预算 {w['budget']:.2f} {BASE_CURRENCY}）"
            )

col1, col2 = st.columns(2)

with col1:
    st.subheader(f"📊 本月（{current_ym}）各分类消费占比")
    totals = get_month_totals(current_ym)
    budgets = get_all_budgets(current_ym)
    pie_data = []
    for cat in CATEGORIES:
        pie_data.append({"分类": cat, "金额": totals.get(cat, 0), "预算": budgets.get(cat, 0)})
    df_pie = pd.DataFrame(pie_data)
    if df_pie["金额"].sum() > 0:
        fig_pie = px.pie(df_pie, values="金额", names="分类", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("本月暂无消费记录")

    st.subheader("📋 本月预算与消费对比")
    df_compare = pd.DataFrame(
        [
            {
                "分类": cat,
                "预算": budgets.get(cat, 0),
                "已消费": totals.get(cat, 0),
                "剩余": max(0, budgets.get(cat, 0) - totals.get(cat, 0)),
                "使用率": f"{(totals.get(cat, 0) / budgets.get(cat, 0) * 100):.1f}%" if budgets.get(cat, 0) > 0 else "-",
            }
            for cat in CATEGORIES
        ]
    )
    st.dataframe(df_compare, use_container_width=True, hide_index=True)

with col2:
    st.subheader("📈 近六个月消费趋势")
    months = get_last_six_months()
    trend = get_trend_data(months)
    df_trend = pd.DataFrame({"月份": list(trend.keys()), "消费总额": list(trend.values())})
    fig_line = px.line(df_trend, x="月份", y="消费总额", markers=True)
    fig_line.update_traces(line=dict(width=3))
    st.plotly_chart(fig_line, use_container_width=True)

st.subheader("🚨 超支分类明细")
over_expenses = get_over_expenses_with_cumulative(current_ym)
if over_expenses:
    df_over = pd.DataFrame(over_expenses)
    df_over["超支标记"] = df_over.apply(
        lambda r: f"🔴 第{r['over_sequence']}笔超支 +{r['over_amount']:.2f}" if r["is_over"] else "",
        axis=1,
    )
    df_over = df_over[
        [
            "category",
            "expense_date",
            "amount",
            "currency",
            "amount_base",
            "cumulative",
            "budget",
            "over_amount",
            "超支标记",
            "note",
        ]
    ]
    df_over.columns = [
        "分类",
        "消费日期",
        "金额",
        "币种",
        f"本位币({BASE_CURRENCY})",
        f"累计({BASE_CURRENCY})",
        f"预算({BASE_CURRENCY})",
        f"累计超支({BASE_CURRENCY})",
        "超支说明",
        "备注",
    ]

    def highlight_over(series):
        return [
            "background-color: #ffcccc; color: #8b0000; font-weight: bold"
            if idx in df_over.index and over_expenses[i]["is_over"]
            else ""
            for i, idx in enumerate(series.index)
        ]

    styled_df = df_over.style.apply(highlight_over, axis=0)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    over_cats = df_over[df_over["超支说明"] != ""]["分类"].unique()
    for cat in over_cats:
        cat_rows = df_over[(df_over["分类"] == cat) & (df_over["超支说明"] != "")]
        if len(cat_rows) > 0:
            first = cat_rows.iloc[0]
            st.caption(
                f"📌 【{cat}】从 {first['消费日期']} 开始超预算，累计超支 {first[f'累计超支({BASE_CURRENCY})']:.2f} {BASE_CURRENCY}，共 {len(cat_rows)} 笔超支记录（红色高亮行）。"
            )
else:
    st.success("本月暂无超支分类 🎉")
