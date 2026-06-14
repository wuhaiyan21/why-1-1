import streamlit as st
import pandas as pd
from datetime import date, timedelta

from db import init_db, CATEGORIES, BASE_CURRENCY
from exchange_rates import seed_exchange_rates
from services import get_all_expenses

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
    df = df[["expense_date", "category", "amount", "currency", "amount_base", "note"]]
    df.columns = ["消费日期", "分类", "金额", "币种", f"本位币({BASE_CURRENCY})", "备注"]
    df = df.sort_values("消费日期", ascending=False)

    st.dataframe(df, use_container_width=True, hide_index=True)

    total = df[f"本位币({BASE_CURRENCY})"].sum()
    st.info(f"📊 查询结果共 {len(df)} 条记录，合计：{total:.2f} {BASE_CURRENCY}")

    by_category = df.groupby("分类")[f"本位币({BASE_CURRENCY})"].sum().reset_index()
    by_category.columns = ["分类", f"合计({BASE_CURRENCY})"]
    by_category = by_category.sort_values(f"合计({BASE_CURRENCY})", ascending=False)
    st.subheader("按分类汇总")
    st.dataframe(by_category, use_container_width=True, hide_index=True)
else:
    st.warning("查询范围内没有记录")
