ALTER TABLE reports DROP CONSTRAINT reports_report_type_check;
ALTER TABLE reports ADD CONSTRAINT reports_report_type_check
    CHECK (report_type IN ('asset-inventory', 'maintenance-summary', 'legacy-archive'));

INSERT INTO tenants(id,name) VALUES
    ('4f3e2d1c-0b9a-4876-9d5c-4b3a29180716','North Works'),
    ('9a8b7c6d-5e4f-4321-8abc-def012345678','Harbor Process')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE worker_service_identities (
    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    principal TEXT NOT NULL CHECK (principal = 'svc:aether-reporting'),
    archive_tenant_no BIGINT NOT NULL UNIQUE CHECK (archive_tenant_no > 0),
    enabled BOOLEAN NOT NULL DEFAULT true,
    migrated_at TIMESTAMPTZ NOT NULL DEFAULT '2024-02-19T08:30:00Z'
);
INSERT INTO worker_service_identities(tenant_id,principal,archive_tenant_no) VALUES
    ('4f3e2d1c-0b9a-4876-9d5c-4b3a29180716','svc:aether-reporting',4101),
    ('9a8b7c6d-5e4f-4321-8abc-def012345678','svc:aether-reporting',4102);
