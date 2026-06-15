import streamlit as st
import pandas as pd
from datetime import date, timedelta
from calendar import monthrange

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

tab1, tab2 = st.tabs(["⚙️ 手动设置预算", "📋 从其他月份复制"])

with tab1:
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

with tab2:
    st.subheader(f"从其他月份复制预算到 {target_ym}")
    st.caption("💡 选择一个已有预算的月份，预览后一键复制到当前目标月。已存在的分类预算将被覆盖，没有预算记录的分类会补上新值。")

    today = date.today()
    available_months = []
    for i in range(1, 25):
        new_year = today.year
        new_month = today.month - i
        while new_month <= 0:
            new_month += 12
            new_year -= 1
        d = date(new_year, new_month, 1)
        ym = get_year_month(d)
        bd = get_all_budgets(ym)
        total_budget = sum(bd.values())
        if total_budget > 0:
            available_months.append((ym, total_budget))

    if not available_months:
        st.info("暂无可复制的历史月份预算。请先在「手动设置」中设置某个月的预算。")
    else:
        source_options = [f"{ym}（合计 {total:.2f} {BASE_CURRENCY}）" for ym, total in available_months]
        source_ym_labels = st.selectbox(
            "选择源月份（已有预算数据的月份）",
            source_options,
            key="copy_source_select",
        )
        source_ym = source_ym_labels.split("（")[0]

        if "copy_confirmed" not in st.session_state:
            st.session_state["copy_confirmed"] = False

        col_preview, col_confirm = st.columns([1, 1])
        with col_preview:
            preview_clicked = st.button("👁️ 预览源月预算", use_container_width=True)
        with col_confirm:
            confirm_clicked = st.button("✅ 确认并复制到 " + target_ym, type="primary", use_container_width=True)

        if preview_clicked or st.session_state.get("copy_show_preview", False):
            st.session_state["copy_show_preview"] = True
            src_budgets = get_all_budgets(source_ym)
            cur_budgets = get_all_budgets(target_ym)

            preview_rows = []
            for cat in CATEGORIES:
                src_val = src_budgets.get(cat, 0)
                cur_val = cur_budgets.get(cat, 0)
                action = "新增" if cur_val == 0 and src_val > 0 else ("覆盖" if src_val != cur_val and src_val > 0 else ("保留" if cur_val == src_val else "无变更"))
                preview_rows.append({
                    "分类": cat,
                    f"源月({source_ym})": src_val,
                    f"目标月({target_ym})": cur_val,
                    f"复制后({target_ym})": src_val,
                    "操作": action,
                })
            df_preview = pd.DataFrame(preview_rows)
            src_total = sum(r[f"源月({source_ym})"] for r in preview_rows)
            cur_total = sum(r[f"目标月({target_ym})"] for r in preview_rows)

            st.markdown("### 📊 复制预览")
            st.warning(f"⚠️ 确认后，目标月 {target_ym} 的分类预算将被源月 {source_ym} 的值**完全覆盖**（源月为 0 的分类也会覆盖目标月的值）。")

            def highlight(row):
                if row["操作"] in ["覆盖", "新增"]:
                    return ["background-color: #fff3cd; font-weight: bold"] * len(row)
                return [""] * len(row)

            styled_preview = df_preview.style.apply(highlight, axis=1)
            st.dataframe(styled_preview, use_container_width=True, hide_index=True)

            st.info(f"📌 源月合计：{src_total:.2f} {BASE_CURRENCY}，目标月当前合计：{cur_total:.2f} {BASE_CURRENCY}，复制后目标月合计：{src_total:.2f} {BASE_CURRENCY}")

        if confirm_clicked:
            src_budgets = get_all_budgets(source_ym)
            overwrite_count = 0
            new_count = 0
            for cat in CATEGORIES:
                src_val = src_budgets.get(cat, 0)
                set_budget(cat, target_ym, src_val)
                old_val = get_all_budgets(target_ym)
            st.success(f"✅ 已成功从 {source_ym} 复制预算到 {target_ym}！所有 {len(CATEGORIES)} 个分类预算已更新。")
            st.session_state["copy_show_preview"] = False
            st.rerun()
