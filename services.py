from datetime import datetime, date
from typing import Optional, Tuple, List, Dict, Any
import csv
import io

import streamlit as st

from db import get_connection, CATEGORIES
from exchange_rates import convert_to_base, CURRENCIES


def get_year_month(d: date) -> str:
    return d.strftime("%Y-%m")


def is_duplicate(amount: float, category: str, expense_date: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM expenses WHERE amount = ? AND category = ? AND expense_date = ?",
            (amount, category, expense_date),
        )
        row = cursor.fetchone()
        return row["cnt"] > 0


def add_expense(
    amount: float,
    currency: str,
    category: str,
    expense_date: str,
    note: Optional[str] = None,
) -> Tuple[bool, str]:
    if is_duplicate(amount, category, expense_date):
        return False, "重复录入：相同金额、分类、日期的记录已存在。"

    d = datetime.strptime(expense_date, "%Y-%m-%d").date()
    amount_base = convert_to_base(amount, currency, expense_date)
    year_month = get_year_month(d)

    budget = get_budget(category, year_month)
    if budget > 0:
        current_total = get_category_month_total(category, year_month)
        if current_total + amount_base > budget:
            return False, f"{category}分类本月预算已用尽（预算：{budget}，已消费：{current_total}），请先调高预算。"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO expenses (amount, currency, amount_base, category, expense_date, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                amount,
                currency,
                amount_base,
                category,
                expense_date,
                note,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    st.cache_data.clear()
    return True, "录入成功。"


@st.cache_data(ttl=60)
def get_budget(category: str, year_month: str) -> float:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT amount FROM budgets WHERE category = ? AND year_month = ?",
            (category, year_month),
        )
        row = cursor.fetchone()
        return row["amount"] if row else 0.0


