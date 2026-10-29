package platform

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"time"
)

// AuthHandler exposes credential operations and a private session resolution contract.
func (s *Server) AuthHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.health)
	mux.HandleFunc("POST /api/auth/register", s.register)
	mux.HandleFunc("POST /api/auth/invitations/accept", s.acceptInvite)
	mux.HandleFunc("POST /api/auth/login", s.login)
	mux.HandleFunc("POST /api/auth/logout", s.logout)
	mux.Handle("GET /internal/session", s.localAuth(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, current(r))
	})))
	return securityHeaders(mux)
}

func (s *Server) auth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cookie, err := r.Cookie(sessionCookie)
		if err != nil {
			writeJSON(w, 401, map[string]string{"error": "authentication required"})
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer cancel()
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, env("AETHER_AUTH_URL", "http://aether-auth:8080")+"/internal/session", nil)
		if err != nil {
			writeError(w, err)
			return
		}
		request.AddCookie(cookie)
		client := &http.Client{CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
		response, err := client.Do(request)
		if err != nil {
			writeJSON(w, 503, map[string]string{"error": "identity service unavailable"})
			return
		}
		defer response.Body.Close()
		if response.StatusCode == 401 {
			writeJSON(w, 401, map[string]string{"error": "session expired"})
			return
		}
		var p principal
		if response.StatusCode != 200 || json.NewDecoder(io.LimitReader(response.Body, 8192)).Decode(&p) != nil || p.UserID == "" || p.TenantID == "" || !oneOf(p.Role, "operator", "maintenance", "tenant_admin", "system_admin") {
			writeJSON(w, 503, map[string]string{"error": "identity service unavailable"})
			return
		}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), principalKey{}, p)))
	})
}
