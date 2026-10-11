"""Validate a complete CSV before touching the current dataset."""

import csv
import io
import re
from decimal import Decimal, InvalidOperation

from app.dbtypes import MAX_AMOUNT, QUANTUM
from app.engine.matcher import _parse_dt

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10_000


class CSVValidationError(ValueError):
    pass


def parse_csv(content: bytes, *, ledger: bool) -> list[dict]:
    if len(content) > MAX_BYTES:
        raise CSVValidationError("File exceeds the 10 MiB limit")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVValidationError("File must be UTF-8 encoded CSV") from exc
    if "\0" in decoded:
        raise CSVValidationError("CSV must not contain NUL characters")
    required = {"transaction_id", "amount", "timestamp"}
    if ledger:
        required |= {"account_id", "currency"}
    reader = csv.DictReader(io.StringIO(decoded), strict=True)
    try:
        headers = reader.fieldnames or []
        missing = required - set(headers)
        if missing:
            raise CSVValidationError("Missing required columns: " + ", ".join(sorted(missing)))
        if len(headers) != len(set(headers)):
            raise CSVValidationError("Duplicate column names are not allowed")
        rows = []
        for row in reader:
            line = reader.line_num
            try:
                if None in row or any(row.get(key) is None for key in required):
                    raise ValueError("row has a different number of values than the header")
                item = {key: (value or "").strip() for key, value in row.items()}
                if not item["transaction_id"] or len(item["transaction_id"]) > 120:
                    raise ValueError("transaction_id must contain 1 to 120 characters")
                amount = Decimal(item["amount"])
                if (
                    not amount.is_finite()
                    or abs(amount) > MAX_AMOUNT
                    or amount != amount.quantize(QUANTUM)
                ):
                    raise ValueError(
                        "amount must be finite, with at most 14 integer digits and 4 decimal places"
                    )
                item["amount"] = amount
                item["timestamp"] = _parse_dt(item["timestamp"])
                item["description"] = item.get("description", "")
                if len(item["description"]) > 2000:
                    raise ValueError("description exceeds 2000 characters")
                if ledger:
                    if not item["account_id"] or len(item["account_id"]) > 120:
                        raise ValueError("account_id must contain 1 to 120 characters")
                    item["currency"] = item["currency"].upper()
                    if not re.fullmatch(r"[A-Z]{3}", item["currency"]):
                        raise ValueError("currency must contain three letters, such as USD or EUR")
                    item["status"] = item.get("status") or "settled"
                    if len(item["status"]) > 50:
                        raise ValueError("status exceeds 50 characters")
                fields = required | {"description"} | ({"status"} if ledger else set())
                rows.append({key: item[key] for key in fields})
            except (ValueError, InvalidOperation) as exc:
                raise CSVValidationError(f"CSV line {line}: {exc}") from exc
            if len(rows) > MAX_ROWS:
                raise CSVValidationError(f"CSV exceeds the {MAX_ROWS:,} row limit")
        if not rows:
            raise CSVValidationError("CSV must contain at least one transaction")
        return rows
    except csv.Error as exc:
        raise CSVValidationError(f"Invalid CSV near line {reader.line_num}: {exc}") from exc
