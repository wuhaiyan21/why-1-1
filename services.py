from datetime import datetime, date
from typing import Optional, Tuple, List

from db import get_connection, CATEGORIES
from exchange_rates import convert_to_base


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
    return True, "录入成功。"


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


def get_category_month_total(category: str, year_month: str) -> float:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(amount_base), 0) as total FROM expenses WHERE category = ? AND strftime('%Y-%m', expense_date) = ?",
            (category, year_month),
        )
        row = cursor.fetchone()
        return row["total"] if row else 0.0


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
