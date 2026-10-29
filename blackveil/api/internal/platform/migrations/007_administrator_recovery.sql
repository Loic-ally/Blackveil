CREATE TABLE administrator_recovery_receipts (
    legacy_tenant_no BIGINT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    token_hash BYTEA NOT NULL UNIQUE
);
CREATE TABLE administrator_recovery_redemptions (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    legacy_tenant_no BIGINT NOT NULL REFERENCES administrator_recovery_receipts(legacy_tenant_no),
    redeemed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, legacy_tenant_no)
);

DO $$
DECLARE receipt TEXT := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
BEGIN
    INSERT INTO administrator_recovery_receipts VALUES
        (4101, '4f3e2d1c-0b9a-4876-9d5c-4b3a29180716', sha256(convert_to(receipt, 'UTF8')));
    INSERT INTO legacy_history VALUES
        (4101, 'ADM-21', '2024-02-21T09:00:00Z',
         'North Works administrator handover. Source UUID 4f3e2d1c-0b9a-4876-9d5c-4b3a29180716; installation 4101. Recovery receipt: ' || receipt ||
         '. Retain with the installation archive for workspace administration recovery. Each account may redeem once.');
END $$;

GRANT SELECT ON administrator_recovery_receipts TO aether_api;
GRANT SELECT, INSERT ON administrator_recovery_redemptions TO aether_api;
