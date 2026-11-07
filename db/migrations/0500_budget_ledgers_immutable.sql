-- Budget ledgers are content-addressed (ledger_id = sha256 of the sealed ledger) and never change.
ALTER TABLE budget_ledgers
  ADD CONSTRAINT budget_ledgers_id_is_hash CHECK (ledger_id = content_hash);
CREATE TRIGGER budget_ledgers_append_only BEFORE UPDATE OR DELETE ON budget_ledgers
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
