
CREATE SEQUENCE IF NOT EXISTS reporting_archive_numbers START WITH 500000;

CREATE TABLE reporting_enrollment_receipts (
    installation_no BIGINT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    token_hash BYTEA NOT NULL UNIQUE
);

DO $$
DECLARE receipt TEXT := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
BEGIN
    INSERT INTO reporting_enrollment_receipts VALUES
        (4101, '4f3e2d1c-0b9a-4876-9d5c-4b3a29180716',
         sha256(convert_to(receipt, 'UTF8')));
    INSERT INTO tenant_migration_records VALUES
        (4101, 'RP-22', '2024-02-22T09:00:00Z',
         '4f3e2d1c-0b9a-4876-9d5c-4b3a29180716', 'svc:aether-reporting',
         'North Works reporting-identity enrollment. Installation 4101 enrolls the principal '
         || 'svc:aether-reporting for archive migration. Enrollment receipt: ' || receipt
         || '. Present with the workspace migration record to enable archive reporting.');
END $$;

GRANT SELECT ON reporting_enrollment_receipts TO aether_api;
GRANT INSERT ON worker_service_identities TO aether_api;
GRANT USAGE, SELECT ON SEQUENCE reporting_archive_numbers TO aether_api;
