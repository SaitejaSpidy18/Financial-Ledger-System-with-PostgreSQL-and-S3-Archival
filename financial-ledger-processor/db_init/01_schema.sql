CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY,
    account_name VARCHAR(100) NOT NULL,
    balance NUMERIC(15, 2) NOT NULL CHECK (balance >= 0)
);

CREATE TABLE IF NOT EXISTS ledger_transactions (
    tx_id VARCHAR(100) PRIMARY KEY,
    from_account_id INTEGER NOT NULL,
    to_account_id INTEGER NOT NULL,
    amount NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
    status VARCHAR(20) NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
    processed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_ledger_from_account
        FOREIGN KEY (from_account_id)
        REFERENCES accounts(account_id),

    CONSTRAINT fk_ledger_to_account
        FOREIGN KEY (to_account_id)
        REFERENCES accounts(account_id),

    CONSTRAINT different_accounts
        CHECK (from_account_id <> to_account_id)
);
