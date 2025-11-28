-- migrations/0001_init_accounts_kind_and_defaults.sql
-- Safe operations: add column if missing, update default accounts values
PRAGMA foreign_keys = OFF;

BEGIN;

-- Add column 'kind' if not exists (SQLite will error if we try to add an existing column; runner checks first)
ALTER TABLE accounts ADD COLUMN kind TEXT DEFAULT 'bank';

-- Add column 'currency' if not exists (in case older table used currency column wrongly)
ALTER TABLE accounts ADD COLUMN currency TEXT DEFAULT 'INR';

-- Ensure default accounts exist (insert only if not present)
INSERT INTO accounts(name, currency, balance, kind)
SELECT 'Main', 'INR', 0.0, 'bank'
WHERE NOT EXISTS(SELECT 1 FROM accounts WHERE LOWER(name)='main');

INSERT INTO accounts(name, currency, balance, kind)
SELECT 'Cash', 'INR', 0.0, 'cash'
WHERE NOT EXISTS(SELECT 1 FROM accounts WHERE LOWER(name)='cash');

INSERT INTO accounts(name, currency, balance, kind)
SELECT 'Credit Card', 'INR', 0.0, 'card'
WHERE NOT EXISTS(SELECT 1 FROM accounts WHERE LOWER(name) LIKE '%card%');

-- Fix rows that incorrectly had kind stored in currency column
UPDATE accounts
SET kind = currency
WHERE kind IS NULL AND LOWER(IFNULL(currency,'')) IN ('bank','cash','card');

-- For the specific known accounts, set canonical kinds
UPDATE accounts SET kind='bank' WHERE LOWER(name)='main';
UPDATE accounts SET kind='cash' WHERE LOWER(name)='cash';
UPDATE accounts SET kind='card' WHERE LOWER(name) LIKE '%card%';

COMMIT;
