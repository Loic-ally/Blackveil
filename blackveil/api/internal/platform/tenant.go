package platform

import (
	"net/http"
	"strconv"
	"time"
)

// migrationLookupNumber reproduces the Stage 01 identity flaw at the settings
// layer. Challenge mode trusts the caller-supplied archive/installation number
// without binding it to the authenticated tenant; patched mode ignores the
// request value and resolves the caller's own canonical number. ok is false for
// an unconfigured identity mode so the handler fails closed.
func migrationLookupNumber(mode string, requested, canonical int64) (number int64, ok bool) {
	switch mode {
	case "patched":
		return canonical, true
	case "challenge":
		return requested, true
	default:
		return 0, false
	}
}

// tenantSettings is the authenticated workspace's own settings view. It never
// discloses another tenant: it returns only the caller's canonical identity and
// archive-enrollment status. (Fills the previously absent tenant settings.)
func (s *Server) tenantSettings(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	var name string
	var canonical int64
	if err := s.db.QueryRow(r.Context(), `SELECT name,legacy_tenant_no FROM tenants WHERE id=$1`, p.TenantID).Scan(&name, &canonical); err != nil {
		writeError(w, err)
		return
	}
	var enrolled bool
	if err := s.db.QueryRow(r.Context(), `SELECT EXISTS(SELECT 1 FROM worker_service_identities WHERE tenant_id=$1 AND enabled)`, p.TenantID).Scan(&enrolled); err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, 200, map[string]any{
		"tenant_uuid":      p.TenantID,
		"name":             name,
		"legacy_tenant_no": canonical,
		"archive_enabled":  enrolled,
	})
}

// tenantMigration returns migration/audit history for an archive installation
// number. Stage 03 (BV-03-HISTORICAL-RECONSTRUCTION): challenge mode resolves
// the number from the request without binding it to the session tenant, so a
// workspace administrator can reconstruct foreign migration records and the
// platform-operator artifact. Patched mode resolves the caller's own canonical
// number and so returns only the caller's history.
func (s *Server) tenantMigration(w http.ResponseWriter, r *http.Request) {
	if !teamAdmin(w, r) {
		return
	}
	p := current(r)
	requested, err := strconv.ParseInt(r.URL.Query().Get("legacy_tenant_no"), 10, 64)
	if err != nil || requested < 0 {
		writeJSON(w, 400, map[string]string{"error": "positive installation number required"})
		return
	}
	var canonical int64
	if err := s.db.QueryRow(r.Context(), `SELECT legacy_tenant_no FROM tenants WHERE id=$1`, p.TenantID).Scan(&canonical); err != nil {
		writeError(w, err)
		return
	}
	number, ok := migrationLookupNumber(env("AETHER_IDENTITY_MODE", "challenge"), requested, canonical)
	if !ok {
		writeJSON(w, 503, map[string]string{"error": "migration service unavailable"})
		return
	}
	rows, err := s.db.Query(r.Context(), `SELECT revision,recorded_at,tenant_uuid,principal,detail FROM tenant_migration_records WHERE legacy_tenant_no=$1 ORDER BY recorded_at`, number)
	if err != nil {
		writeError(w, err)
		return
	}
	defer rows.Close()
	records := []map[string]any{}
	for rows.Next() {
		var revision, detail string
		var recordedAt time.Time
		var tenantUUID, principal *string
		if err = rows.Scan(&revision, &recordedAt, &tenantUUID, &principal, &detail); err != nil {
			writeError(w, err)
			return
		}
		records = append(records, map[string]any{
			"legacy_tenant_no": number,
			"revision":         revision,
			"recorded_at":      recordedAt.Format(time.RFC3339),
			"tenant_uuid":      tenantUUID,
			"principal":        principal,
			"detail":           detail,
		})
	}
	if err = rows.Err(); err != nil {
		writeError(w, err)
		return
	}
	if _, err = s.db.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id,detail) VALUES($1,$2,'tenant.migration_read','tenant',$3,jsonb_build_object('legacy_tenant_no',$4::bigint))`, p.TenantID, p.UserID, p.TenantID, number); err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, 200, map[string]any{"legacy_tenant_no": number, "records": records})
}
