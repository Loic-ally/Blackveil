package platform

import (
	"crypto/sha256"
	"net/http"
	"strings"
	"time"

	"golang.org/x/crypto/bcrypt"
)

func teamAdmin(w http.ResponseWriter, r *http.Request) bool {
	if !oneOf(current(r).Role, "tenant_admin", "system_admin") {
		writeJSON(w, 403, map[string]string{"error": "workspace administrator access required"})
		return false
	}
	return true
}

func (s *Server) team(w http.ResponseWriter, r *http.Request) {
	if !teamAdmin(w, r) {
		return
	}
	p := current(r)
	rows, err := s.db.Query(r.Context(), `SELECT id,email,display_name,role FROM users WHERE tenant_id=$1 ORDER BY created_at`, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	users := []map[string]string{}
	for rows.Next() {
		var id, email, name, role string
		if err = rows.Scan(&id, &email, &name, &role); err != nil {
			rows.Close()
			writeError(w, err)
			return
		}
		users = append(users, map[string]string{"id": id, "email": email, "name": name, "role": role})
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		writeError(w, err)
		return
	}
	rows, err = s.db.Query(r.Context(), `SELECT id,email,role,expires_at,accepted_at,revoked_at FROM invitations WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 100`, p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	defer rows.Close()
	invites := []map[string]any{}
	for rows.Next() {
		var id, email, role string
		var expires time.Time
		var accepted, revoked *time.Time
		if err = rows.Scan(&id, &email, &role, &expires, &accepted, &revoked); err != nil {
			writeError(w, err)
			return
		}
		invites = append(invites, map[string]any{"id": id, "email": email, "role": role, "expires_at": expires, "accepted_at": accepted, "revoked_at": revoked})
	}
	if err = rows.Err(); err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, 200, map[string]any{"users": users, "invitations": invites})
}

func (s *Server) invite(w http.ResponseWriter, r *http.Request) {
	if !teamAdmin(w, r) {
		return
	}
	p := current(r)
	var in struct {
		Email string `json:"email"`
		Role  string `json:"role"`
	}
	if !decode(w, r, &in) {
		return
	}
	in.Email = strings.ToLower(strings.TrimSpace(in.Email))
	if !strings.Contains(in.Email, "@") || !oneOf(in.Role, "operator", "maintenance", "tenant_admin") {
		writeJSON(w, 400, map[string]string{"error": "valid email and workspace role required"})
		return
	}
	token := randomToken(32)
	digest := sha256.Sum256([]byte(token))
	id := newUUID()
	tx, err := s.db.Begin(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	defer tx.Rollback(r.Context())
	_, err = tx.Exec(r.Context(), `INSERT INTO invitations(id,tenant_id,email,role,token_hash,created_by) VALUES($1,$2,$3,$4,$5,$6)`, id, p.TenantID, in.Email, in.Role, digest[:], p.UserID)
	if err == nil {
		_, err = tx.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) VALUES($1,$2,'invitation.created','invitation',$3)`, p.TenantID, p.UserID, id)
	}
	if err == nil {
		err = tx.Commit(r.Context())
	}
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, 201, map[string]string{"id": id, "url": s.publicOrigin + "/join#" + token})
}

func (s *Server) revokeInvite(w http.ResponseWriter, r *http.Request) {
	if !teamAdmin(w, r) {
		return
	}
	result, err := s.db.Exec(r.Context(), `WITH revoked AS (
		UPDATE invitations SET revoked_at=now() WHERE id=$1 AND tenant_id=$2 AND accepted_at IS NULL AND revoked_at IS NULL RETURNING id
	) INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id)
	SELECT $2,$3,'invitation.revoked','invitation',id::text FROM revoked`, r.PathValue("id"), current(r).TenantID, current(r).UserID)
	if err != nil {
		writeError(w, err)
		return
	}
	if result.RowsAffected() != 1 {
		writeJSON(w, 404, map[string]string{"error": "pending invitation not found"})
		return
	}
	w.WriteHeader(204)
}

func (s *Server) changeRole(w http.ResponseWriter, r *http.Request) {
	if !teamAdmin(w, r) {
		return
	}
	p := current(r)
	var in struct {
		Role string `json:"role"`
	}
	if !decode(w, r, &in) {
		return
	}
	if !oneOf(in.Role, "operator", "maintenance", "tenant_admin") {
		writeJSON(w, 400, map[string]string{"error": "unsupported workspace role"})
		return
	}
	if r.PathValue("id") == p.UserID {
		writeJSON(w, 409, map[string]string{"error": "another administrator must change your role"})
		return
	}
	tx, err := s.db.Begin(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	defer tx.Rollback(r.Context())
	// Serialize role decisions within the workspace, and re-check the actor under the lock.
	_, err = tx.Exec(r.Context(), `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, p.TenantID)
	var actorRole string
	if err == nil {
		err = tx.QueryRow(r.Context(), `SELECT role FROM users WHERE id=$1 AND tenant_id=$2`, p.UserID, p.TenantID).Scan(&actorRole)
	}
	if err != nil {
		writeError(w, err)
		return
	}
	if !oneOf(actorRole, "tenant_admin", "system_admin") {
		writeJSON(w, 403, map[string]string{"error": "administrator access revoked"})
		return
	}
	result, err := tx.Exec(r.Context(), `UPDATE users SET role=$1 WHERE id=$2 AND tenant_id=$3 AND role<>'system_admin'`, in.Role, r.PathValue("id"), p.TenantID)
	if err != nil {
		writeError(w, err)
		return
	}
	if result.RowsAffected() != 1 {
		writeJSON(w, 404, map[string]string{"error": "editable workspace user not found"})
		return
	}
	_, err = tx.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id,detail) VALUES($1,$2,'user.role_changed','user',$3,jsonb_build_object('role',$4::text))`, p.TenantID, p.UserID, r.PathValue("id"), in.Role)
	if err == nil {
		err = tx.Commit(r.Context())
	}
	if err != nil {
		writeError(w, err)
		return
	}
	w.WriteHeader(204)
}

func (s *Server) acceptInvite(w http.ResponseWriter, r *http.Request) {
	if !s.checkOrigin(w, r) {
		return
	}
	var in struct {
		Token    string `json:"token"`
		Email    string `json:"email"`
		Name     string `json:"name"`
		Password string `json:"password"`
	}
	if !decode(w, r, &in) {
		return
	}
	in.Email = strings.ToLower(strings.TrimSpace(in.Email))
	in.Name = strings.TrimSpace(in.Name)
	if len(in.Token) != 64 || in.Name == "" || len(in.Password) < 12 || len(in.Password) > 72 {
		writeJSON(w, 400, map[string]string{"error": "valid invitation, name and 12–72 character password required"})
		return
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(in.Password), bcrypt.DefaultCost)
	if err != nil {
		writeError(w, err)
		return
	}
	tx, err := s.db.Begin(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	defer tx.Rollback(r.Context())
	digest := sha256.Sum256([]byte(in.Token))
	var tenant, role, inviteID string
	err = tx.QueryRow(r.Context(), `SELECT id,tenant_id,role FROM invitations WHERE token_hash=$1 AND email=$2 AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>now() FOR UPDATE`, digest[:], in.Email).Scan(&inviteID, &tenant, &role)
	if err != nil {
		writeJSON(w, 403, map[string]string{"error": "invitation is invalid or unavailable"})
		return
	}
	id := newUUID()
	_, err = tx.Exec(r.Context(), `INSERT INTO users(id,tenant_id,email,display_name,password_hash,role) VALUES($1,$2,$3,$4,$5,$6)`, id, tenant, in.Email, in.Name, string(hash), role)
	if err != nil {
		if isUnique(err) {
			writeJSON(w, 409, map[string]string{"error": "account already exists"})
		} else {
			writeError(w, err)
		}
		return
	}
	_, err = tx.Exec(r.Context(), `UPDATE invitations SET accepted_at=now() WHERE id=$1`, inviteID)
	if err == nil {
		_, err = tx.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) VALUES($1,$2,'invitation.accepted','invitation',$3)`, tenant, id, inviteID)
	}
	if err == nil {
		err = tx.Commit(r.Context())
	}
	if err != nil {
		writeError(w, err)
		return
	}
	if !s.createSession(w, r, id) {
		return
	}
	writeJSON(w, 201, map[string]string{"id": id, "tenant_id": tenant, "role": role})
}
