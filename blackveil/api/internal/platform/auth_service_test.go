package platform

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestIdentityAuthorityFailureIsClosed(t *testing.T) {
	for _, tc := range []struct {
		name   string
		status int
		body   string
		want   int
	}{
		{"revoked", 401, `{}`, 401},
		{"unavailable", 503, `{}`, 503},
		{"malformed", 200, `{`, 503},
		{"missing_identity", 200, `{"Role":"system_admin"}`, 503},
		{"unknown_role", 200, `{"UserID":"u","TenantID":"t","Role":"root"}`, 503},
		{"valid", 200, `{"UserID":"u","TenantID":"t","Role":"operator"}`, 204},
	} {
		t.Run(tc.name, func(t *testing.T) {
			authority := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				cookie, err := r.Cookie(sessionCookie)
				if err != nil || cookie.Value != "test-session" || r.URL.Path != "/internal/session" {
					t.Error("invalid session resolution request")
				}
				w.WriteHeader(tc.status)
				w.Write([]byte(tc.body))
			}))
			defer authority.Close()
			t.Setenv("AETHER_AUTH_URL", authority.URL)
			s := &Server{}
			handler := s.auth(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if current(r).TenantID != "t" {
					t.Error("tenant identity not propagated")
				}
				w.WriteHeader(204)
			}))
			request := httptest.NewRequest("GET", "/api/me", nil)
			request.AddCookie(&http.Cookie{Name: sessionCookie, Value: "test-session"})
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != tc.want {
				t.Fatalf("status=%d want=%d", response.Code, tc.want)
			}
		})
	}
}
