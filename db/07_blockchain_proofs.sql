-- ==============================================================================
-- TradeShield * 07_blockchain_proofs.sql
--
-- MOCK blockchain integrity layer.
--
-- PostgreSQL remains the system of record for all trading and application data.
-- This table stores MOCK proof metadata only -- it is NOT a real blockchain, does
-- NOT contain real transactions, and does NOT replace any existing table.
--
-- What is stored here (mock/demo only):
--   - proof_id
--   - reference_id        ( TradeShield event reference, e.g. order_id/execution_id/event_id )
--   - entity_type         ( the kind of TradeShield entity the proof anchors )
--   - event_type          ( e.g. TRADE_EXECUTED, ORDER_BLOCKED )
--   - record_hash         ( MOCK 64-char hex, looks like a SHA-256 digest )
--   - blockchain_status   ( anchored | pending | verification_failed )
--   - transaction_hash    ( MOCK 64-char hex, looks like a tx hash )
--   - block_number        ( MOCK integer, looks like a block number )
--   - network             ( MOCK network identifier )
--   - contract_address    ( MOCK 0x... address )
--   - created_at          ( when the mock proof record was created )
--
-- What is NOT stored here:
--   passwords, JWTs, balances, full financial records, or personal data.
-- ============================================================================

CREATE TABLE IF NOT EXISTS blockchain_proofs (
    proof_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reference_id      VARCHAR(128) NOT NULL,
    entity_type       VARCHAR(32)  NOT NULL,
    event_type        VARCHAR(64)  NOT NULL,
    record_hash       VARCHAR(64)  NOT NULL,
    blockchain_status VARCHAR(32)  NOT NULL DEFAULT 'anchored'
                       CHECK (blockchain_status IN ('anchored','pending','verification_failed','mock')),
    transaction_hash  VARCHAR(64)  NOT NULL,
    block_number      INTEGER      NOT NULL,
    network           VARCHAR(128) NOT NULL,
    contract_address  VARCHAR(42)  NOT NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    -- Optional trade context for demo-flagged-trade proofs so the admin UI
    -- can show the actual instrument / side / quantity / order without
    -- changing the core mock proof contract. Nullable: only populated for
    -- demo FLAG proofs that correspond to a real order.
    order_id          UUID,
    execution_id      UUID,
    instrument_id     UUID,
    side              VARCHAR(4),
    quantity          NUMERIC(18,6),
    CONSTRAINT uq_proof_reference_entity
        UNIQUE (reference_id, entity_type)
);

COMMENT ON TABLE blockchain_proofs IS
' MOCK blockchain integrity metadata for demonstration only.
  NOT a real blockchain, NOT real transactions, NOT a replacement for any TradeShield table.
  trade-context columns (order_id, execution_id, instrument_id, side, quantity) are
  populated only for demo FLAG proofs that correspond to a real order -- they are NOT
  stored for seed or other mock proofs, and never for real (non-demo) events.';
