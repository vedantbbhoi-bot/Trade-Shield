-- ============================================================================
-- TradeShield * 09_demo_flagging.sql
--
-- Additive, idempotent support for the MOCK demo trade flagging feature.
--
-- - Extends the security_events event_type CHECK with ORDER_FLAGGED_DEMO so the
--   demo can write a clearly-labelled demo security event (distinguishable from a
--   real ORDER_FLAGGED detection, which always has a matched indicator).
-- - Extends vw_blocked_orders to include ORDER_FLAGGED_DEMO so the admin
--   blocked/flagged page can display demo-flagged trades.
--
-- These changes do NOT touch any trigger (t1-t5) or the real threat-screening
-- or financial logic.
-- ============================================================================

-- --- 1. Allow ORDER_FLAGGED_DEMO in security_events.event_type --------------
-- Drop the existing event_type CHECK (if any) and re-add one that also admits
-- ORDER_FLAGGED_DEMO. PostgreSQL may store the original IN(...) as an internal
-- = ANY (...) form, so matching/replacing by definition text is fragile; the
-- drop-if-exists + re-add approach is robust and idempotent.

ALTER TABLE security_events
  DROP CONSTRAINT IF EXISTS security_events_event_type_check;

ALTER TABLE security_events
  ADD CONSTRAINT security_events_event_type_check
  CHECK (event_type IN ('ORDER_BLOCKED', 'ORDER_FLAGGED', 'ORDER_FLAGGED_DEMO',
                        'THREAT_MATCH', 'AUTH_FAILURE',
                        'THREAT_INDICATOR_CHANGED', 'ORDER_REJECTED'));

-- --- 2. Include ORDER_FLAGGED_DEMO in the blocked/flagged orders view, with proof link --------
-- Idempotent: drop the old view (if any) then recreate. Safe on a fresh or
-- already-seeded DB. The view now exposes mock_proof_reference and proof_id so
-- the admin blocked/flagged page can link each ORDER_FLAGGED_DEMO event to its
-- MOCK blockchain proof.

DROP VIEW IF EXISTS vw_blocked_orders;

CREATE VIEW vw_blocked_orders AS
SELECT e.event_id,
       e.event_type,
       e.severity,
       e.created_at           AS detected_at,
       e.account_id,
       e.order_id,
       e.indicator_id,
       i.indicator_type,
       i.value                AS indicator_value,
       i.threat_category,
       i.confidence,
       s.name                 AS source_name,
       (e.details->>'side')          AS attempted_side,
       (e.details->>'order_type')    AS attempted_order_type,
       (e.details->>'quantity')::NUMERIC      AS attempted_quantity,
       (e.details->>'limit_price')::NUMERIC   AS attempted_limit_price,
       (e.details->>'origin_ip')     AS origin_ip,
       (e.details->>'reason')        AS reason,
       (e.details->>'mock_proof_reference') AS mock_proof_reference,
       p.proof_id                      AS proof_id,
       e.details
FROM security_events e
LEFT JOIN threat_indicators i ON i.indicator_id = e.indicator_id
LEFT JOIN threat_sources s    ON s.source_id = i.source_id
LEFT JOIN blockchain_proofs p
       ON p.reference_id = e.details->>'mock_proof_reference'
      AND p.entity_type = 'order'
      AND p.event_type  = 'ORDER_FLAGGED_DEMO'
WHERE e.event_type IN ('ORDER_BLOCKED', 'ORDER_FLAGGED', 'ORDER_FLAGGED_DEMO')
ORDER BY e.created_at DESC;
