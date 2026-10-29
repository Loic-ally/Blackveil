GRANT USAGE ON SCHEMA public TO aether_api, aether_auth, aether_worker, aether_legacy, aether_telemetry;

GRANT SELECT (id, tenant_id, email, display_name, role, created_at) ON users TO aether_api;
GRANT UPDATE (role) ON users TO aether_api;
GRANT SELECT ON invitations TO aether_api;
GRANT INSERT ON invitations TO aether_api;
GRANT UPDATE (revoked_at) ON invitations TO aether_api;
GRANT SELECT, INSERT ON assets TO aether_api;
GRANT SELECT, INSERT ON telemetry TO aether_api;
GRANT SELECT, INSERT ON incidents TO aether_api;
GRANT UPDATE (status, updated_at) ON incidents TO aether_api;
GRANT SELECT, INSERT ON notifications TO aether_api;
GRANT UPDATE (read_at) ON notifications TO aether_api;
GRANT SELECT, INSERT ON reports TO aether_api;
GRANT UPDATE (status, error, completed_at) ON reports TO aether_api;
GRANT SELECT, INSERT ON audit_events TO aether_api;
GRANT SELECT ON worker_service_identities TO aether_api;
GRANT INSERT ON legacy_report_requests TO aether_api;
GRANT USAGE, SELECT ON SEQUENCE audit_events_id_seq, telemetry_id_seq TO aether_api;

GRANT SELECT, INSERT ON tenants, users, sessions, assets, telemetry,
    notifications, audit_events TO aether_auth;
GRANT DELETE ON sessions TO aether_auth;
GRANT SELECT ON invitations TO aether_auth;
GRANT UPDATE (accepted_at) ON invitations TO aether_auth;
GRANT USAGE, SELECT ON SEQUENCE audit_events_id_seq, telemetry_id_seq TO aether_auth;
GRANT USAGE ON SEQUENCE legacy_tenant_numbers TO aether_auth;

GRANT SELECT ON assets, incidents, telemetry, worker_service_identities,
    legacy_report_requests TO aether_worker;
GRANT SELECT, UPDATE ON reports TO aether_worker;
GRANT INSERT ON notifications, audit_events TO aether_worker;
GRANT USAGE, SELECT ON SEQUENCE audit_events_id_seq TO aether_worker;

GRANT SELECT ON legacy_history TO aether_legacy;
GRANT SELECT ON assets TO aether_telemetry;
GRANT INSERT ON telemetry TO aether_telemetry;
GRANT USAGE, SELECT ON SEQUENCE telemetry_id_seq TO aether_telemetry;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO aether_api;
