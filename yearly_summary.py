#!/usr/bin/env python3
import argparse
import csv
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime

CATEGORIES = ["餐饮", "交通", "娱乐", "住房", "其他"]


@contextmanager
def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def generate_month_range(start_ym, end_ym):
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


def resolve_year_or_range(args):
    if args.year:
        start_ym = f"{args.year}-01"
        end_ym = f"{args.year}-12"
    else:
        if not args.start or not args.end:
            print("错误：必须指定 --year，或同时指定 --start 和 --end", file=sys.stderr)
            sys.exit(1)
        start_ym = args.start
        end_ym = args.end
    try:
        datetime.strptime(start_ym, "%Y-%m")
        datetime.strptime(end_ym, "%Y-%m")
    except ValueError:
        print("错误：月份格式必须为 YYYY-MM，例如 2025-01", file=sys.stderr)
        sys.exit(1)
    if start_ym > end_ym:
        print("错误：起始月份不能晚于结束月份", file=sys.stderr)
        sys.exit(1)
    return start_ym, end_ym


def query_monthly_expenses(conn, months):
    result = {}
    for ym in months:
        result[ym] = {c: 0.0 for c in CATEGORIES}
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


def query_monthly_budgets(conn, months):
    result = {}
    recorded_months = set()
    missing_details = {}
    for ym in months:
        result[ym] = {c: 0.0 for c in CATEGORIES}
        missing_details[ym] = set(CATEGORIES)
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
            warnings.append((ym, "全部", sorted(CATEGORIES)))
        else:
            if missing_details[ym]:
                warnings.append((ym, "部分", sorted(missing_details[ym])))
    return result, warnings, recorded_months


def build_category_rows(months, expenses, budgets):
    rows = []
    for ym in months:
        row = {"月份": ym}
        for cat in CATEGORIES:
            row[f"{cat}_实际"] = round(expenses[ym][cat], 2)
            row[f"{cat}_预算"] = round(budgets[ym][cat], 2)
        rows.append(row)
    return rows


def build_summary_rows(months, expenses, budgets, recorded_months):
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


def find_overexpense_months(summary_rows):
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


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows, fieldnames):
    header = "| " + " | ".join(fieldnames) + " |"
    sep = "| " + " | ".join(["---"] * len(fieldnames)) + " |"
    lines = [header, sep]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(fn, "")) for fn in fieldnames) + " |")
    return "\n".join(lines)


def write_category_markdown(path, category_rows, category_fields):
    parts = []
    parts.append("# 各月各分类支出与预算\n")
    parts.append(markdown_table(category_rows, category_fields))
    parts.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def write_summary_markdown(path, summary_rows, over_months, summary_fields):
    parts = []
    parts.append("# 各月总支出、总预算与执行率\n")
    parts.append(markdown_table(summary_rows, summary_fields))
    parts.append("")
    parts.append("## 超支月份清单\n")
    if over_months:
        over_fields = ["月份", "总支出", "总预算", "超支金额"]
        over_table_rows = []
        for om in over_months:
            over_table_rows.append({
                "月份": om["月份"],
                "总支出": om["总支出"],
                "总预算": om["总预算"],
                "超支金额": om["超支金额"],
            })
        parts.append(markdown_table(over_table_rows, over_fields))
        parts.append("")
        parts.append("> 排序规则：超支金额从大到小，金额相同按月份先后。")
    else:
        parts.append("_查询范围内无超支月份。_")
    parts.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def main():
    parser = argparse.ArgumentParser(
        description="家庭开支年度汇总工具：输出按月、按分类的实际支出与预算执行情况，支持 CSV 与 Markdown 格式。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  # 生成 2025 全年汇总（CSV）
  python yearly_summary.py --year 2025

  # 生成指定区间汇总（Markdown 表格）
  python yearly_summary.py --start 2025-01 --end 2025-06 --format markdown

  # 指定数据库路径与输出目录
  python yearly_summary.py --year 2025 --db ./data/expenses.db --output-dir ./output
        """,
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--year",
        type=str,
        help="指定完整年份（如 2025），等价于 --start YYYY-01 --end YYYY-12",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="起始月份，格式 YYYY-MM（如 2025-01），需与 --end 搭配使用",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="结束月份，格式 YYYY-MM（如 2025-12），需与 --start 搭配使用",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "expenses.db"),
        help="SQLite 数据库文件路径（默认：./data/expenses.db）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.getcwd(),
        help="输出目录（默认：当前目录）",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["csv", "markdown"],
        default="csv",
        help="输出格式：csv（默认）或 markdown",
    )

    args = parser.parse_args()

    if not args.year and (not args.start or not args.end):
        parser.error("必须指定 --year，或同时指定 --start 与 --end")

    start_ym, end_ym = resolve_year_or_range(args)
    months = generate_month_range(start_ym, end_ym)

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"错误：数据库文件不存在：{db_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    with get_connection(db_path) as conn:
        expenses = query_monthly_expenses(conn, months)
        budgets, budget_warnings, recorded_months = query_monthly_budgets(conn, months)

    for ym, scope, missing_cats in budget_warnings:
        if scope == "全部":
            print(f"警告：月份 {ym} 缺少所有分类的预算记录，预算列按 0 处理。", file=sys.stderr)
        else:
            print(
                f"警告：月份 {ym} 缺少分类预算记录（{'、'.join(missing_cats)}），对应分类预算列按 0 处理。",
                file=sys.stderr,
            )

    category_rows = build_category_rows(months, expenses, budgets)
    summary_rows = build_summary_rows(months, expenses, budgets, recorded_months)

    category_fields = ["月份"]
    for cat in CATEGORIES:
        category_fields.append(f"{cat}_实际")
        category_fields.append(f"{cat}_预算")
    summary_fields = ["月份", "总支出", "总预算", "执行率(%)"]

    if args.format == "csv":
        cat_path = os.path.join(output_dir, "monthly_category_summary.csv")
        sum_path = os.path.join(output_dir, "monthly_total_summary.csv")
        write_csv(cat_path, category_rows, category_fields)
        write_csv(sum_path, summary_rows, summary_fields)
        print(f"已生成：{cat_path}")
        print(f"已生成：{sum_path}")
    else:
        over_months = find_overexpense_months(summary_rows)
        cat_path = os.path.join(output_dir, "monthly_category_summary.md")
        sum_path = os.path.join(output_dir, "monthly_total_summary.md")
        write_category_markdown(cat_path, category_rows, category_fields)
        write_summary_markdown(sum_path, summary_rows, over_months, summary_fields)
        print(f"已生成：{cat_path}")
        print(f"已生成：{sum_path}")


if __name__ == "__main__":
    main()
