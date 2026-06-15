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
    st.caption("💡 选择一个已有预算的月份，**必须先点预览**查看对照表，确认后再复制。已存在的分类预算将被覆盖（源月为 0 的分类不会覆盖目标月），没有预算记录的分类会补上新值。")

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

        if "copy_previewed_source" not in st.session_state:
            st.session_state["copy_previewed_source"] = None

        col_preview, col_confirm = st.columns([1, 1])
        with col_preview:
            preview_clicked = st.button("👁️ 预览源月预算", use_container_width=True)
        with col_confirm:
            has_previewed = st.session_state.get("copy_previewed_source") == source_ym
            confirm_clicked = st.button(
                "✅ 确认并复制到 " + target_ym,
                type="primary",
                use_container_width=True,
                disabled=not has_previewed,
                help="请先点击左侧「预览源月预算」查看对照表后再确认复制。"
            )

        if not has_previewed:
            st.caption("ℹ️ 请先点击「预览源月预算」查看各分类复制对照表。")

        if preview_clicked or has_previewed:
            if preview_clicked:
                st.session_state["copy_previewed_source"] = source_ym
                st.session_state["copy_show_preview"] = True
                st.rerun()
            src_budgets = get_all_budgets(source_ym)
            cur_budgets = get_all_budgets(target_ym)

            preview_rows = []
            will_change = 0
            for cat in CATEGORIES:
                src_val = src_budgets.get(cat, 0)
                cur_val = cur_budgets.get(cat, 0)
                if src_val == 0 and cur_val > 0:
                    action = "保留（源月为0）"
                    after_val = cur_val
                elif src_val > 0 and cur_val == 0:
                    action = "新增"
                    after_val = src_val
                    will_change += 1
                elif src_val > 0 and src_val != cur_val:
                    action = "覆盖"
                    after_val = src_val
                    will_change += 1
                elif src_val > 0 and src_val == cur_val:
                    action = "已一致"
                    after_val = src_val
                else:
                    action = "无变更"
                    after_val = cur_val
                preview_rows.append({
                    "分类": cat,
                    f"源月({source_ym})": src_val,
                    f"目标月({target_ym})": cur_val,
                    f"复制后({target_ym})": after_val,
                    "操作": action,
                })
            df_preview = pd.DataFrame(preview_rows)
            src_total_positive = sum(max(src_budgets.get(cat, 0), 0) for cat in CATEGORIES)
            cur_total = sum(r[f"目标月({target_ym})"] for r in preview_rows)
            after_total = sum(r[f"复制后({target_ym})"] for r in preview_rows)

            st.markdown("### 📊 复制预览")
            if will_change > 0:
                st.warning(f"⚠️ 确认后，将有 **{will_change}** 个分类预算变更（新增或覆盖）。源月为 0 的分类不会修改目标月已有值。")
            else:
                st.info("ℹ️ 所有分类已一致或源月为 0 无需修改，无需复制。")

            def highlight(row):
                if row["操作"] in ["覆盖", "新增"]:
                    return ["background-color: #fff3cd; font-weight: bold"] * len(row)
                if row["操作"] == "保留（源月为0）":
                    return ["background-color: #e3f2fd; color: #0d47a1"] * len(row)
                return [""] * len(row)

            styled_preview = df_preview.style.apply(highlight, axis=1)
            st.dataframe(styled_preview, use_container_width=True, hide_index=True)

            st.info(f"📌 源月有效预算合计（非0）：{src_total_positive:.2f} {BASE_CURRENCY}，目标月当前合计：{cur_total:.2f} {BASE_CURRENCY}，复制后目标月合计：{after_total:.2f} {BASE_CURRENCY}")

        if confirm_clicked and has_previewed:
            src_budgets = get_all_budgets(source_ym)
            cur_budgets = get_all_budgets(target_ym)
            changed_count = 0
            for cat in CATEGORIES:
                src_val = src_budgets.get(cat, 0)
                cur_val = cur_budgets.get(cat, 0)
                if src_val > 0 and src_val != cur_val:
                    set_budget(cat, target_ym, src_val)
                    changed_count += 1
            st.success(f"✅ 已成功从 {source_ym} 复制预算到 {target_ym}！共更新 {changed_count} 个分类。")
            st.session_state["copy_previewed_source"] = None
            st.session_state["copy_show_preview"] = False
            st.rerun()
