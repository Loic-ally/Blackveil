package platform

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"embed"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
	"golang.org/x/crypto/bcrypt"
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

const sessionCookie = "aether_session"

type Server struct {
	db               *pgxpool.Pool
	nats             *nats.Conn
	cache            *redis.Client
	publicOrigin     string
	vmSSHAddress     string
	vmSSHKeyPath     string
	vmSSHHostKeyPath string
	validatorToken   string
	validatorURL     string
	validatorClient  *http.Client
}

type principal struct {
	UserID, TenantID, Email, DisplayName, Role string
}

func New(ctx context.Context) (*Server, error) {
	dbURL := env("DATABASE_URL", "postgres://aether:aether-dev-only@aether-db:5432/aether?sslmode=disable")
	pool, err := pgxpool.New(ctx, dbURL)
	if err != nil {
		return nil, err
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, err
	}
	var nc *nats.Conn
	natsURL := env("NATS_URL", "nats://aether-bus:4222")
	for attempt := 0; attempt < 20; attempt++ {
		nc, err = nats.Connect(natsURL, nats.Timeout(1500*time.Millisecond), nats.MaxReconnects(2))
		if err == nil {
			break
		}
		time.Sleep(500 * time.Millisecond)
	}
	if err != nil {
		pool.Close()
		return nil, fmt.Errorf("connect to NATS: %w", err)
	}
	redisOptions, err := redis.ParseURL(env("REDIS_URL", "redis://aether-cache:6379/0"))
	if err != nil {
		nc.Close()
		pool.Close()
		return nil, err
	}
	cache := redis.NewClient(redisOptions)
	if err = cache.Ping(ctx).Err(); err != nil {
		_ = cache.Close()
		nc.Close()
		pool.Close()
		return nil, fmt.Errorf("connect to Redis: %w", err)
	}
	return &Server{
		db: pool, nats: nc, cache: cache,
		publicOrigin:     env("PUBLIC_ORIGIN", "https://aether.blackveil.test"),
		vmSSHAddress:     env("AETHER_VM_SSH_ADDRESS", "aether-linux-vm:2222"),
		vmSSHKeyPath:     env("AETHER_VM_SSH_KEY_PATH", "/var/lib/aether-vm/operator_ed25519"),
		vmSSHHostKeyPath: env("AETHER_VM_SSH_HOST_KEY_PATH", "/var/lib/aether-vm/guest_host_ed25519.pub"),
		validatorToken:   env("AETHER_VALIDATOR_TOKEN", ""),
		validatorURL:     env("AETHER_VALIDATOR_URL", "http://aether-validator:9000"),
		// No redirects: the validator is a fixed internal endpoint, never a
		// caller-influenced URL.
		validatorClient: &http.Client{
			Timeout:       6 * time.Second,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
		},
	}, nil
}

func (s *Server) Close() { _ = s.cache.Close(); s.nats.Close(); s.db.Close() }

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.health)
	mux.HandleFunc("GET /api/docs", s.docs)
	mux.Handle("GET /api/team", s.auth(http.HandlerFunc(s.team)))
	mux.Handle("POST /api/v2/team/recover", s.auth(s.sameOrigin(http.HandlerFunc(s.recoverAdministrator))))
	mux.Handle("POST /api/team/invitations", s.auth(s.sameOrigin(http.HandlerFunc(s.invite))))
	mux.Handle("DELETE /api/team/invitations/{id}", s.auth(s.sameOrigin(http.HandlerFunc(s.revokeInvite))))
	mux.Handle("PATCH /api/team/users/{id}", s.auth(s.sameOrigin(http.HandlerFunc(s.changeRole))))
	mux.Handle("GET /api/me", s.auth(http.HandlerFunc(s.me)))
	mux.Handle("GET /api/v2/tenant", s.auth(http.HandlerFunc(s.tenantSettings)))
	mux.Handle("GET /api/v2/tenant/migration", s.auth(http.HandlerFunc(s.tenantMigration)))
	mux.Handle("POST /api/v2/tenant/reporting-identity", s.auth(s.sameOrigin(http.HandlerFunc(s.enrollReportingIdentity))))
	mux.Handle("POST /api/v2/lab/operator-recovery", s.auth(s.sameOrigin(http.HandlerFunc(s.recoverOperator))))
	mux.Handle("GET /api/lab/terminal", s.auth(http.HandlerFunc(s.terminal)))
	mux.Handle("GET /api/v2/lab/final-proof", s.auth(http.HandlerFunc(s.finalProofStatus)))
	mux.Handle("POST /api/v2/lab/final-proof", s.auth(s.sameOrigin(http.HandlerFunc(s.submitFinalProof))))
	mux.Handle("GET /api/dashboard", s.auth(http.HandlerFunc(s.dashboard)))
	mux.Handle("GET /api/assets", s.auth(http.HandlerFunc(s.assets)))
	mux.Handle("POST /api/assets", s.auth(s.sameOrigin(http.HandlerFunc(s.createAsset))))
	mux.Handle("GET /api/assets/{id}/telemetry", s.auth(http.HandlerFunc(s.telemetry)))
	mux.Handle("GET /api/incidents", s.auth(http.HandlerFunc(s.listIncidents)))
	mux.Handle("POST /api/incidents", s.auth(s.sameOrigin(http.HandlerFunc(s.createIncident))))
	mux.Handle("PATCH /api/incidents/{id}", s.auth(s.sameOrigin(http.HandlerFunc(s.updateIncident))))
	mux.Handle("GET /api/notifications", s.auth(http.HandlerFunc(s.notifications)))
	mux.Handle("POST /api/notifications/{id}/read", s.auth(s.sameOrigin(http.HandlerFunc(s.readNotification))))
	mux.Handle("POST /api/v2/reports/historical", s.auth(s.sameOrigin(http.HandlerFunc(s.historicalReport))))
	mux.Handle("GET /api/reports", s.auth(http.HandlerFunc(s.listReports)))
	mux.Handle("POST /api/reports", s.auth(s.sameOrigin(http.HandlerFunc(s.createReport))))
	mux.Handle("GET /api/reports/{id}", s.auth(http.HandlerFunc(s.getReport)))
	mux.Handle("GET /api/audit", s.auth(http.HandlerFunc(s.audit)))
	return securityHeaders(mux)
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	if err := s.db.Ping(ctx); err != nil {
		writeJSON(w, 503, map[string]any{"status": "degraded", "database": "unavailable"})
		return
	}
	if !s.nats.IsConnected() {
		writeJSON(w, 503, map[string]any{"status": "degraded", "bus": "unavailable"})
		return
	}
	if err := s.cache.Ping(ctx).Err(); err != nil {
		writeJSON(w, 503, map[string]any{"status": "degraded", "cache": "unavailable"})
		return
	}
	writeJSON(w, 200, map[string]string{"status": "ok"})
}

