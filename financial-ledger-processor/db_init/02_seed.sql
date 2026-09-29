INSERT INTO accounts (account_id, account_name, balance)
VALUES
    (101, 'Alice', 500.00),
    (102, 'Bob', 100.00),
    (103, 'Charlie', 0.00)
ON CONFLICT (account_id) DO NOTHING;
