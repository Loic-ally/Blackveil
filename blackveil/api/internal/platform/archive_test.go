package platform

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestArchiveWorkerProtocol(t *testing.T) {
	for _, mode := range []string{"challenge", "patched"} {
		for _, wrongTenant := range []bool{false, true} {
			t.Run(mode+"/wrongTenant="+map[bool]string{false: "false", true: "true"}[wrongTenant], func(t *testing.T) {
				key := strings.Repeat("ab", 32)
				server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					var e archiveEnvelope
					if err := json.NewDecoder(r.Body).Decode(&e); err != nil {
						t.Error(err)
						w.WriteHeader(400)
						return
					}
					if r.Method != "POST" || r.URL.Path != "/v1/legacy/archive" {
						t.Error("unexpected agent request")
					}
					projection := "job-1\nsvc:aether-reporting\n4f3e2d1c-0b9a-4876-9d5c-4b3a29180716"
					if mode == "patched" {
						projection += "\n4101"
					}
					decoded, _ := hex.DecodeString(key)
					mac := hmac.New(sha256.New, decoded)
					mac.Write([]byte(projection))
					if e.Signature != hex.EncodeToString(mac.Sum(nil)) {
						t.Error("incorrect signing projection")
					}
					tenant := e.TenantUUID
					if wrongTenant {
						tenant = "9a8b7c6d-5e4f-4321-8abc-def012345678"
					}
					json.NewEncoder(w).Encode(map[string]any{"job_id": e.JobID, "tenant_uuid": tenant, "resolved_legacy_tenant_no": 4101, "records": map[string]any{"legacy_tenant_no": 4101, "record": "north-works, seal inspection"}})
				}))
				defer server.Close()
				e := archiveEnvelope{JobID: "job-1", Principal: "svc:aether-reporting", TenantUUID: "4f3e2d1c-0b9a-4876-9d5c-4b3a29180716", LegacyTenantNo: 4101}
				csv, err := fetchArchive(context.Background(), server.URL, key, mode, &e)
				if wrongTenant {
					if err == nil {
						t.Fatal("foreign tenant response accepted")
					}
					return
				}
				if err != nil || !strings.Contains(csv, `"north-works, seal inspection"`) {
					t.Fatalf("archive CSV = %q, error = %v", csv, err)
				}
			})
		}
	}
}

func TestArchiveWorkerRejectsRedirect(t *testing.T) {
	called := false
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { called = true }))
	defer target.Close()
	redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, target.URL, 307) }))
	defer redirect.Close()
	_, err := fetchArchive(context.Background(), redirect.URL, strings.Repeat("ab", 32), "challenge", &archiveEnvelope{})
	if err == nil || called {
		t.Fatal("signed archive request followed redirect")
	}
}