func (s *Server) register(w http.ResponseWriter, r *http.Request) {
	if !s.checkOrigin(w, r) {
		return
	}
	var in struct {
		Name     string `json:"name"`
		Email    string `json:"email"`
		Company  string `json:"company"`
		Password string `json:"password"`
	}
	if !decode(w, r, &in) {
		return
	}
	in.Email = strings.ToLower(strings.TrimSpace(in.Email))
	in.Name, in.Company = strings.TrimSpace(in.Name), strings.TrimSpace(in.Company)
	if in.Name == "" || in.Company == "" || !strings.Contains(in.Email, "@") || len(in.Password) < 12 {
		writeJSON(w, 400, map[string]string{"error": "name, company, valid email, and a password of at least 12 characters are required"})
		return
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(in.Password), bcrypt.DefaultCost)
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": "unable to create account"})
		return
	}
	tx, err := s.db.Begin(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	defer tx.Rollback(r.Context())
	tenantID, userID := newUUID(), newUUID()
	if _, err = tx.Exec(r.Context(), `INSERT INTO tenants(id,name) VALUES($1,$2)`, tenantID, in.Company); err != nil {
		if isUnique(err) {
			writeJSON(w, 409, map[string]string{"error": "an account with that email already exists"})
		} else {
			writeError(w, err)
		}
		return
	}
	if _, err = tx.Exec(r.Context(), `INSERT INTO users(id,tenant_id,email,display_name,password_hash,role) VALUES($1,$2,$3,$4,$5,'operator')`, userID, tenantID, in.Email, in.Name, string(hash)); err != nil {
		writeError(w, err)
		return
	}
	if err = seedWorkspace(r.Context(), tx, tenantID, userID); err != nil {
		writeError(w, err)
		return
	}
	if _, err = tx.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) VALUES($1,$2,'account.created','user',$3)`, tenantID, userID, userID); err != nil {
		writeError(w, err)
		return
	}
	if err = tx.Commit(r.Context()); err != nil {
		writeError(w, err)
		return
	}
	if !s.createSession(w, r, userID) {
		return
	}
	writeJSON(w, 201, map[string]any{"id": userID, "tenant_id": tenantID, "email": in.Email, "display_name": in.Name, "role": "operator"})
}

func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	if !s.checkOrigin(w, r) {
		return
	}
	var in struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if !decode(w, r, &in) {
		return
	}
	var userID, hash string
	err := s.db.QueryRow(r.Context(), `SELECT id,password_hash FROM users WHERE email=$1`, strings.ToLower(strings.TrimSpace(in.Email))).Scan(&userID, &hash)
	if err != nil || bcrypt.CompareHashAndPassword([]byte(hash), []byte(in.Password)) != nil {
		writeJSON(w, 401, map[string]string{"error": "email or password is incorrect"})
		return
	}
	if !s.createSession(w, r, userID) {
		return
	}
	_, _ = s.db.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) SELECT tenant_id,id,'session.created','user',id::text FROM users WHERE id=$1`, userID)
	writeJSON(w, 200, map[string]string{"status": "authenticated"})
}

func (s *Server) createSession(w http.ResponseWriter, r *http.Request, userID string) bool {
	token := randomToken(32)
	digest := sha256.Sum256([]byte(token))
	_, err := s.db.Exec(r.Context(), `INSERT INTO sessions(token_hash,user_id,expires_at) VALUES($1,$2,now()+interval '12 hours')`, digest[:], userID)
	if err != nil {
		writeError(w, err)
		return false
	}
	http.SetCookie(w, &http.Cookie{Name: sessionCookie, Value: token, Path: "/", HttpOnly: true, Secure: true, SameSite: http.SameSiteStrictMode, MaxAge: 43200})
	return true
}

