# Financial Ledger Transaction Processor

A local financial transaction pipeline built with Python, PostgreSQL, Docker Compose, and MinIO.

## Architecture

- PostgreSQL is the operational database for account balances and ledger history.
- PostgreSQL constraints enforce database-level data integrity.
- `processor.py` reads a transaction CSV and processes each row in an explicit database transaction.
- MinIO stores the original processed CSV in a Hive-style partition path.

## ACID Design

Each input transaction follows this sequence:

1. Begin a database transaction.
2. Deduct the transfer amount from the sender account.
3. Add the transfer amount to the receiver account.
4. Insert a `SUCCESS` ledger record.
5. Commit the transaction.

If any database constraint or validation fails:

1. Roll back the transaction.
2. Insert a separate `FAILED` ledger record.
3. Commit the failure log.

The `accounts.balance` constraint prevents negative balances. Foreign keys prevent transfers involving nonexistent accounts. Therefore, failed transfers cannot partially change balances.

## Prerequisites

- Docker Desktop running
- Python 3.10 or later
- VS Code with the Python extension recommended

## Setup

Copy the environment template:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and choose a local password for `DB_PASSWORD`.

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Start PostgreSQL and MinIO:

```powershell
docker compose up -d
docker compose ps
```

Wait until PostgreSQL reports healthy. The first startup runs the SQL files in `db_init/`.

## Run the Processor

Process the included sample file:

```powershell
python processor.py
```

Or provide a custom CSV path:

```powershell
python processor.py .\data\pending_transactions.csv
```

The required CSV columns are:

```text
tx_id,from_account,to_account,amount
```

## Verify PostgreSQL

View account balances:

```powershell
docker compose exec postgres psql -U ledger_admin -d financial_ledger -c "SELECT * FROM accounts ORDER BY account_id;"
```

View transaction results:

```powershell
docker compose exec postgres psql -U ledger_admin -d financial_ledger -c "SELECT tx_id, from_account_id, to_account_id, amount, status, processed_at FROM ledger_transactions ORDER BY processed_at;"
```

## Verify MinIO

Open the MinIO Console:

```text
http://localhost:9001
```

Sign in using `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from `.env`. Open the `ledger-archive` bucket and inspect the object path:

```text
processed/year=YYYY/month=MM/day=DD/<your-file>.csv
```

## Reset the Local Environment

PostgreSQL initialization SQL runs only when its data volume is created for the first time. To reset all local data and rerun initialization:

```powershell
docker compose down -v
docker compose up -d
```

## Stop Services

```powershell
docker compose down
```
