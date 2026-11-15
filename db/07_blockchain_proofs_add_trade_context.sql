-- ==============================================================================
-- TradeShield * 07_blockchain_proofs_add_trade_context.sql
--
-- Idempotent additive migration: add optional trade-context columns to the
-- existing blockchain_proofs table so demo FLAG proofs can reference the real
-- order / execution / instrument / side / quantity they correspond to.
--
-- These columns are NULL for seed proofs and for any non-trade proofs; they are
-- populated only by the demo flagging path in orders.py. This is a backward-
-- compatible extension only -- it does not change the mock proof contract or any
-- existing row's hash / status / network values.
--
-- Run AFTER 07_blockchain_proofs.sql. Safe to run against an already-seeded DB.
-- ==============================================================================

ALTER TABLE blockchain_proofs
  ADD COLUMN IF NOT EXISTS order_id UUID,
  ADD COLUMN IF NOT EXISTS execution_id UUID,
  ADD COLUMN IF NOT EXISTS instrument_id UUID,
  ADD COLUMN IF NOT EXISTS side VARCHAR(4),
  ADD COLUMN IF NOT EXISTS quantity NUMERIC(18,6);
