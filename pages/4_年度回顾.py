import streamlit as st
import pandas as pd
from datetime import date

from db import init_db, CATEGORIES, BASE_CURRENCY
from exchange_rates import seed_exchange_rates
from services import (
    get_year_month,
    get_yearly_summary_data,
)

st.set_page_config(page_title="年度回顾", page_icon="📅", layout="wide")

init_db()
seed_exchange_rates()

st.title("📅 年度回顾")

today = date.today()
current_year = today.year
current_ym = get_year_month(today)

mode = st.radio(
    "查询模式",
    ["完整年份", "指定月份区间"],
    horizontal=True,
    help="选择「完整年份」查看全年数据，或选择「指定月份区间」自定义起止月份"
)

year_val = None
start_ym_val = None
end_ym_val = None

if mode == "完整年份":
    year_val = str(st.number_input("选择年份", min_value=2000, max_value=2100, value=current_year, step=1))
else:
    col1, col2 = st.columns(2)
    with col1:
        default_start_year = current_year
        default_start_month = 1
        start_year = st.number_input("起始年份", min_value=2000, max_value=2100, value=default_start_year, key="start_year")
        start_month = st.number_input("起始月份", min_value=1, max_value=12, value=default_start_month, key="start_month")
        start_ym_val = f"{int(start_year):04d}-{int(start_month):02d}"
    with col2:
        default_end_year = current_year
        default_end_month = today.month
        end_year = st.number_input("结束年份", min_value=2000, max_value=2100, value=default_end_year, key="end_year")
        end_month = st.number_input("结束月份", min_value=1, max_value=12, value=default_end_month, key="end_month")
        end_ym_val = f"{int(end_year):04d}-{int(end_month):02d}"

query_clicked = st.button("🔍 查询", type="primary", use_container_width=True)

if query_clicked or ("yearly_summary_result" in st.session_state):
    if query_clicked:
        if mode == "完整年份":
            result = get_yearly_summary_data(year=year_val)
        else:
            if start_ym_val > end_ym_val:
                st.error(f"❌ 起始月份 {start_ym_val} 不能晚于结束月份 {end_ym_val}，请调整后重新查询。")
                st.session_state.pop("yearly_summary_result", None)
                st.stop()
            result = get_yearly_summary_data(start_ym=start_ym_val, end_ym=end_ym_val)
        st.session_state["yearly_summary_result"] = result
    else:
        result = st.session_state["yearly_summary_result"]

    if not result.get("success", False):
        st.error(f"❌ {result.get('error', '查询失败')}")
        st.stop()

    st.success(f"✅ 查询成功：{result['start_ym']} 至 {result['end_ym']}，共 {len(result['months'])} 个月")

    if result["warning_messages"]:
        st.subheader("⚠️ 预算记录警告")
        for msg in result["warning_messages"]:
            st.warning(msg)

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["📊 月度合计表", "📁 分类明细表", "🚨 超支月份清单"])

    with tab1:
        st.subheader(f"📊 各月总支出、总预算与执行率（{result['start_ym']} ~ {result['end_ym']}）")
        df_summary = pd.DataFrame(result["summary_rows"])

        def highlight_over_row(row):
            over = False
            budget = row["总预算"]
            if isinstance(row["执行率(%)"], (int, float)) and budget > 0 and row["总支出"] > budget:
                over = True
            return ["background-color: #ffcccc; color: #8b0000; font-weight: bold" if over else "" for _ in row]

        styled_summary = df_summary.style.apply(highlight_over_row, axis=1)
        st.dataframe(styled_summary, use_container_width=True, hide_index=True)
        st.caption("💡 超支月份已用红色高亮标记。执行率「-」表示该月份未设置任何预算记录。")

    with tab2:
        st.subheader(f"📁 各月各分类支出与预算（{result['start_ym']} ~ {result['end_ym']}）")
        df_category = pd.DataFrame(result["category_rows"])
        st.dataframe(df_category, use_container_width=True, hide_index=True)
        st.caption(f"💡 共包含 {len(CATEGORIES)} 个分类：{'、'.join(CATEGORIES)}。每个分类展示实际支出与预算金额。")

    with tab3:
        st.subheader(f"🚨 超支月份清单（{result['start_ym']} ~ {result['end_ym']}）")
        if result["overexpense_months"]:
            df_over = pd.DataFrame(result["overexpense_months"])
            df_over_display = df_over[["月份", "总支出", "总预算", "超支金额"]]

            def highlight_amount_col(val):
                return "background-color: #ff6b6b; color: white; font-weight: bold"

            styled_over = df_over_display.style.applymap(highlight_amount_col, subset=["超支金额"])
            st.dataframe(styled_over, use_container_width=True, hide_index=True)
            st.caption("📌 排序规则：超支金额从大到小，金额相同按月份先后。")
        else:
            st.success("🎉 查询范围内无超支月份，预算执行良好！")

    st.markdown("---")
    st.subheader("📥 一键下载 CSV 文件")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📁 下载分类明细 CSV",
            data=result["category_csv"].encode("utf-8-sig"),
            file_name="monthly_category_summary.csv",
            mime="text/csv",
            use_container_width=True,
            help="包含每个月份各分类的实际支出与预算，列顺序与命令行工具导出完全一致"
        )
    with col2:
        st.download_button(
            label="📊 下载月度合计 CSV",
            data=result["summary_csv"].encode("utf-8-sig"),
            file_name="monthly_total_summary.csv",
            mime="text/csv",
            use_container_width=True,
            help="包含每个月份的总支出、总预算与执行率，列顺序与命令行工具导出完全一致"
        )

    st.markdown("### 📝 命令行验证说明")
    if mode == "完整年份":
        st.code(f"python yearly_summary.py --year {year_val} --format csv --db ./data/expenses.db --output-dir ./output", language="bash")
    else:
        st.code(f"python yearly_summary.py --start {start_ym_val} --end {end_ym_val} --format csv --db ./data/expenses.db --output-dir ./output", language="bash")
    st.caption("使用上述命令可获得与页面上「一键下载」完全一致的 CSV 文件。")