func (s *Server) logout(w http.ResponseWriter, r *http.Request) {
	if !s.checkOrigin(w, r) {
		return
	}
	if c, err := r.Cookie(sessionCookie); err == nil {
		digest := sha256.Sum256([]byte(c.Value))
		_, _ = s.db.Exec(r.Context(), `DELETE FROM sessions WHERE token_hash=$1`, digest[:])
	}
	http.SetCookie(w, &http.Cookie{Name: sessionCookie, Value: "", Path: "/", HttpOnly: true, Secure: true, SameSite: http.SameSiteStrictMode, MaxAge: -1})
	w.WriteHeader(204)
}

func (s *Server) localAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, err := r.Cookie(sessionCookie)
		if err != nil {
			writeJSON(w, 401, map[string]string{"error": "authentication required"})
			return
		}
		digest := sha256.Sum256([]byte(c.Value))
		var p principal
		err = s.db.QueryRow(r.Context(), `SELECT u.id,u.tenant_id,u.email,u.display_name,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=$1 AND s.expires_at>now()`, digest[:]).Scan(&p.UserID, &p.TenantID, &p.Email, &p.DisplayName, &p.Role)
		if err != nil {
			writeJSON(w, 401, map[string]string{"error": "session expired"})
			return
		}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), principalKey{}, p)))
	})
}

type principalKey struct{}

func current(r *http.Request) principal {
	p, _ := r.Context().Value(principalKey{}).(principal)
	return p
}

func (s *Server) sameOrigin(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.checkOrigin(w, r) {
			next.ServeHTTP(w, r)
		}
	})
}
func (s *Server) checkOrigin(w http.ResponseWriter, r *http.Request) bool {
	if r.Header.Get("Origin") != s.publicOrigin {
		writeJSON(w, 403, map[string]string{"error": "request origin rejected"})
		return false
	}
	return true
}

func (s *Server) me(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	var archiveEnabled bool
	if err := s.db.QueryRow(r.Context(), `SELECT EXISTS(SELECT 1 FROM worker_service_identities WHERE tenant_id=$1 AND enabled)`, p.TenantID).Scan(&archiveEnabled); err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, 200, map[string]any{"id": p.UserID, "tenant_id": p.TenantID, "email": p.Email, "display_name": p.DisplayName, "role": p.Role, "archive_enabled": archiveEnabled})
}

