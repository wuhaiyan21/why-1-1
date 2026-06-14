from db import get_connection, BASE_CURRENCY

CURRENCIES = {
    "CNY": "人民币",
    "USD": "美元",
    "EUR": "欧元",
    "JPY": "日元",
    "GBP": "英镑",
    "HKD": "港币",
    "KRW": "韩元",
    "SGD": "新加坡元",
    "AUD": "澳元",
    "CAD": "加元",
    "CHF": "瑞士法郎",
    "THB": "泰铢",
}

DEFAULT_RATES = {
    "CNY": 1.0,
    "USD": 7.25,
    "EUR": 7.85,
    "JPY": 0.048,
    "GBP": 9.15,
    "HKD": 0.93,
    "KRW": 0.0053,
    "SGD": 5.35,
    "AUD": 4.75,
    "CAD": 5.30,
    "CHF": 8.20,
    "THB": 0.20,
}


def seed_exchange_rates():
    with get_connection() as conn:
        cursor = conn.cursor()
        for currency, rate in DEFAULT_RATES.items():
            cursor.execute(
                """
                INSERT OR IGNORE INTO exchange_rates (currency, rate_date, rate_to_base)
                VALUES (?, 'default', ?)
                """,
                (currency, rate),
            )
        conn.commit()


def get_rate(currency: str, rate_date: str = None) -> float:
    with get_connection() as conn:
        cursor = conn.cursor()
        if rate_date:
            cursor.execute(
                "SELECT rate_to_base FROM exchange_rates WHERE currency = ? AND rate_date = ?",
                (currency, rate_date),
            )
            row = cursor.fetchone()
            if row:
                return row["rate_to_base"]
        cursor.execute(
            "SELECT rate_to_base FROM exchange_rates WHERE currency = ? AND rate_date = 'default'",
            (currency,),
        )
        row = cursor.fetchone()
        if row:
            return row["rate_to_base"]
        return DEFAULT_RATES.get(currency, 1.0)


def convert_to_base(amount: float, currency: str, rate_date: str = None) -> float:
    if currency == BASE_CURRENCY:
        return amount
    rate = get_rate(currency, rate_date)
    return round(amount * rate, 2)
