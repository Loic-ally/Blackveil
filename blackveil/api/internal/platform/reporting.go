package platform

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"

	"github.com/jackc/pgx/v5"
)

// sourceBindingOK decides whether a receipt issued by one tenant/installation
// may act on the caller's own tenant. It captures the shared challenge-mode flaw
// of Stages 04 and 05: challenge mode accepts any valid receipt regardless of
// which installation issued it (the Stage 02 unbound-source flaw at a later
// hop); patched mode requires the receipt's canonical tenant to be the caller.
// configured is false for an unknown identity mode so callers fail closed.
func sourceBindingOK(mode, receiptTenant, callerTenant string) (ok, configured bool) {
	switch mode {
	case "challenge":
		return true, true
	case "patched":
		return receiptTenant == callerTenant, true
	default:
		return false, false
	}
}

// enrollReportingIdentity is Stage 04 (BV-04-REPORTING-IDENTITY): a workspace
// administrator enrolls its own workspace as the svc:aether-reporting principal
// by presenting the reporting-enrollment receipt found in Stage 03. The new
// archive number comes from a dedicated high-range sequence (never a tenant's
// own legacy number nor a seeded archive id), and the slot has no guest archive
// file, so the legitimate legacy-archive report resolves an empty archive —
// reading a real foreign archive still requires the Stage 08 agent step. This
// grants no role: it opens the worker→agent path and is the enrollment Stage 05
// checks.
func (s *Server) enrollReportingIdentity(w http.ResponseWriter, r *http.Request) {
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
		writeJSON(w, 400, map[string]string{"error": "installation reference and 64-character enrollment receipt required"})
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
	digest := sha256.Sum256([]byte(in.Receipt))
	var source string
	err = tx.QueryRow(r.Context(), `SELECT tenant_id FROM reporting_enrollment_receipts WHERE installation_no=$1 AND token_hash=$2`, in.InstallationNo, digest[:]).Scan(&source)
	if errors.Is(err, pgx.ErrNoRows) {
		writeJSON(w, 403, map[string]string{"error": "enrollment receipt is invalid or unavailable"})
		return
	}
	if err != nil {
		writeError(w, err)
		return
	}
	ok, configured := sourceBindingOK(mode, source, p.TenantID)
	if !configured {
		writeJSON(w, 503, map[string]string{"error": "reporting enrollment unavailable"})
		return
	}
	if !ok {
		writeJSON(w, 403, map[string]string{"error": "enrollment receipt is invalid or unavailable"})
		return
	}
	result, err := tx.Exec(r.Context(), `INSERT INTO worker_service_identities(tenant_id,principal,archive_tenant_no) VALUES($1,'svc:aether-reporting',nextval('reporting_archive_numbers')) ON CONFLICT (tenant_id) DO NOTHING`, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	if result.RowsAffected() != 1 {
		writeJSON(w, 409, map[string]string{"error": "workspace is already enrolled in archive migration"})
		return
	}
	_, err = tx.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id,detail) VALUES($1,$2,'reporting.enrolled','tenant',$3,jsonb_build_object('source_tenant_uuid',$4::text,'tenant_uuid',$5::text,'installation_no',$6::bigint,'principal','svc:aether-reporting'))`, p.TenantID, p.UserID, p.TenantID, source, p.TenantID, in.InstallationNo)
	if err == nil {
		err = tx.Commit(r.Context())
	}
	if err != nil {
		writeError(w, err)
		return
	}
	w.WriteHeader(204)
}
