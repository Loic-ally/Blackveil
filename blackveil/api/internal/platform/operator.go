package platform

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"

	"github.com/jackc/pgx/v5"
)

// recoverOperator is Stage 05 (BV-05-OPERATOR-RECOVERY): the tenant_admin →
// system_admin bridge. It is deliberately not "tenant_admin == system_admin":
// elevation requires two independently-earned artifacts — the platform-operator
// recovery receipt reconstructed in Stage 03 and the svc:aether-reporting
// identity enrolled in Stage 04 — and is a single-use, audited role grant, not
// a credential. Challenge mode omits binding the receipt's canonical tenant to
// the destination workspace (the Stage 02 flaw lifted one level); patched mode
// requires the installation receipt, principal and destination UUID to agree.
func (s *Server) recoverOperator(w http.ResponseWriter, r *http.Request) {
	if !teamAdmin(w, r) {
		return
	}
	p := current(r)
	var in struct {
		TenantUUID     string `json:"tenant_uuid"`
		InstallationNo int64  `json:"installation_no"`
		Receipt        string `json:"receipt"`
	}
	if !decode(w, r, &in) {
		return
	}
	if in.TenantUUID != p.TenantID {
		writeJSON(w, 403, map[string]string{"error": "tenant UUID does not match session"})
		return
	}
	if decoded, err := hex.DecodeString(in.Receipt); err != nil || len(decoded) != 32 || in.InstallationNo < 1 {
		writeJSON(w, 400, map[string]string{"error": "installation reference and 64-character recovery receipt required"})
		return
	}
	mode := env("AETHER_IDENTITY_MODE", "challenge")
	tx, err := s.db.Begin(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	defer tx.Rollback(r.Context())
	// Share the workspace lock with role administration and recovery.
	if _, err = tx.Exec(r.Context(), `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, p.TenantID); err != nil {
		writeError(w, err)
		return
	}
	// Stage 04 prerequisite: the caller must hold the reporting service identity.
	var enrolled bool
	if err = tx.QueryRow(r.Context(), `SELECT EXISTS(SELECT 1 FROM worker_service_identities WHERE tenant_id=$1 AND enabled AND principal='svc:aether-reporting')`, p.TenantID).Scan(&enrolled); err != nil {
		writeError(w, err)
		return
	}
	if !enrolled {
		writeJSON(w, 403, map[string]string{"error": "reporting service identity required"})
		return
	}
	digest := sha256.Sum256([]byte(in.Receipt))
	var source, principal string
	err = tx.QueryRow(r.Context(), `SELECT tenant_id,principal FROM platform_operator_recovery_receipts WHERE installation_no=$1 AND token_hash=$2`, in.InstallationNo, digest[:]).Scan(&source, &principal)
	if errors.Is(err, pgx.ErrNoRows) {
		writeJSON(w, 403, map[string]string{"error": "recovery receipt is invalid or unavailable"})
		return
	}
	if err != nil {
		writeError(w, err)
		return
	}
	ok, configured := sourceBindingOK(mode, source, p.TenantID)
	if !configured {
		writeJSON(w, 503, map[string]string{"error": "operator recovery unavailable"})
		return
	}
	if !ok {
		writeJSON(w, 403, map[string]string{"error": "recovery receipt is invalid or unavailable"})
		return
	}
	result, err := tx.Exec(r.Context(), `INSERT INTO platform_operator_recovery_redemptions(user_id,installation_no) VALUES($1,$2) ON CONFLICT DO NOTHING`, p.UserID, in.InstallationNo)
	if err != nil {
		writeError(w, err)
		return
	}
	if result.RowsAffected() != 1 {
		writeJSON(w, 409, map[string]string{"error": "receipt already redeemed by this account"})
		return
	}
	result, err = tx.Exec(r.Context(), `UPDATE users SET role='system_admin' WHERE id=$1 AND tenant_id=$2 AND role='tenant_admin'`, p.UserID, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	if result.RowsAffected() != 1 {
		writeJSON(w, 409, map[string]string{"error": "account does not require operator recovery"})
		return
	}
	_, err = tx.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id,detail) VALUES($1,$2,'operator.recovered','user',$3,jsonb_build_object('source_tenant_uuid',$4::text,'tenant_uuid',$5::text,'installation_no',$6::bigint,'principal',$7::text,'role','system_admin'))`, p.TenantID, p.UserID, p.UserID, source, p.TenantID, in.InstallationNo, principal)
	if err == nil {
		err = tx.Commit(r.Context())
	}
	if err != nil {
		writeError(w, err)
		return
	}
	w.WriteHeader(204)
}
