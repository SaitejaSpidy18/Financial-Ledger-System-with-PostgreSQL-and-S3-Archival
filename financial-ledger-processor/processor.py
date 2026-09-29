import argparse
import csv
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import boto3
import psycopg2
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from psycopg2 import Error as DatabaseError


load_dotenv()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_db_connection():
    return psycopg2.connect(
        host=required_env("DB_HOST"),
        port=required_env("DB_PORT"),
        user=required_env("DB_USER"),
        password=required_env("DB_PASSWORD"),
        dbname=required_env("DB_NAME"),
    )


def transaction_exists(connection, tx_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM ledger_transactions WHERE tx_id = %s",
            (tx_id,),
        )
        return cursor.fetchone() is not None


def log_failed_transaction(connection, row: dict, reason: str) -> None:
    try:
        amount = Decimal(row["amount"])
    except (InvalidOperation, KeyError):
        amount = Decimal("0.01")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ledger_transactions
                (tx_id, from_account_id, to_account_id, amount, status)
            VALUES
                (%s, %s, %s, %s, 'FAILED')
            ON CONFLICT (tx_id) DO NOTHING
            """,
            (
                row.get("tx_id"),
                row.get("from_account"),
                row.get("to_account"),
                amount,
            ),
        )
    connection.commit()
    print(f"FAILED: {row.get('tx_id')} - {reason}")


def process_row(connection, row: dict) -> None:
    tx_id = row["tx_id"].strip()
    from_account = int(row["from_account"])
    to_account = int(row["to_account"])
    amount = Decimal(row["amount"])

    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    if from_account == to_account:
        raise ValueError("Sender and receiver must be different accounts.")

    if transaction_exists(connection, tx_id):
        print(f"SKIPPED: {tx_id} already exists.")
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")

            cursor.execute(
                """
                UPDATE accounts
                SET balance = balance - %s
                WHERE account_id = %s
                """,
                (amount, from_account),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Sender account {from_account} does not exist.")

            cursor.execute(
                """
                UPDATE accounts
                SET balance = balance + %s
                WHERE account_id = %s
                """,
                (amount, to_account),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Receiver account {to_account} does not exist.")

            cursor.execute(
                """
                INSERT INTO ledger_transactions
                    (tx_id, from_account_id, to_account_id, amount, status)
                VALUES
                    (%s, %s, %s, %s, 'SUCCESS')
                """,
                (tx_id, from_account, to_account, amount),
            )

        connection.commit()
        print(f"SUCCESS: {tx_id}")

    except (DatabaseError, ValueError) as error:
        connection.rollback()
        log_failed_transaction(connection, row, str(error))


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=required_env("AWS_ENDPOINT_URL"),
        aws_access_key_id=required_env("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=required_env("AWS_SECRET_ACCESS_KEY"),
        region_name="us-east-1",
    )


def ensure_bucket_exists(s3_client, bucket_name: str) -> None:
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError:
        s3_client.create_bucket(Bucket=bucket_name)
        print(f"Created bucket: {bucket_name}")


def archive_csv(csv_path: Path) -> str:
    s3_client = get_s3_client()
    bucket_name = required_env("S3_BUCKET_NAME")
    ensure_bucket_exists(s3_client, bucket_name)

    run_date = datetime.now()
    object_key = (
        f"processed/year={run_date:%Y}/month={run_date:%m}/"
        f"day={run_date:%d}/{csv_path.name}"
    )

    s3_client.upload_file(str(csv_path), bucket_name, object_key)
    print(f"Archived: s3://{bucket_name}/{object_key}")
    return object_key


def validate_headers(csv_path: Path) -> None:
    required_columns = {"tx_id", "from_account", "to_account", "amount"}

    with csv_path.open(mode="r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("CSV must contain a header row.")

        missing_columns = required_columns - set(reader.fieldnames)
        if missing_columns:
            raise ValueError(
                f"CSV is missing required columns: {', '.join(sorted(missing_columns))}"
            )


def process_csv(csv_path: Path) -> None:
    validate_headers(csv_path)

    connection = get_db_connection()
    try:
        with csv_path.open(mode="r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row in reader:
                try:
                    process_row(connection, row)
                except (ValueError, KeyError, InvalidOperation) as error:
                    connection.rollback()
                    try:
                        log_failed_transaction(connection, row, str(error))
                    except DatabaseError as log_error:
                        connection.rollback()
                        print(
                            f"Could not record failure for {row.get('tx_id')}: {log_error}",
                            file=sys.stderr,
                        )
    finally:
        connection.close()

    archive_csv(csv_path)


def main():
    parser = argparse.ArgumentParser(
        description="Process a financial transaction CSV and archive it to MinIO."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="data/pending_transactions.csv",
        help="Path to CSV with tx_id, from_account, to_account, amount columns.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    process_csv(csv_path)


if __name__ == "__main__":
    main()