def set_budget(category: str, year_month: str, amount: float):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO budgets (category, year_month, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(category, year_month) DO UPDATE SET amount = excluded.amount
            """,
            (category, year_month, amount),
        )
        conn.commit()
    st.cache_data.clear()


@st.cache_data(ttl=60)
def get_all_budgets(year_month: str) -> dict:
    result = {c: 0.0 for c in CATEGORIES}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT category, amount FROM budgets WHERE year_month = ?",
            (year_month,),
        )
        for row in cursor.fetchall():
            result[row["category"]] = row["amount"]
    return result


@st.cache_data(ttl=60)
def get_category_month_total(category: str, year_month: str) -> float:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(amount_base), 0) as total FROM expenses WHERE category = ? AND strftime('%Y-%m', expense_date) = ?",
            (category, year_month),
        )
        row = cursor.fetchone()
        return row["total"] if row else 0.0


@st.cache_data(ttl=60)
def get_month_totals(year_month: str) -> dict:
    result = {c: 0.0 for c in CATEGORIES}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT category, COALESCE(SUM(amount_base), 0) as total FROM expenses WHERE strftime('%Y-%m', expense_date) = ? GROUP BY category",
            (year_month,),
        )
        for row in cursor.fetchall():
            result[row["category"]] = row["total"]
    return result


@st.cache_data(ttl=60)
def get_budget_warnings(year_month: str) -> List[dict]:
    warnings = []
    budgets = get_all_budgets(year_month)
    totals = get_month_totals(year_month)
    for cat in CATEGORIES:
        budget = budgets.get(cat, 0)
        spent = totals.get(cat, 0)
        if budget > 0:
            ratio = spent / budget
            if ratio >= 1.0:
                warnings.append({"category": cat, "level": "over", "ratio": ratio, "spent": spent, "budget": budget})
            elif ratio >= 0.8:
                warnings.append({"category": cat, "level": "warn", "ratio": ratio, "spent": spent, "budget": budget})
    return warnings


@st.cache_data(ttl=60)
def get_over_expenses(year_month: str) -> List[dict]:
    result = []
    budgets = get_all_budgets(year_month)
    totals = get_month_totals(year_month)
    with get_connection() as conn:
        cursor = conn.cursor()
        for cat in CATEGORIES:
            budget = budgets.get(cat, 0)
            spent = totals.get(cat, 0)
            if budget > 0 and spent >= budget:
                cursor.execute(
                    "SELECT * FROM expenses WHERE category = ? AND strftime('%Y-%m', expense_date) = ? ORDER BY expense_date DESC",
                    (cat, year_month),
                )
                for row in cursor.fetchall():
                    result.append(dict(row))
    return result


@st.cache_data(ttl=60)
def get_over_expenses_with_cumulative(year_month: str) -> List[dict]:
    result = []
    budgets = get_all_budgets(year_month)
    totals = get_month_totals(year_month)
    with get_connection() as conn:
        cursor = conn.cursor()
        for cat in CATEGORIES:
            budget = budgets.get(cat, 0)
            spent = totals.get(cat, 0)
            if budget > 0 and spent >= budget:
                cursor.execute(
                    "SELECT * FROM expenses WHERE category = ? AND strftime('%Y-%m', expense_date) = ? ORDER BY expense_date ASC, id ASC",
                    (cat, year_month),
                )
                rows = cursor.fetchall()
                cumulative = 0.0
                over_start_idx = None
                for idx, row in enumerate(rows):
                    row_dict = dict(row)
                    cumulative += row_dict["amount_base"]
                    row_dict["cumulative"] = round(cumulative, 2)
                    row_dict["budget"] = budget
                    row_dict["over_amount"] = round(max(0, cumulative - budget), 2)
                    if over_start_idx is None and cumulative > budget:
                        over_start_idx = idx
                    if over_start_idx is not None and idx >= over_start_idx:
                        row_dict["is_over"] = True
                        row_dict["over_sequence"] = idx - over_start_idx + 1
                    else:
                        row_dict["is_over"] = False
                        row_dict["over_sequence"] = 0
                    result.append(row_dict)
    result.sort(key=lambda x: (x["category"], x["expense_date"], x["id"]), reverse=False)
    return result


@st.cache_data(ttl=60)
def get_last_six_months() -> List[str]:
    today = date.today()
    months = []
    for i in range(5, -1, -1):
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        d = date(year, month, 1)
        months.append(get_year_month(d))
    return months


@st.cache_data(ttl=60)
def get_trend_data(months: List[str]) -> dict:
    data = {m: 0.0 for m in months}
    with get_connection() as conn:
        cursor = conn.cursor()
        for ym in months:
            cursor.execute(
                "SELECT COALESCE(SUM(amount_base), 0) as total FROM expenses WHERE strftime('%Y-%m', expense_date) = ?",
                (ym,),
            )
            row = cursor.fetchone()
            data[ym] = row["total"] if row else 0.0
    return data


@st.cache_data(ttl=60)
def get_all_expenses(start_date: str = None, end_date: str = None, category: str = None) -> List[dict]:
    query = "SELECT * FROM expenses WHERE 1=1"
    params = []
    if start_date:
        query += " AND expense_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND expense_date <= ?"
        params.append(end_date)
    if category and category != "全部":
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY expense_date DESC"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def check_and_clear_prev_month_budget():
    today = date.today()
    if today.day != 1:
        return
    ym = get_year_month(today)
    prev = today.replace(day=1)
    if prev.month == 1:
        prev = prev.replace(year=prev.year - 1, month=12)
    else:
        prev = prev.replace(month=prev.month - 1)
    prev_ym = get_year_month(prev)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key FROM system_info WHERE key = ?", (f"cleared_{prev_ym}",))
        if cursor.fetchone():
            return
        totals = get_month_totals(prev_ym)
        budgets = get_all_budgets(prev_ym)
        cursor.execute(
            "INSERT OR IGNORE INTO system_info (key, value) VALUES (?, ?)",
            (f"cleared_{prev_ym}", datetime.now().isoformat()),
        )
        conn.commit()


@st.cache_data(ttl=60)
def get_expense_by_id(expense_id: int) -> Optional[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_expense(
    expense_id: int,
    amount: float,
    currency: str,
    category: str,
    expense_date: str,
    note: Optional[str] = None,
) -> Tuple[bool, str]:
    existing = get_expense_by_id(expense_id)
    if not existing:
        return False, "记录不存在。"

    amount_base = convert_to_base(amount, currency, expense_date)

    old_ym = get_year_month(datetime.strptime(existing["expense_date"], "%Y-%m-%d").date())
    new_ym = get_year_month(datetime.strptime(expense_date, "%Y-%m-%d").date())
    affected_yms = set([old_ym, new_ym])
    affected_cats = set([existing["category"], category])

    for ym in affected_yms:
        for cat in affected_cats:
            budget = get_budget(cat, ym)
            if budget > 0:
                current_total = get_category_month_total(cat, ym)
                new_total = current_total
                if existing["expense_date"].startswith(ym) and existing["category"] == cat:
                    new_total -= existing["amount_base"]
                if expense_date.startswith(ym) and category == cat:
                    new_total += amount_base
                if new_total > budget:
                    return False, f"修改后【{cat}】{ym} 分类将超预算（预算：{budget}，修改后消费：{new_total:.2f}），请先调高预算。"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE expenses
            SET amount = ?, currency = ?, amount_base = ?, category = ?, expense_date = ?, note = ?
            WHERE id = ?
            """,
            (amount, currency, amount_base, category, expense_date, note, expense_id),
        )
        conn.commit()
    st.cache_data.clear()
    return True, "修改成功。"