func (s *Server) dashboard(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	cacheKey := "dashboard:" + p.TenantID
	if cached, err := s.cache.Get(r.Context(), cacheKey).Bytes(); err == nil {
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_, _ = w.Write(cached)
		return
	}
	var assets, openIncidents, reports int
	_ = s.db.QueryRow(r.Context(), `SELECT count(*) FROM assets WHERE tenant_id=$1`, p.TenantID).Scan(&assets)
	_ = s.db.QueryRow(r.Context(), `SELECT count(*) FROM incidents WHERE tenant_id=$1 AND status<>'resolved'`, p.TenantID).Scan(&openIncidents)
	_ = s.db.QueryRow(r.Context(), `SELECT count(*) FROM reports WHERE tenant_id=$1`, p.TenantID).Scan(&reports)
	rows, err := s.db.Query(r.Context(), `SELECT a.id,a.asset_code,a.name,a.category,a.location,a.operating_state,COALESCE((SELECT t.temperature_c FROM telemetry t WHERE t.asset_id=a.id ORDER BY t.observed_at DESC LIMIT 1),0),COALESCE((SELECT t.pressure_bar FROM telemetry t WHERE t.asset_id=a.id ORDER BY t.observed_at DESC LIMIT 1),0),COALESCE((SELECT t.vibration_mm_s FROM telemetry t WHERE t.asset_id=a.id ORDER BY t.observed_at DESC LIMIT 1),0) FROM assets a WHERE a.tenant_id=$1 ORDER BY a.asset_code`, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	defer rows.Close()
	assetsOut := make([]map[string]any, 0)
	for rows.Next() {
		var id, code, name, category, location, state string
		var temp, pressure, vibration float64
		if err = rows.Scan(&id, &code, &name, &category, &location, &state, &temp, &pressure, &vibration); err != nil {
			writeError(w, err)
			return
		}
		assetsOut = append(assetsOut, map[string]any{"id": id, "code": code, "name": name, "category": category, "location": location, "state": state, "temperature_c": temp, "pressure_bar": pressure, "vibration_mm_s": vibration})
	}
	result := map[string]any{"assets_total": assets, "open_incidents": openIncidents, "reports_total": reports, "assets": assetsOut}
	if body, marshalErr := json.Marshal(result); marshalErr == nil {
		_ = s.cache.Set(r.Context(), cacheKey, body, 15*time.Second).Err()
	}
	writeJSON(w, 200, result)
}

func (s *Server) invalidateDashboard(ctx context.Context, tenantID string) {
	_ = s.cache.Del(ctx, "dashboard:"+tenantID).Err()
}

func (s *Server) assets(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	rows, err := s.db.Query(r.Context(), `SELECT id,asset_code,name,category,location,operating_state FROM assets WHERE tenant_id=$1 ORDER BY asset_code`, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	defer rows.Close()
	out := make([]map[string]string, 0)
	for rows.Next() {
		var id, code, name, category, location, state string
		if err = rows.Scan(&id, &code, &name, &category, &location, &state); err != nil {
			writeError(w, err)
			return
		}
		out = append(out, map[string]string{"id": id, "code": code, "name": name, "category": category, "location": location, "state": state})
	}
	writeJSON(w, 200, out)
}

func (s *Server) createAsset(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	var in struct {
		Code     string `json:"code"`
		Name     string `json:"name"`
		Category string `json:"category"`
		Location string `json:"location"`
	}
	if !decode(w, r, &in) {
		return
	}
	in.Code, in.Name, in.Category, in.Location = strings.TrimSpace(in.Code), strings.TrimSpace(in.Name), strings.TrimSpace(in.Category), strings.TrimSpace(in.Location)
	if in.Code == "" || in.Name == "" || in.Category == "" || in.Location == "" || len(in.Code) > 32 || len(in.Name) > 120 || len(in.Location) > 120 {
		writeJSON(w, 400, map[string]string{"error": "code, name, category, and location are required"})
		return
	}
	id := newUUID()
	tx, err := s.db.Begin(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	defer tx.Rollback(r.Context())
	if _, err = tx.Exec(r.Context(), `INSERT INTO assets(id,tenant_id,asset_code,name,category,location) VALUES($1,$2,$3,$4,$5,$6)`, id, p.TenantID, in.Code, in.Name, in.Category, in.Location); err != nil {
		if isUnique(err) {
			writeJSON(w, 409, map[string]string{"error": "an asset with that code already exists"})
		} else {
			writeError(w, err)
		}
		return
	}
	for point := 47; point >= 0; point-- {
		at := time.Now().UTC().Add(-time.Duration(point) * 30 * time.Minute)
		phase := float64(point) * 0.21
		_, err = tx.Exec(r.Context(), `INSERT INTO telemetry(tenant_id,asset_id,observed_at,temperature_c,pressure_bar,vibration_mm_s,throughput_pct) VALUES($1,$2,$3,$4,$5,$6,$7)`, p.TenantID, id, at, 58+4*math.Sin(phase), 7.2+0.25*math.Sin(phase*0.7), 1.8+0.3*math.Sin(phase*1.3), 76+12*math.Sin(phase*0.43))
		if err != nil {
			writeError(w, err)
			return
		}
	}
	_, err = tx.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) VALUES($1,$2,'asset.created','asset',$3)`, p.TenantID, p.UserID, id)
	if err != nil {
		writeError(w, err)
		return
	}
	if err = tx.Commit(r.Context()); err != nil {
		writeError(w, err)
		return
	}
	s.invalidateDashboard(r.Context(), p.TenantID)
	writeJSON(w, 201, map[string]string{"id": id, "code": in.Code, "name": in.Name})
}

func (s *Server) telemetry(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	id := r.PathValue("id")
	hours := 24
	if v := r.URL.Query().Get("hours"); v != "" {
		n, e := strconv.Atoi(v)
		if e != nil || n < 1 || n > 168 {
			writeJSON(w, 400, map[string]string{"error": "hours must be between 1 and 168"})
			return
		}
		hours = n
	}
	rows, err := s.db.Query(r.Context(), `SELECT observed_at,temperature_c,pressure_bar,vibration_mm_s,throughput_pct FROM telemetry WHERE tenant_id=$1 AND asset_id=$2 AND observed_at>=now()-($3::int * interval '1 hour') ORDER BY observed_at`, p.TenantID, id, hours)
	if err != nil {
		writeError(w, err)
		return
	}
	defer rows.Close()
	out := make([]map[string]any, 0)
	for rows.Next() {
		var at time.Time
		var t, pr, v, th float64
		if err = rows.Scan(&at, &t, &pr, &v, &th); err != nil {
			writeError(w, err)
			return
		}
		out = append(out, map[string]any{"observed_at": at, "temperature_c": t, "pressure_bar": pr, "vibration_mm_s": v, "throughput_pct": th})
	}
	writeJSON(w, 200, out)
}

func (s *Server) listIncidents(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	rows, err := s.db.Query(r.Context(), `SELECT i.id,i.title,i.description,i.severity,i.status,i.created_at,a.asset_code,a.name FROM incidents i JOIN assets a ON a.id=i.asset_id WHERE i.tenant_id=$1 ORDER BY i.created_at DESC`, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	defer rows.Close()
	out := make([]map[string]any, 0)
	for rows.Next() {
		var id, title, description, severity, status, code, name string
		var created time.Time
		if err = rows.Scan(&id, &title, &description, &severity, &status, &created, &code, &name); err != nil {
			writeError(w, err)
			return
		}
		out = append(out, map[string]any{"id": id, "title": title, "description": description, "severity": severity, "status": status, "created_at": created, "asset_code": code, "asset_name": name})
	}
	writeJSON(w, 200, out)
}

func (s *Server) createIncident(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	var in struct {
		AssetID     string `json:"asset_id"`
		Title       string `json:"title"`
		Description string `json:"description"`
		Severity    string `json:"severity"`
	}
	if !decode(w, r, &in) {
		return
	}
	in.Title = strings.TrimSpace(in.Title)
	if in.Title == "" || !oneOf(in.Severity, "low", "medium", "high", "critical") {
		writeJSON(w, 400, map[string]string{"error": "title and valid severity are required"})
		return
	}
	id := newUUID()
	tag, err := s.db.Exec(r.Context(), `INSERT INTO incidents(id,tenant_id,asset_id,title,description,severity,created_by) SELECT $1,$2,a.id,$4,$5,$6,$7 FROM assets a WHERE a.id=$3 AND a.tenant_id=$2`, id, p.TenantID, in.AssetID, in.Title, in.Description, in.Severity, p.UserID)
	if err != nil {
		writeError(w, err)
		return
	}
	if tag.RowsAffected() == 0 {
		writeJSON(w, 404, map[string]string{"error": "asset not found"})
		return
	}
	_, err = s.db.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) VALUES($1,$2,'incident.created','incident',$3)`, p.TenantID, p.UserID, id)
	if err != nil {
		writeError(w, err)
		return
	}
	_, _ = s.db.Exec(r.Context(), `INSERT INTO notifications(id,tenant_id,user_id,message) VALUES($1,$2,NULL,$3)`, newUUID(), p.TenantID, "New "+in.Severity+" maintenance incident: "+in.Title)
	s.invalidateDashboard(r.Context(), p.TenantID)
	writeJSON(w, 201, map[string]string{"id": id, "status": "open"})
}

func (s *Server) updateIncident(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	var in struct {
		Status string `json:"status"`
	}
	if !decode(w, r, &in) {
		return
	}
	if !oneOf(in.Status, "open", "acknowledged", "resolved") {
		writeJSON(w, 400, map[string]string{"error": "invalid incident status"})
		return
	}
	id := r.PathValue("id")
	tag, err := s.db.Exec(r.Context(), `UPDATE incidents SET status=$1,updated_at=now() WHERE id=$2 AND tenant_id=$3`, in.Status, id, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	if tag.RowsAffected() == 0 {
		writeJSON(w, 404, map[string]string{"error": "incident not found"})
		return
	}
	_, _ = s.db.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) VALUES($1,$2,'incident.status_changed','incident',$3)`, p.TenantID, p.UserID, id)
	s.invalidateDashboard(r.Context(), p.TenantID)
	writeJSON(w, 200, map[string]string{"id": id, "status": in.Status})
}

func (s *Server) notifications(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	rows, err := s.db.Query(r.Context(), `SELECT id,message,read_at,created_at FROM notifications WHERE tenant_id=$1 AND (user_id IS NULL OR user_id=$2) ORDER BY created_at DESC LIMIT 50`, p.TenantID, p.UserID)
	if err != nil {
		writeError(w, err)
		return
	}
	defer rows.Close()
	out := make([]map[string]any, 0)
	for rows.Next() {
		var id, msg string
		var readAt *time.Time
		var created time.Time
		if err = rows.Scan(&id, &msg, &readAt, &created); err != nil {
			writeError(w, err)
			return
		}
		out = append(out, map[string]any{"id": id, "message": msg, "read_at": readAt, "created_at": created})
	}
	writeJSON(w, 200, out)
}

func (s *Server) readNotification(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	tag, err := s.db.Exec(r.Context(), `UPDATE notifications SET read_at=now() WHERE id=$1 AND tenant_id=$2 AND (user_id IS NULL OR user_id=$3)`, r.PathValue("id"), p.TenantID, p.UserID)
	if err != nil {
		writeError(w, err)
		return
	}
	if tag.RowsAffected() == 0 {
		writeJSON(w, 404, map[string]string{"error": "notification not found"})
		return
	}
	w.WriteHeader(204)
}

func (s *Server) createReport(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	var in struct {
		Type string `json:"type"`
	}
	if !decode(w, r, &in) {
		return
	}
	if in.Type == "" {
		in.Type = "asset-inventory"
	}
	if !oneOf(in.Type, "asset-inventory", "maintenance-summary", "legacy-archive") {
		writeJSON(w, 400, map[string]string{"error": "unsupported report type"})
		return
	}
	if in.Type == "legacy-archive" {
		var enrolled bool
		if err := s.db.QueryRow(r.Context(), `SELECT EXISTS(SELECT 1 FROM worker_service_identities WHERE tenant_id=$1 AND enabled)`, p.TenantID).Scan(&enrolled); err != nil {
			writeError(w, err)
			return
		}
		if !enrolled {
			writeJSON(w, 403, map[string]string{"error": "workspace is not enrolled in archive migration"})
			return
		}
	}
	id := newUUID()
	_, err := s.db.Exec(r.Context(), `INSERT INTO reports(id,tenant_id,requested_by,report_type) VALUES($1,$2,$3,$4)`, id, p.TenantID, p.UserID, in.Type)
	if err != nil {
		writeError(w, err)
		return
	}
	payload, _ := json.Marshal(map[string]string{"report_id": id})
	if err = s.nats.Publish("aether.reports.requested", payload); err != nil {
		_, _ = s.db.Exec(r.Context(), `UPDATE reports SET status='failed',error='queue unavailable',completed_at=now() WHERE id=$1`, id)
		writeJSON(w, 503, map[string]string{"error": "report queue unavailable"})
		return
	}
	_, _ = s.db.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) VALUES($1,$2,'report.queued','report',$3)`, p.TenantID, p.UserID, id)
	s.invalidateDashboard(r.Context(), p.TenantID)
	writeJSON(w, 202, map[string]string{"id": id, "status": "queued"})
}

