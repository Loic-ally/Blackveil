-- Stage 05 (BV-05-OPERATOR-RECOVERY) single-use redemption tracking.
-- The platform-operator receipt table is seeded in migration 008; this adds the
-- per-account redemption ledger so a platform-operator receipt elevates a given
-- account to system_admin at most once, mirroring the Stage 02 administrator
-- recovery ledger.
CREATE TABLE platform_operator_recovery_redemptions (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    installation_no BIGINT NOT NULL REFERENCES platform_operator_recovery_receipts(installation_no),
    redeemed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, installation_no)
);

GRANT SELECT, INSERT ON platform_operator_recovery_redemptions TO aether_api;
