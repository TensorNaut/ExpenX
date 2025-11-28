-- migrations/0002_investment_settlements_add_account_principal.sql
PRAGMA foreign_keys = OFF;
BEGIN;

ALTER TABLE investment_settlements ADD COLUMN account_id INTEGER;
ALTER TABLE investment_settlements ADD COLUMN principal_reduced REAL DEFAULT 0.0;

COMMIT;