func (s *Server) listReports(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	rows, err := s.db.Query(r.Context(), `SELECT id,report_type,status,error,created_at,completed_at FROM reports WHERE tenant_id=$1 ORDER BY created_at DESC`, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	defer rows.Close()
	out := make([]map[string]any, 0)
	for rows.Next() {
		var id, typ, status, problem string
		var created time.Time
		var done *time.Time
		if err = rows.Scan(&id, &typ, &status, &problem, &created, &done); err != nil {
			writeError(w, err)
			return
		}
		out = append(out, map[string]any{"id": id, "type": typ, "status": status, "error": problem, "created_at": created, "completed_at": done})
	}
	writeJSON(w, 200, out)
}

func (s *Server) getReport(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	var content, status, typ string
	err := s.db.QueryRow(r.Context(), `SELECT content,status,report_type FROM reports WHERE id=$1 AND tenant_id=$2`, r.PathValue("id"), p.TenantID).Scan(&content, &status, &typ)
	if err != nil {
		writeJSON(w, 404, map[string]string{"error": "report not found"})
		return
	}
	if status != "complete" {
		writeJSON(w, 202, map[string]any{"status": status})
		return
	}
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", "attachment; filename=\"aether-report-"+typ+".csv\"")
	_, _ = io.WriteString(w, content)
}

