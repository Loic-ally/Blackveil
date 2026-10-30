-- Stage 15 (BV-15-THE-BLACK-VEIL) player-facing completion ledger.
-- Records that a player submitted a correct final proof through the AETHER API
-- (POST /api/v2/lab/final-proof), which forwards the candidate to the isolated
-- validator. One completion per user (idempotent). The submitted proof is stored
-- only as a SHA-256 hash, never in plaintext; the minted flag is retained so the
-- player can re-view their completion without re-contacting the validator.
CREATE TABLE final_proof_completions (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    proof_sha256 BYTEA NOT NULL,
    flag TEXT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT ON final_proof_completions TO aether_api;
