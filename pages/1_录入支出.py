import streamlit as st
from datetime import date

from db import init_db, CATEGORIES, BASE_CURRENCY
from exchange_rates import seed_exchange_rates, CURRENCIES, convert_to_base, get_rate
from services import add_expense, get_year_month, get_budget, get_category_month_total

st.set_page_config(page_title="录入支出", page_icon="✏️", layout="centered")

init_db()
seed_exchange_rates()

st.title("✏️ 录入支出")

with st.form("expense_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input("金额", min_value=0.01, step=0.01, value=0.01)
        currency = st.selectbox("币种", list(CURRENCIES.keys()), format_func=lambda x: f"{x} - {CURRENCIES[x]}")
        category = st.selectbox("分类", CATEGORIES)
    with col2:
        expense_date = st.date_input("消费日期", value=date.today())
        note = st.text_input("备注（可选）", "")

    expense_date_str = expense_date.strftime("%Y-%m-%d")
    rate = get_rate(currency, expense_date_str)
    amount_base = convert_to_base(amount, currency, expense_date_str)
    st.info(f"💱 汇率：1 {currency} = {rate:.4f} {BASE_CURRENCY}，折合本位币：{amount_base:.2f} {BASE_CURRENCY}")

    ym = get_year_month(expense_date)
    budget = get_budget(category, ym)
    current_total = get_category_month_total(category, ym)
    if budget > 0:
        remaining = budget - current_total
        st.write(f"📋 【{category}】{ym} 预算：{budget:.2f}，已消费：{current_total:.2f}，剩余：{max(0, remaining):.2f} {BASE_CURRENCY}")
        if remaining <= 0:
            st.error(f"该分类本月预算已用尽，请先在预算设置页调高预算。")

    submitted = st.form_submit_button("确认录入", type="primary")
    if submitted:
        success, msg = add_expense(amount, currency, category, expense_date_str, note if note else None)
        if success:
            st.success(msg)
        else:
            st.error(msg)