func (s *Server) audit(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	rows, err := s.db.Query(r.Context(), `SELECT e.action,e.object_type,e.object_id,e.created_at,COALESCE(u.display_name,'system'),e.detail FROM audit_events e LEFT JOIN users u ON u.id=e.user_id WHERE e.tenant_id=$1 ORDER BY e.created_at DESC LIMIT 100`, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	defer rows.Close()
	out := make([]map[string]any, 0)
	for rows.Next() {
		var action, kind, id, actor string
		var at time.Time
		var detail json.RawMessage
		if err = rows.Scan(&action, &kind, &id, &at, &actor, &detail); err != nil {
			writeError(w, err)
			return
		}
		out = append(out, map[string]any{"action": action, "object_type": kind, "object_id": id, "at": at, "actor": actor, "detail": detail})
	}
	writeJSON(w, 200, out)
}

func (s *Server) docs(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = io.WriteString(w, `<!doctype html><html><head><title>AETHER API</title><style>body{max-width:900px;margin:4rem auto;font:16px system-ui;color:#17252b}code{background:#edf1ef;padding:.2rem .4rem}li{margin:.65rem 0}</style></head><body><h1>AETHER Platform API</h1><p>All requests use the active HTTPS session cookie. Mutations require a same-origin request.</p><ul><li><code>GET /api/dashboard</code> — operating summary</li><li><code>GET /api/assets</code>, <code>GET /api/assets/{id}/telemetry?hours=24</code></li><li><code>GET /api/incidents</code>, <code>POST /api/incidents</code>, <code>PATCH /api/incidents/{id}</code></li><li><code>GET /api/notifications</code></li><li><code>GET /api/reports</code>, <code>POST /api/reports</code>, <code>GET /api/reports/{id}</code></li><li><code>GET /api/audit</code> — includes archived operation provenance</li><li><code>GET /api/team</code>, <code>POST /api/team/invitations</code>, <code>PATCH /api/team/users/{id}</code> — workspace administrators</li></ul><h2>Administrator recovery (compatibility schema 1)</h2><p><code>POST /api/v2/team/recover</code> accepts <code>tenant_uuid</code> (the active workspace), <code>legacy_tenant_no</code> (installation reference), and <code>receipt</code> (64-character administrator handover receipt retained in the historical export). Recovery restores workspace administration for the current account. Each account may redeem a receipt once.</p><h2>Historical exports (compatibility schema 1)</h2><p><code>POST /api/v2/reports/historical</code> accepts <code>tenant_uuid</code> (your current workspace UUID from <code>GET /api/me</code>) and <code>legacy_tenant_no</code> (the numeric installation reference printed on historical exports). The response is a queued report ID; poll the report list and download its CSV when complete.</p><p>The UUID field was added during the 2024 identity migration. Installation references remain in the compatibility contract for archived import clients. Empty archives produce a CSV header with no records.</p><p>Account creation is available on the public platform. Each new workspace starts with ordinary operator access.</p></body></html>`)
}

func (s *Server) runWorker(ctx context.Context) error {
	wake := make(chan struct{}, 1)
	_, err := s.nats.Subscribe("aether.reports.requested", func(_ *nats.Msg) {
		select {
		case wake <- struct{}{}:
		default:
		}
	})
	if err != nil {
		return err
	}
	defer s.nats.Flush()
	log.Print("report worker polling durable report queue")
	ticker := time.NewTicker(750 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-wake:
			if err := s.processOneReport(ctx); err != nil {
				log.Printf("report processing: %v", err)
			}
		case <-ticker.C:
			if err := s.processOneReport(ctx); err != nil {
				log.Printf("report processing: %v", err)
			}
		}
	}
}