@st.cache_data(ttl=60)
def get_trend_data_by_category(months: List[str], categories: List[str]) -> dict:
    data = {}
    for cat in categories:
        data[cat] = {m: 0.0 for m in months}
    with get_connection() as conn:
        cursor = conn.cursor()
        for ym in months:
            cursor.execute(
                "SELECT category, COALESCE(SUM(amount_base), 0) as total FROM expenses WHERE strftime('%Y-%m', expense_date) = ? AND category IN ({}) GROUP BY category".format(
                    ",".join("?" * len(categories))
                ),
                (ym, *categories),
            )
            for row in cursor.fetchall():
                data[row["category"]][ym] = row["total"]
    return data


def generate_month_range(start_ym: str, end_ym: str) -> List[str]:
    start = datetime.strptime(start_ym, "%Y-%m")
    end = datetime.strptime(end_ym, "%Y-%m")
    months = []
    current = start
    while current <= end:
        months.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def validate_year_or_range(year: Optional[str] = None, start_ym: Optional[str] = None, end_ym: Optional[str] = None) -> Tuple[bool, str, Optional[str], Optional[str]]:
    if year:
        s = f"{year}-01"
        e = f"{year}-12"
        try:
            datetime.strptime(s, "%Y-%m")
            datetime.strptime(e, "%Y-%m")
        except ValueError:
            return False, "年份格式错误", None, None
        return True, "", s, e
    else:
        if not start_ym or not end_ym:
            return False, "必须指定年份，或同时指定起始月份与结束月份", None, None
        try:
            datetime.strptime(start_ym, "%Y-%m")
            datetime.strptime(end_ym, "%Y-%m")
        except ValueError:
            return False, "月份格式必须为 YYYY-MM，例如 2025-01", None, None
        if start_ym > end_ym:
            return False, f"起始月份 {start_ym} 不能晚于结束月份 {end_ym}", None, None
        return True, "", start_ym, end_ym


@st.cache_data(ttl=60)
def query_monthly_expenses_for_range(months: List[str]) -> Dict[str, Dict[str, float]]:
    result = {}
    for ym in months:
        result[ym] = {c: 0.0 for c in CATEGORIES}
    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(months))
        cursor.execute(
            f"SELECT category, strftime('%Y-%m', expense_date) as ym, "
            f"COALESCE(SUM(amount_base), 0) as total "
            f"FROM expenses "
            f"WHERE strftime('%Y-%m', expense_date) IN ({placeholders}) "
            f"GROUP BY category, ym",
            months,
        )
        for row in cursor.fetchall():
            cat = row["category"]
            ym = row["ym"]
            if cat in CATEGORIES and ym in result:
                result[ym][cat] = row["total"]
    return result


@st.cache_data(ttl=60)
def query_monthly_budgets_for_range(months: List[str]) -> Tuple[Dict[str, Dict[str, float]], List[Dict[str, Any]], set]:
    result = {}
    recorded_months = set()
    missing_details = {}
    for ym in months:
        result[ym] = {c: 0.0 for c in CATEGORIES}
        missing_details[ym] = set(CATEGORIES)
    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(months))
        cursor.execute(
            f"SELECT category, year_month, amount "
            f"FROM budgets "
            f"WHERE year_month IN ({placeholders})",
            months,
        )
        for row in cursor.fetchall():
            cat = row["category"]
            ym = row["year_month"]
            if ym in result:
                recorded_months.add(ym)
                if cat in CATEGORIES:
                    result[ym][cat] = row["amount"]
                    missing_details[ym].discard(cat)
    warnings = []
    for ym in months:
        if ym not in recorded_months:
            warnings.append({"month": ym, "scope": "全部", "missing_categories": sorted(CATEGORIES)})
        else:
            if missing_details[ym]:
                warnings.append({"month": ym, "scope": "部分", "missing_categories": sorted(missing_details[ym])})
    return result, warnings, recorded_months


