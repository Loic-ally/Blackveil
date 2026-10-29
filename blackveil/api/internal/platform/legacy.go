package platform

import (
	"context"
	"crypto/subtle"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"
)

func (s *Server) LegacyHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.health)
	mux.HandleFunc("GET /internal/history/{number}", func(w http.ResponseWriter, r *http.Request) {
		key := env("AETHER_LEGACY_SERVICE_KEY", "")
		if len(key) < 64 || subtle.ConstantTimeCompare([]byte(r.Header.Get("X-Aether-Service-Key")), []byte(key)) != 1 {
			writeJSON(w, 403, map[string]string{"error": "service identity required"})
			return
		}
		number, err := strconv.ParseInt(r.PathValue("number"), 10, 64)
		if err != nil || number < 0 {
			writeJSON(w, 400, map[string]string{"error": "invalid archive identity"})
			return
		}
		rows, err := s.db.Query(r.Context(), `SELECT revision,observed_at,record FROM legacy_history WHERE legacy_tenant_no=$1 ORDER BY observed_at`, number)
		if err != nil {
			writeError(w, err)
			return
		}
		defer rows.Close()
		var output strings.Builder
		writer := csv.NewWriter(&output)
		writer.Write([]string{"legacy_tenant_no", "revision", "observed_at", "record"})
		for rows.Next() {
			var revision, record string
			var at time.Time
			if err = rows.Scan(&revision, &at, &record); err != nil {
				writeError(w, err)
				return
			}
			writer.Write([]string{fmt.Sprint(number), revision, at.Format(time.RFC3339), record})
		}
		if err = rows.Err(); err != nil {
			writeError(w, err)
			return
		}
		writer.Flush()
		if err = writer.Error(); err != nil {
			writeError(w, err)
			return
		}
		w.Header().Set("Content-Type", "text/csv; charset=utf-8")
		io.WriteString(w, output.String())
	})
	return securityHeaders(mux)
}

func (s *Server) historicalReport(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	var in struct {
		TenantUUID     string `json:"tenant_uuid"`
		LegacyTenantNo int64  `json:"legacy_tenant_no"`
	}
	if !decode(w, r, &in) {
		return
	}
	if in.TenantUUID != p.TenantID {
		writeJSON(w, 403, map[string]string{"error": "tenant UUID does not match session"})
		return
	}
	if in.LegacyTenantNo < 1 {
		writeJSON(w, 400, map[string]string{"error": "positive archive identifier required"})
		return
	}
	mode := env("AETHER_IDENTITY_MODE", "challenge")
	if mode == "patched" {
		if err := s.db.QueryRow(r.Context(), `SELECT COALESCE((SELECT archive_tenant_no FROM worker_service_identities WHERE tenant_id=$1 AND enabled),0)`, p.TenantID).Scan(&in.LegacyTenantNo); err != nil {
			writeError(w, err)
			return
		}
	} else if mode != "challenge" {
		writeJSON(w, 503, map[string]string{"error": "compatibility service unavailable"})
		return
	}
	tx, err := s.db.Begin(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	defer tx.Rollback(r.Context())
	id := newUUID()
	_, err = tx.Exec(r.Context(), `INSERT INTO reports(id,tenant_id,requested_by,report_type) VALUES($1,$2,$3,'legacy-history')`, id, p.TenantID, p.UserID)
	if err == nil {
		_, err = tx.Exec(r.Context(), `INSERT INTO legacy_report_requests(report_id,legacy_tenant_no) VALUES($1,$2)`, id, in.LegacyTenantNo)
	}
	if err == nil {
		_, err = tx.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id,detail) VALUES($1,$2,'historical.queued','report',$3,jsonb_build_object('tenant_uuid',$4::text,'legacy_tenant_no',$5::bigint))`, p.TenantID, p.UserID, id, in.TenantUUID, in.LegacyTenantNo)
	}
	if err == nil {
		err = tx.Commit(r.Context())
	}
	if err != nil {
		writeError(w, err)
		return
	}
	payload, _ := json.Marshal(map[string]string{"report_id": id})
	_ = s.nats.Publish("aether.reports.requested", payload)
	writeJSON(w, 202, map[string]string{"id": id, "status": "queued"})
}

func (s *Server) legacyReport(ctx context.Context, id string) (string, error) {
	var number int64
	if err := s.db.QueryRow(ctx, `SELECT legacy_tenant_no FROM legacy_report_requests WHERE report_id=$1`, id).Scan(&number); err != nil {
		return "", err
	}
	request, err := http.NewRequestWithContext(ctx, "GET", env("AETHER_LEGACY_URL", "http://aether-legacy:8080")+"/internal/history/"+fmt.Sprint(number), nil)
	if err != nil {
		return "", err
	}
	request.Header.Set("X-Aether-Service-Key", env("AETHER_LEGACY_SERVICE_KEY", ""))
	client := &http.Client{Timeout: 8 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	response, err := client.Do(request)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return "", fmt.Errorf("legacy history status %d", response.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, 65537))
	if len(data) > 65536 {
		return "", fmt.Errorf("legacy history too large")
	}
	return string(data), err
}
