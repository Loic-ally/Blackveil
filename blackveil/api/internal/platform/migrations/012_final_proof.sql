CREATE TABLE final_proof_completions (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    proof_sha256 BYTEA NOT NULL,
    flag TEXT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT ON final_proof_completions TO aether_api;
