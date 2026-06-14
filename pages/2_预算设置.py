import streamlit as st
from datetime import date

from db import init_db, CATEGORIES, BASE_CURRENCY
from exchange_rates import seed_exchange_rates
from services import get_year_month, get_all_budgets, set_budget, get_month_totals

st.set_page_config(page_title="预算设置", page_icon="📋", layout="centered")

init_db()
seed_exchange_rates()

st.title("📋 预算设置")

current_ym = get_year_month(date.today())
year = st.number_input("年份", min_value=2000, max_value=2100, value=int(current_ym.split("-")[0]))
month = st.number_input("月份", min_value=1, max_value=12, value=int(current_ym.split("-")[1]))
target_ym = f"{year:04d}-{month:02d}"

st.subheader(f"设置 {target_ym} 的分类预算（单位：{BASE_CURRENCY}）")

budgets = get_all_budgets(target_ym)
totals = get_month_totals(target_ym)

with st.form("budget_form"):
    new_budgets = {}
    for cat in CATEGORIES:
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            st.markdown(f"**{cat}**")
        with col2:
            new_budgets[cat] = st.number_input(
                f"预算_{cat}",
                min_value=0.0,
                step=100.0,
                value=float(budgets.get(cat, 0)),
                label_visibility="collapsed",
                key=f"budget_{cat}",
            )
        with col3:
            spent = totals.get(cat, 0)
            st.write(f"已消费：{spent:.2f}")

    submitted = st.form_submit_button("保存预算", type="primary")
    if submitted:
        for cat, amt in new_budgets.items():
            set_budget(cat, target_ym, amt)
        st.success(f"✅ {target_ym} 的预算已保存！")
