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
    get_trend_data_by_category,
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

    chart_mode = st.radio(
        "图表模式",
        ["仅显示总额", "按分类对比（叠加总额）", "仅按分类对比"],
        horizontal=True,
        help="选择「按分类对比」可在下方多选分类进行对比",
    )

    if chart_mode != "仅显示总额":
        default_cats = CATEGORIES[:2] if len(CATEGORIES) >= 2 else CATEGORIES
        selected_categories = st.multiselect(
            "选择分类进行对比（至少选 2 个效果最佳）",
            CATEGORIES,
            default=default_cats,
        )
    else:
        selected_categories = []

    trend_data_long = []

    if chart_mode == "仅显示总额" or chart_mode == "按分类对比（叠加总额）":
        total_trend = get_trend_data(months)
        for m in months:
            trend_data_long.append({"月份": m, "金额": total_trend[m], "系列": f"消费总额"})

    if chart_mode != "仅显示总额" and selected_categories:
        cat_trend = get_trend_data_by_category(months, selected_categories)
        for cat in selected_categories:
            for m in months:
                trend_data_long.append({"月份": m, "金额": cat_trend[cat][m], "系列": f"{cat}"})

    if trend_data_long:
        df_trend = pd.DataFrame(trend_data_long)
        if len(selected_categories) > 0 and chart_mode != "仅显示总额":
            color_map = {}
            if chart_mode == "按分类对比（叠加总额）":
                color_map[f"消费总额"] = "#2c3e50"
            palette = px.colors.qualitative.Set2
            for idx, cat in enumerate(selected_categories):
                color_map[cat] = palette[idx % len(palette)]
            fig_line = px.line(
                df_trend,
                x="月份",
                y="金额",
                color="系列",
                markers=True,
                color_discrete_map=color_map,
                labels={"金额": f"金额（{BASE_CURRENCY}）"},
            )
        else:
            fig_line = px.line(
                df_trend,
                x="月份",
                y="金额",
                color="系列",
                markers=True,
                labels={"金额": f"金额（{BASE_CURRENCY}）"},
            )
        fig_line.update_traces(line=dict(width=3))
        fig_line.update_layout(
            legend_title="",
            yaxis_title=f"金额（{BASE_CURRENCY}）",
        )
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("请选择至少一个分类，或切换到「仅显示总额」模式")

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
