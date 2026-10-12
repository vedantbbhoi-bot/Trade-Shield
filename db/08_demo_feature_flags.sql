-- ==============================================================================
-- TradeShield * 08_demo_feature_flags.sql
--
-- Tiny admin-editable flags used only by the MOCK blockchain demo integration.
--
-- This is deliberately minimal and admin-only. It does NOT affect order execution,
-- trading logic, security screening, auth, or RBAC.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS demo_feature_flags (
    flag_key       VARCHAR(64) PRIMARY KEY,
    flag_value     TEXT NOT NULL DEFAULT 'false',
    updated_by     UUID,                       -- admin user_id who last changed it
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_demo_flag_boolean_value
        CHECK (flag_value IN ('true', 'false'))
);

COMMENT ON TABLE demo_feature_flags IS
' Admin-controlled demo feature flags (MOCK blockchain integration only ).';

-- Start with the demo client mock proof recording flag disabled.
INSERT INTO demo_feature_flags (flag_key, flag_value)
VALUES ('demo_client_blockchain_proofs', 'false')
ON CONFLICT (flag_key) DO NOTHING;
