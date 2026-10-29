ALTER TABLE reports DROP CONSTRAINT reports_report_type_check;
ALTER TABLE reports ADD CONSTRAINT reports_report_type_check CHECK (
    report_type IN ('asset-inventory','maintenance-summary','legacy-archive','legacy-history')
);
CREATE TABLE legacy_report_requests (
    report_id UUID PRIMARY KEY REFERENCES reports(id) ON DELETE CASCADE,
    legacy_tenant_no BIGINT NOT NULL CHECK (legacy_tenant_no>=0)
);
CREATE TABLE legacy_history (
    legacy_tenant_no BIGINT NOT NULL,
    revision TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    record TEXT NOT NULL,
    PRIMARY KEY (legacy_tenant_no,revision)
);
INSERT INTO legacy_history VALUES
 (4101,'IM-17','2024-02-19T08:30:00Z','North Works: archive tenant 4101 maps to UUID 4f3e2d1c-0b9a-4876-9d5c-4b3a29180716. Reporting principal svc:aether-reporting retained under migration protocol 1.'),
 (4101,'IM-19','2024-02-20T10:15:00Z','Archive replay receipt fields: job_id, principal, tenant_uuid. Numeric archive selector is retained by the archive adapter. Build agent/1.4.2-migration-protocol.'),
 (4102,'IM-18','2024-02-19T08:45:00Z','Harbor Process: archive tenant 4102 maps to UUID 9a8b7c6d-5e4f-4321-8abc-def012345678. Public installation snapshots still carry the previous North Works source reference.'),
 (4102,'OP-64','2024-03-04T16:00:00Z','Maintenance archive C-17 retained on aether-linux. Archive transport is distinct from the telemetry cache; a cache flush does not change archive identity resolution.');
