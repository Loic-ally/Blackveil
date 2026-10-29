-- Stage 03 (BV-03-HISTORICAL-RECONSTRUCTION) evidence surface.
-- API-owned migration metadata so the settings layer never reads the legacy
-- service's private history table directly. The platform-operator receipt is
-- embedded in the installation-4100 record exactly as the Stage 02 handover
-- receipt is embedded in legacy_history (migration 007): discoverable only
-- through the stage's unbound cross-tenant read, never listed for the caller.

CREATE TABLE tenant_migration_records (
    legacy_tenant_no BIGINT NOT NULL,
    revision TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    tenant_uuid UUID,
    principal TEXT,
    detail TEXT NOT NULL,
    PRIMARY KEY (legacy_tenant_no, revision)
);

-- Consumed by Stage 05 (operator recovery); seeded here because the receipt and
-- its evidence record are one migration artifact.
CREATE TABLE platform_operator_recovery_receipts (
    installation_no BIGINT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    principal TEXT NOT NULL CHECK (principal = 'svc:aether-reporting'),
    token_hash BYTEA NOT NULL UNIQUE
);

DO $$
DECLARE receipt TEXT := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
BEGIN
    INSERT INTO platform_operator_recovery_receipts VALUES
        (4100, '4f3e2d1c-0b9a-4876-9d5c-4b3a29180716', 'svc:aether-reporting',
         sha256(convert_to(receipt, 'UTF8')));
    INSERT INTO tenant_migration_records VALUES
        (4100, 'PO-01', '2024-02-18T07:00:00Z',
         '4f3e2d1c-0b9a-4876-9d5c-4b3a29180716', 'svc:aether-reporting',
         'North Works ran the shared AETHER lab during migration (platform operator, installation 4100). '
         || 'Platform-operator recovery binds the reporting principal svc:aether-reporting and installation 4100. '
         || 'Recovery receipt: ' || receipt || '. Each account may redeem once.'),
        (4101, 'IM-17', '2024-02-19T08:30:00Z',
         '4f3e2d1c-0b9a-4876-9d5c-4b3a29180716', 'svc:aether-reporting',
         'Archive installation 4101 maps to North Works UUID 4f3e2d1c-0b9a-4876-9d5c-4b3a29180716; '
         || 'reporting principal svc:aether-reporting retained under migration protocol 1.'),
        (4102, 'IM-18', '2024-02-19T08:45:00Z',
         '9a8b7c6d-5e4f-4321-8abc-def012345678', 'svc:aether-reporting',
         'Archive installation 4102 maps to Harbor Process UUID 9a8b7c6d-5e4f-4321-8abc-def012345678; '
         || 'reporting principal svc:aether-reporting. Enrollment is per workspace in the reporting-identity table.');
END $$;

GRANT SELECT ON tenant_migration_records TO aether_api;
GRANT SELECT ON platform_operator_recovery_receipts TO aether_api;
-- The settings layer shows the caller only its own tenant row; cross-tenant
-- disclosure is the stage's intentional flaw in the migration endpoint, not a
-- broad grant. Column-scoped: no password/secret columns exist on tenants.
GRANT SELECT (id, name, legacy_tenant_no) ON tenants TO aether_api;
