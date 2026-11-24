"""Загрузка одной согласованной пары таблиц для дашборда и анализа."""

from pathlib import Path

import pandas as pd

from src.data.generator import generate
from src.data.validation import validate

ORDERS_CSV = "orders.csv"
ATTEMPTS_CSV = "payment_attempts.csv"


def csv_versions(data_dir: Path) -> tuple[tuple[int, int] | None, ...]:
    """Меняет ключ кеша при появлении, удалении или обновлении любого CSV."""
    versions = []
    for name in (ORDERS_CSV, ATTEMPTS_CSV):
        try:
            info = (data_dir / name).stat()
        except FileNotFoundError:
            versions.append(None)
        else:
            versions.append((info.st_mtime_ns, info.st_size))
    return tuple(versions)


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    orders_path = data_dir / ORDERS_CSV
    attempts_path = data_dir / ATTEMPTS_CSV
    orders_exist, attempts_exist = orders_path.exists(), attempts_path.exists()
    if orders_exist != attempts_exist:
        missing = attempts_path if orders_exist else orders_path
        raise ValueError(f"Для загрузки CSV нужны обе таблицы. Отсутствует {missing.name}.")
    if orders_exist:
        orders = pd.read_csv(orders_path, parse_dates=["created_at"])
        attempts = pd.read_csv(attempts_path, parse_dates=["created_at"])
    else:
        orders, attempts = generate()

    validate(orders, attempts)
    return orders, attempts