func (s *Server) runTelemetry(ctx context.Context) error {
	log.Print("telemetry generator started")
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case at := <-ticker.C:
			if err := s.recordTelemetry(ctx, at.UTC()); err != nil {
				log.Printf("telemetry generation: %v", err)
			}
		}
	}
}

func (s *Server) recordTelemetry(ctx context.Context, at time.Time) error {
	rows, err := s.db.Query(ctx, `SELECT id,tenant_id FROM assets ORDER BY id`)
	if err != nil {
		return err
	}
	type assetRef struct{ id, tenant string }
	assets := make([]assetRef, 0)
	for rows.Next() {
		var a assetRef
		if err = rows.Scan(&a.id, &a.tenant); err != nil {
			rows.Close()
			return err
		}
		assets = append(assets, a)
	}
	rows.Close()
	for i, a := range assets {
		phase := float64(at.Unix()/15+int64(i*11)) * 0.035
		_, err = s.db.Exec(ctx, `INSERT INTO telemetry(tenant_id,asset_id,observed_at,temperature_c,pressure_bar,vibration_mm_s,throughput_pct) VALUES($1,$2,$3,$4,$5,$6,$7)`, a.tenant, a.id, at, 60+4*math.Sin(phase), 7.1+0.3*math.Sin(phase*0.73), 1.9+0.32*math.Sin(phase*1.27), 77+11*math.Sin(phase*0.41))
		if err != nil {
			return err
		}
	}
	return nil
}

func (s *Server) processOneReport(ctx context.Context) error {
	tx, err := s.db.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	var id, tenantID, requestedBy, kind string
	err = tx.QueryRow(ctx, `SELECT id,tenant_id,requested_by,report_type FROM reports WHERE status='queued' OR (status='running' AND lease_until<now()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1`).Scan(&id, &tenantID, &requestedBy, &kind)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil
	}
	if err != nil {
		return err
	}
	// Capture the attempt_count as a lease fence token: a competing worker that
	// reclaims an expired lease increments it, so this owner's later result or
	// failure write is rejected and cannot clobber the reclaiming worker's work.
	var fence int
	if err = tx.QueryRow(ctx, `UPDATE reports SET status='running',lease_until=now()+interval '1 minute',attempt_count=attempt_count+1 WHERE id=$1 RETURNING attempt_count`, id).Scan(&fence); err != nil {
		return err
	}
	if err = tx.Commit(ctx); err != nil {
		return err
	}
	var content string
	if kind == "asset-inventory" {
		content, err = s.assetReport(ctx, tenantID)
	} else if kind == "legacy-history" {
		content, err = s.legacyReport(ctx, id)
	} else if kind == "legacy-archive" {
		content, err = s.archiveReport(ctx, id, tenantID)
	} else {
		content, err = s.maintenanceReport(ctx, tenantID)
	}
	if err != nil {
		// Only the current lease owner may mark the report failed.
		_, updateErr := s.db.Exec(ctx, `UPDATE reports SET status='failed',error='report generation failed',lease_until=NULL,completed_at=now() WHERE id=$1 AND status='running' AND attempt_count=$2`, id, fence)
		if updateErr != nil {
			return updateErr
		}
		return err
	}
	// Record the result and its notification atomically, under the lease fence,
	// so a report never completes without its notification (or vice versa) and a
	// stale owner cannot overwrite a reclaiming worker's result.
	done, err := s.db.Begin(ctx)
	if err != nil {
		return err
	}
	defer done.Rollback(ctx)
	result, err := done.Exec(ctx, `UPDATE reports SET status='complete',content=$1,lease_until=NULL,completed_at=now() WHERE id=$2 AND status='running' AND attempt_count=$3`, content, id, fence)
	if err != nil {
		return err
	}
	if result.RowsAffected() != 1 {
		// Lease lost to a reclaiming worker; let that owner finish and notify.
		return nil
	}
	if _, err = done.Exec(ctx, `INSERT INTO notifications(id,tenant_id,user_id,message) VALUES($1,$2,$3,$4)`, newUUID(), tenantID, requestedBy, "Your AETHER "+kind+" report is ready."); err != nil {
		return err
	}
	return done.Commit(ctx)
}

func (s *Server) assetReport(ctx context.Context, tenantID string) (string, error) {
	rows, err := s.db.Query(ctx, `SELECT asset_code,name,category,location,operating_state FROM assets WHERE tenant_id=$1 ORDER BY asset_code`, tenantID)
	if err != nil {
		return "", err
	}
	defer rows.Close()
	var b strings.Builder
	w := csv.NewWriter(&b)
	_ = w.Write([]string{"asset_code", "name", "category", "location", "state"})
	for rows.Next() {
		var a, bv, c, d, e string
		if err = rows.Scan(&a, &bv, &c, &d, &e); err != nil {
			return "", err
		}
		if err = w.Write([]string{a, bv, c, d, e}); err != nil {
			return "", err
		}
	}
	w.Flush()
	return b.String(), w.Error()
}

