package platform

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"

	"github.com/jackc/pgx/v5"
)

func (s *Server) recoverAdministrator(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	var in struct {
		TenantUUID     string `json:"tenant_uuid"`
		LegacyTenantNo int64  `json:"legacy_tenant_no"`
		Receipt        string `json:"receipt"`
	}
	if !decode(w, r, &in) {
		return
	}
	if in.TenantUUID != p.TenantID {
		writeJSON(w, 403, map[string]string{"error": "tenant UUID does not match session"})
		return
	}
	if decoded, err := hex.DecodeString(in.Receipt); err != nil || len(decoded) != 32 || in.LegacyTenantNo < 1 {
		writeJSON(w, 400, map[string]string{"error": "installation reference and 64-character recovery receipt required"})
		return
	}
	mode := env("AETHER_IDENTITY_MODE", "challenge")
	if mode != "challenge" && mode != "patched" {
		writeJSON(w, 503, map[string]string{"error": "recovery service unavailable"})
		return
	}
	tx, err := s.db.Begin(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	defer tx.Rollback(r.Context())
	// Share the workspace lock with ordinary role administration.
	_, err = tx.Exec(r.Context(), `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	digest := sha256.Sum256([]byte(in.Receipt))
	var source string
	err = tx.QueryRow(r.Context(), `SELECT tenant_id FROM administrator_recovery_receipts WHERE legacy_tenant_no=$1 AND token_hash=$2`, in.LegacyTenantNo, digest[:]).Scan(&source)
	if errors.Is(err, pgx.ErrNoRows) {
		writeJSON(w, 403, map[string]string{"error": "recovery receipt is invalid or unavailable"})
		return
	}
	if err != nil {
		writeError(w, err)
		return
	}
	if mode == "patched" && source != p.TenantID {
		writeJSON(w, 403, map[string]string{"error": "recovery receipt is invalid or unavailable"})
		return
	}
	result, err := tx.Exec(r.Context(), `INSERT INTO administrator_recovery_redemptions(user_id,legacy_tenant_no) VALUES($1,$2) ON CONFLICT DO NOTHING`, p.UserID, in.LegacyTenantNo)
	if err != nil {
		writeError(w, err)
		return
	}
	if result.RowsAffected() != 1 {
		writeJSON(w, 409, map[string]string{"error": "receipt already redeemed by this account"})
		return
	}
	result, err = tx.Exec(r.Context(), `UPDATE users SET role='tenant_admin' WHERE id=$1 AND tenant_id=$2 AND role IN ('operator','maintenance')`, p.UserID, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	if result.RowsAffected() != 1 {
		writeJSON(w, 409, map[string]string{"error": "account does not require administrator recovery"})
		return
	}
	_, err = tx.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id,detail) VALUES($1,$2,'administrator.recovered','user',$3,jsonb_build_object('source_tenant_uuid',$4::text,'tenant_uuid',$5::text,'legacy_tenant_no',$6::bigint,'role','tenant_admin'))`, p.TenantID, p.UserID, p.UserID, source, p.TenantID, in.LegacyTenantNo)
	if err == nil {
		err = tx.Commit(r.Context())
	}
	if err != nil {
		writeError(w, err)
		return
	}
	w.WriteHeader(204)
}
