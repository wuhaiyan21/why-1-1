import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime

from db import init_db, CATEGORIES, BASE_CURRENCY
from exchange_rates import seed_exchange_rates, CURRENCIES, convert_to_base, get_rate
from services import get_all_expenses, get_expense_by_id, update_expense

st.set_page_config(page_title="历史记录查询", page_icon="📜", layout="wide")

init_db()
seed_exchange_rates()

st.title("📜 历史记录查询")

col1, col2, col3 = st.columns(3)
with col1:
    start_date = st.date_input("起始日期", value=date.today() - timedelta(days=30))
with col2:
    end_date = st.date_input("结束日期", value=date.today())
with col3:
    category_filter = st.selectbox("分类筛选", ["全部"] + CATEGORIES)

start_str = start_date.strftime("%Y-%m-%d")
end_str = end_date.strftime("%Y-%m-%d")

expenses = get_all_expenses(start_str, end_str, category_filter)

if expenses:
    df = pd.DataFrame(expenses)
    df_display = df[["id", "expense_date", "category", "amount", "currency", "amount_base", "note"]].copy()
    df_display = df_display.sort_values("expense_date", ascending=False)
    df_display.columns = ["ID", "消费日期", "分类", "金额", "币种", f"本位币({BASE_CURRENCY})", "备注"]

    col_sel, col_del = st.columns([1, 1])
    with col_sel:
        expense_ids = [f"{row['ID']} - {row['消费日期']} - {row['分类']} - {row['金额']}{row['币种']} - {(row['备注'] or '')}" for _, row in df_display.iterrows()]
        selected_label = st.selectbox(
            "选择要编辑的记录",
            ["-- 请选择 --"] + expense_ids,
            key="select_expense",
        )
        selected_id = None
        if selected_label != "-- 请选择 --":
            selected_id = int(selected_label.split(" - ")[0])

    with col_del:
        st.write("")
        st.write("")
        edit_clicked = st.button("✏️ 编辑选中记录", type="primary", disabled=selected_id is None, use_container_width=True)

    if edit_clicked and selected_id:
        st.session_state["editing_id"] = selected_id
        st.rerun()

    st.dataframe(df_display.drop(columns=["ID"]), use_container_width=True, hide_index=True)

    total = df_display[f"本位币({BASE_CURRENCY})"].sum()
    st.info(f"📊 查询结果共 {len(df_display)} 条记录，合计：{total:.2f} {BASE_CURRENCY}")

    by_category = df_display.groupby("分类")[f"本位币({BASE_CURRENCY})"].sum().reset_index()
    by_category.columns = ["分类", f"合计({BASE_CURRENCY})"]
    by_category = by_category.sort_values(f"合计({BASE_CURRENCY})", ascending=False)
    st.subheader("按分类汇总")
    st.dataframe(by_category, use_container_width=True, hide_index=True)
else:
    st.warning("查询范围内没有记录")

if st.session_state.get("editing_id"):
    editing_id = st.session_state["editing_id"]
    expense = get_expense_by_id(editing_id)
    if expense:
        st.divider()
        st.subheader(f"✏️ 编辑记录 (ID: {editing_id})")
        with st.form("edit_form"):
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                new_amount = st.number_input("金额", min_value=0.01, step=0.01, value=float(expense["amount"]), key="edit_amount")
                new_currency = st.selectbox(
                    "币种",
                    list(CURRENCIES.keys()),
                    format_func=lambda x: f"{x} - {CURRENCIES[x]}",
                    index=list(CURRENCIES.keys()).index(expense["currency"]) if expense["currency"] in CURRENCIES else 0,
                    key="edit_currency",
                )
                new_category = st.selectbox(
                    "分类",
                    CATEGORIES,
                    index=CATEGORIES.index(expense["category"]) if expense["category"] in CATEGORIES else 0,
                    key="edit_category",
                )
            with col_e2:
                exp_date = datetime.strptime(expense["expense_date"], "%Y-%m-%d").date()
                new_expense_date = st.date_input("消费日期", value=exp_date, key="edit_date")
                new_note = st.text_input("备注（可选）", value=expense["note"] or "", key="edit_note")

            new_date_str = new_expense_date.strftime("%Y-%m-%d")
            rate = get_rate(new_currency, new_date_str)
            new_amount_base = convert_to_base(new_amount, new_currency, new_date_str)
            st.info(f"💱 汇率：1 {new_currency} = {rate:.4f} {BASE_CURRENCY}，折合本位币：{new_amount_base:.2f} {BASE_CURRENCY}")

            col_sub, col_cancel = st.columns([1, 1])
            with col_sub:
                submitted = st.form_submit_button("💾 保存修改", type="primary", use_container_width=True)
            with col_cancel:
                cancel = st.form_submit_button("❌ 取消编辑", use_container_width=True)

            if submitted:
                success, msg = update_expense(
                    editing_id, new_amount, new_currency, new_category, new_date_str, new_note if new_note else None
                )
                if success:
                    st.success(f"✅ {msg} 返回首页可查看图表已刷新。")
                    st.session_state["editing_id"] = None
                    st.rerun()
                else:
                    st.error(msg)
            if cancel:
                st.session_state["editing_id"] = None
                st.rerun()
    else:
        st.error("未找到要编辑的记录")
        st.session_state["editing_id"] = None