def build_category_rows(months: List[str], expenses: Dict[str, Dict[str, float]], budgets: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    rows = []
    for ym in months:
        row = {"月份": ym}
        for cat in CATEGORIES:
            row[f"{cat}_实际"] = round(expenses[ym][cat], 2)
            row[f"{cat}_预算"] = round(budgets[ym][cat], 2)
        rows.append(row)
    return rows


def build_summary_rows(months: List[str], expenses: Dict[str, Dict[str, float]], budgets: Dict[str, Dict[str, float]], recorded_months: set) -> List[Dict[str, Any]]:
    rows = []
    for ym in months:
        total_expense = sum(expenses[ym].values())
        total_budget = sum(budgets[ym].values())
        if ym not in recorded_months:
            execution_rate = "-"
        else:
            execution_rate = round((total_expense / total_budget * 100), 2) if total_budget > 0 else 0.0
        rows.append({
            "月份": ym,
            "总支出": round(total_expense, 2),
            "总预算": round(total_budget, 2),
            "执行率(%)": execution_rate,
        })
    return rows


def find_overexpense_months(summary_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    over = []
    for r in summary_rows:
        total_budget = r["总预算"]
        if isinstance(r["执行率(%)"], (int, float)) and total_budget > 0 and r["总支出"] > total_budget:
            over.append({
                "月份": r["月份"],
                "超支金额": round(r["总支出"] - total_budget, 2),
                "总支出": r["总支出"],
                "总预算": total_budget,
            })
    over.sort(key=lambda x: (-x["超支金额"], x["月份"]))
    return over


def get_category_fields() -> List[str]:
    fields = ["月份"]
    for cat in CATEGORIES:
        fields.append(f"{cat}_实际")
        fields.append(f"{cat}_预算")
    return fields


def get_summary_fields() -> List[str]:
    return ["月份", "总支出", "总预算", "执行率(%)"]


def get_overexpense_fields() -> List[str]:
    return ["月份", "总支出", "总预算", "超支金额"]


def write_csv_to_string(rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def get_yearly_summary_data(year: Optional[str] = None, start_ym: Optional[str] = None, end_ym: Optional[str] = None) -> Dict[str, Any]:
    ok, msg, s, e = validate_year_or_range(year, start_ym, end_ym)
    if not ok:
        return {"success": False, "error": msg}
    months = generate_month_range(s, e)
    expenses = query_monthly_expenses_for_range(months)
    budgets, budget_warnings, recorded_months = query_monthly_budgets_for_range(months)
    category_rows = build_category_rows(months, expenses, budgets)
    summary_rows = build_summary_rows(months, expenses, budgets, recorded_months)
    overexpense_months = find_overexpense_months(summary_rows)

    warning_messages = []
    for w in budget_warnings:
        if w["scope"] == "全部":
            warning_messages.append(f"月份 {w['month']} 缺少所有分类的预算记录，预算列按 0 处理。")
        else:
            warning_messages.append(f"月份 {w['month']} 缺少分类预算记录（{'、'.join(w['missing_categories'])}），对应分类预算列按 0 处理。")

    category_fields = get_category_fields()
    summary_fields = get_summary_fields()
    category_csv = write_csv_to_string(category_rows, category_fields)
    summary_csv = write_csv_to_string(summary_rows, summary_fields)

    return {
        "success": True,
        "start_ym": s,
        "end_ym": e,
        "months": months,
        "category_rows": category_rows,
        "summary_rows": summary_rows,
        "overexpense_months": overexpense_months,
        "warning_messages": warning_messages,
        "category_fields": category_fields,
        "summary_fields": summary_fields,
        "category_csv": category_csv,
        "summary_csv": summary_csv,
    }
