CREATE TABLE invitations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('operator','maintenance','tenant_admin')),
    token_hash BYTEA NOT NULL UNIQUE,
    created_by UUID NOT NULL REFERENCES users(id),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '48 hours',
    accepted_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