func (s *Server) maintenanceReport(ctx context.Context, tenantID string) (string, error) {
	rows, err := s.db.Query(ctx, `SELECT i.title,i.severity,i.status,a.asset_code,i.created_at FROM incidents i JOIN assets a ON a.id=i.asset_id WHERE i.tenant_id=$1 ORDER BY i.created_at DESC`, tenantID)
	if err != nil {
		return "", err
	}
	defer rows.Close()
	var b strings.Builder
	w := csv.NewWriter(&b)
	_ = w.Write([]string{"title", "severity", "status", "asset_code", "created_at"})
	for rows.Next() {
		var a, bv, c, d string
		var at time.Time
		if err = rows.Scan(&a, &bv, &c, &d, &at); err != nil {
			return "", err
		}
		if err = w.Write([]string{a, bv, c, d, at.Format(time.RFC3339)}); err != nil {
			return "", err
		}
	}
	w.Flush()
	return b.String(), w.Error()
}

func seedWorkspace(ctx context.Context, tx pgx.Tx, tenantID, userID string) error {
	type seed struct{ code, name, category, location string }
	items := []seed{{"P-101", "Primary feed pump", "Pump", "North process hall"}, {"C-204", "Compressor train 2", "Compressor", "Utilities block"}, {"HX-018", "Heat exchanger 18", "Heat exchanger", "Recovery line"}}
	for i, a := range items {
		id := newUUID()
		if _, err := tx.Exec(ctx, `INSERT INTO assets(id,tenant_id,asset_code,name,category,location) VALUES($1,$2,$3,$4,$5,$6)`, id, tenantID, a.code, a.name, a.category, a.location); err != nil {
			return err
		}
		for point := 47; point >= 0; point-- {
			at := time.Now().UTC().Add(-time.Duration(point) * 30 * time.Minute)
			phase := float64(point+i*7) * 0.21
			temp := 58 + float64(i*5) + 4*math.Sin(phase)
			pressure := 7.2 + 0.25*math.Sin(phase*0.7)
			vibration := 1.8 + 0.3*math.Sin(phase*1.3)
			throughput := 76 + 12*math.Sin(phase*0.43)
			if _, err := tx.Exec(ctx, `INSERT INTO telemetry(tenant_id,asset_id,observed_at,temperature_c,pressure_bar,vibration_mm_s,throughput_pct) VALUES($1,$2,$3,$4,$5,$6,$7)`, tenantID, id, at, temp, pressure, vibration, throughput); err != nil {
				return err
			}
		}
	}
	if _, err := tx.Exec(ctx, `INSERT INTO notifications(id,tenant_id,user_id,message) VALUES($1,$2,$3,'Workspace initialized. Review asset telemetry and maintenance incidents to begin.')`, newUUID(), tenantID, userID); err != nil {
		return err
	}
	return nil
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) { s.Handler().ServeHTTP(w, r) }

func Run() error {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	mode := env("AETHER_MODE", "api")
	if mode == "migrate" {
		return migrate(ctx)
	}
	server, err := New(ctx)
	if err != nil {
		return err
	}
	defer server.Close()
	if mode == "worker" {
		return server.runWorker(ctx)
	}
	if mode == "telemetry" {
		return server.runTelemetry(ctx)
	}
	addr := env("LISTEN_ADDR", ":8080")
	handler := server.Handler()
	if mode == "auth" {
		handler = server.AuthHandler()
	}
	if mode == "legacy" {
		handler = server.LegacyHandler()
	}
	httpServer := &http.Server{Addr: addr, Handler: handler, ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 60 * time.Second}
	log.Printf("AETHER %s listening on %s", mode, addr)
	return httpServer.ListenAndServe()
}

func decode(w http.ResponseWriter, r *http.Request, v any) bool {
	r.Body = http.MaxBytesReader(w, r.Body, 1<<20)
	d := json.NewDecoder(r.Body)
	d.DisallowUnknownFields()
	if err := d.Decode(v); err != nil {
		writeJSON(w, 400, map[string]string{"error": "invalid request body"})
		return false
	}
	return true
}
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func writeError(w http.ResponseWriter, err error) {
	log.Printf("request error: %v", err)
	writeJSON(w, 500, map[string]string{"error": "request could not be completed"})
}
func newUUID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	h := hex.EncodeToString(b)
	return h[:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:]
}
func randomToken(n int) string {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}
func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
func oneOf(v string, allowed ...string) bool {
	for _, x := range allowed {
		if v == x {
			return true
		}
	}
	return false
}
func isUnique(err error) bool { return strings.Contains(strings.ToLower(err.Error()), "unique") }

func securityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "same-origin")
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; connect-src 'self' wss://aether.blackveil.test; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
		next.ServeHTTP(w, r)
	})
}

var _ io.Reader
var _ = strconv.IntSize
