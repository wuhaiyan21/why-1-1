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
    help="选择「完整年份」查看全年数据，或选择「指定月份区间」自定义起止月份",
    key="query_mode"
)

last_mode = st.session_state.get("_last_mode", mode)
if mode != last_mode:
    for k in ["current_summary_result", "current_query_mode", "current_year_val", "current_start_ym", "current_end_ym"]:
        st.session_state.pop(k, None)
    st.session_state["_last_mode"] = mode
    st.rerun()

year_val = None
start_ym_val = None
end_ym_val = None

with st.form("yearly_query_form"):
    if mode == "完整年份":
        year_val = str(st.number_input("选择年份", min_value=2000, max_value=2100, value=current_year, step=1, key="year_input"))
    else:
        col1, col2 = st.columns(2)
        with col1:
            default_start_year = current_year
            default_start_month = 1
            start_year = st.number_input("起始年份", min_value=2000, max_value=2100, value=default_start_year, key="start_year_input")
            start_month = st.number_input("起始月份", min_value=1, max_value=12, value=default_start_month, key="start_month_input")
            start_ym_val = f"{int(start_year):04d}-{int(start_month):02d}"
        with col2:
            default_end_year = current_year
            default_end_month = today.month
            end_year = st.number_input("结束年份", min_value=2000, max_value=2100, value=default_end_year, key="end_year_input")
            end_month = st.number_input("结束月份", min_value=1, max_value=12, value=default_end_month, key="end_month_input")
            end_ym_val = f"{int(end_year):04d}-{int(end_month):02d}"

    query_clicked = st.form_submit_button("🔍 查询", type="primary", use_container_width=True)

    if query_clicked:
        for k in ["current_summary_result", "current_query_mode", "current_year_val", "current_start_ym", "current_end_ym"]:
            st.session_state.pop(k, None)

        if mode == "指定月份区间" and start_ym_val > end_ym_val:
            st.error(f"❌ 起始月份 {start_ym_val} 不能晚于结束月份 {end_ym_val}，请调整后重新查询。")
            st.stop()

        if mode == "完整年份":
            result = get_yearly_summary_data(year=year_val)
        else:
            result = get_yearly_summary_data(start_ym=start_ym_val, end_ym=end_ym_val)

        if not result.get("success", False):
            st.error(f"❌ {result.get('error', '查询失败')}")
        else:
            st.session_state["current_summary_result"] = result
            st.session_state["current_query_mode"] = mode
            st.session_state["current_year_val"] = year_val
            st.session_state["current_start_ym"] = start_ym_val
            st.session_state["current_end_ym"] = end_ym_val
            st.rerun()

has_result = st.session_state.get("current_summary_result") is not None

if has_result:
    result = st.session_state["current_summary_result"]
    display_mode = st.session_state["current_query_mode"]
    display_year = st.session_state["current_year_val"]
    display_start = st.session_state["current_start_ym"]
    display_end = st.session_state["current_end_ym"]

    if mode == "完整年份":
        current_input_params = {"mode": mode, "year": year_val}
        queried_params = {"mode": display_mode, "year": display_year}
        params_match = (mode == display_mode) and (year_val == display_year)
        current_params_desc = f"{mode} {year_val}"
        queried_params_desc = f"{display_mode} {display_year}"
    else:
        current_input_params = {"mode": mode, "start": start_ym_val, "end": end_ym_val}
        queried_params = {"mode": display_mode, "start": display_start, "end": display_end}
        params_match = (mode == display_mode) and (start_ym_val == display_start) and (end_ym_val == display_end)
        current_params_desc = f"{mode} {start_ym_val} ~ {end_ym_val}"
        queried_params_desc = f"{display_mode} {display_start} ~ {display_end}"

    status_container = st.container()
    with status_container:
        if not params_match:
            st.warning(
                f"⚠️ **当前输入参数**：{current_params_desc}　|　"
                f"**当前展示数据参数**：{queried_params_desc}　|　"
                f"两者不一致，请点击「查询」按钮刷新数据。"
            )
        else:
            st.success(f"✅ 查询成功：{result['start_ym']} 至 {result['end_ym']}，共 {len(result['months'])} 个月")

    if st.button("🗑️ 清除当前查询结果", use_container_width=False, key="clear_result_btn"):
        for k in ["current_summary_result", "current_query_mode", "current_year_val", "current_start_ym", "current_end_ym"]:
            st.session_state.pop(k, None)
        st.rerun()

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
    st.subheader(f"📥 一键下载 CSV 文件（数据范围：{result['start_ym']} ~ {result['end_ym']}）")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label=f"📁 下载分类明细 CSV",
            data=result["category_csv"].encode("utf-8-sig"),
            file_name="monthly_category_summary.csv",
            mime="text/csv",
            use_container_width=True,
            help=f"查询参数：{queried_params_desc}，列顺序与命令行工具导出完全一致"
        )
    with col2:
        st.download_button(
            label=f"📊 下载月度合计 CSV",
            data=result["summary_csv"].encode("utf-8-sig"),
            file_name="monthly_total_summary.csv",
            mime="text/csv",
            use_container_width=True,
            help=f"查询参数：{queried_params_desc}，列顺序与命令行工具导出完全一致"
        )

    st.markdown(f"### 📝 命令行验证说明（基于查询参数：{queried_params_desc}）")
    if display_mode == "完整年份":
        st.code(f"python yearly_summary.py --year {display_year} --format csv --db ./data/expenses.db --output-dir ./output", language="bash")
    else:
        st.code(f"python yearly_summary.py --start {display_start} --end {display_end} --format csv --db ./data/expenses.db --output-dir ./output", language="bash")
    st.caption("使用上述命令可获得与页面上「一键下载」完全一致的 CSV 文件。")
else:
    st.info("👆 请在上方选择查询参数，然后点击「查询」按钮查看年度汇总数据。")
