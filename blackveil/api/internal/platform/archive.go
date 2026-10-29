package platform

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type archiveEnvelope struct {
	JobID          string `json:"job_id"`
	Principal      string `json:"principal"`
	TenantUUID     string `json:"tenant_uuid"`
	LegacyTenantNo int64  `json:"legacy_tenant_no"`
	Signature      string `json:"signature"`
}

func (s *Server) archiveReport(ctx context.Context, job, tenant string) (string, error) {
	envelope := archiveEnvelope{JobID: job, TenantUUID: tenant}
	if err := s.db.QueryRow(ctx, `SELECT principal,archive_tenant_no FROM worker_service_identities WHERE tenant_id=$1 AND enabled`, tenant).Scan(&envelope.Principal, &envelope.LegacyTenantNo); err != nil {
		return "", err
	}
	content, err := fetchArchive(ctx, env("AETHER_AGENT_URL", "http://aether-linux-vm:18080"), env("AETHER_AGENT_KEY", ""), env("AETHER_AGENT_MODE", "challenge"), &envelope)
	if err != nil {
		return "", err
	}
	detail, err := json.Marshal(envelope)
	if err != nil {
		return "", err
	}
	_, err = s.db.Exec(ctx, `INSERT INTO audit_events(tenant_id,action,object_type,object_id,detail) VALUES($1,'archive.resolved','report',$2,$3)`, tenant, job, string(detail))
	return content, err
}

func fetchArchive(ctx context.Context, endpoint, keyHex, mode string, envelope *archiveEnvelope) (string, error) {
	if mode != "challenge" && mode != "patched" {
		return "", fmt.Errorf("unsupported archive protocol mode")
	}
	key, err := hex.DecodeString(keyHex)
	if err != nil || len(key) < 32 {
		return "", fmt.Errorf("archive signing key unavailable")
	}
	projection := fmt.Sprintf("%s\n%s\n%s", envelope.JobID, envelope.Principal, envelope.TenantUUID)
	if mode == "patched" {
		projection += fmt.Sprintf("\n%d", envelope.LegacyTenantNo)
	}
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(projection))
	envelope.Signature = hex.EncodeToString(mac.Sum(nil))
	body, err := json.Marshal(envelope)
	if err != nil {
		return "", err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(endpoint, "/")+"/v1/legacy/archive", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	request.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 8 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	response, err := client.Do(request)
	if err != nil {
		return "", fmt.Errorf("archive agent connection: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return "", fmt.Errorf("archive agent returned %d", response.StatusCode)
	}
	var result struct {
		JobID          string `json:"job_id"`
		TenantUUID     string `json:"tenant_uuid"`
		LegacyTenantNo int64  `json:"resolved_legacy_tenant_no"`
		Records        struct {
			LegacyTenantNo int64  `json:"legacy_tenant_no"`
			Record         string `json:"record"`
		} `json:"records"`
	}
	if err = json.NewDecoder(io.LimitReader(response.Body, 64*1024)).Decode(&result); err != nil {
		return "", err
	}
	if result.JobID != envelope.JobID || result.TenantUUID != envelope.TenantUUID || result.LegacyTenantNo != envelope.LegacyTenantNo || result.Records.LegacyTenantNo != envelope.LegacyTenantNo || result.Records.Record == "" {
		return "", fmt.Errorf("archive response identity mismatch")
	}
	var output strings.Builder
	w := csv.NewWriter(&output)
	if err = w.WriteAll([][]string{{"job_id", "tenant_uuid", "archive_tenant_no", "record"}, {result.JobID, result.TenantUUID, fmt.Sprint(result.LegacyTenantNo), result.Records.Record}}); err != nil {
		return "", err
	}
	return output.String(), nil
}
