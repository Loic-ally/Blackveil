package platform

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5"
)

const (
	finalProofMaxBody   = 8 << 10
	finalProofRateLimit = 12
	finalProofWindow    = time.Minute
)

type finalProofBundle struct {
	Attestation string `json:"attestation"`
	VeilTag     string `json:"veil_tag"`
	Manifest    string `json:"manifest"`
	PivotNumber int64  `json:"pivot_number"`
	TenantUUID  string `json:"tenant_uuid"`
}

func (b finalProofBundle) complete() bool {
	return b.Attestation != "" && b.VeilTag != "" && b.Manifest != "" && b.PivotNumber != 0 && b.TenantUUID != ""
}

func (s *Server) submitFinalProof(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	if p.Role != "system_admin" {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "final submission is not enabled for this identity"})
		return
	}
	if !s.allowFinalProof(r.Context(), p.UserID) {
		writeJSON(w, http.StatusTooManyRequests, map[string]string{"error": "too many submissions; try again shortly"})
		return
	}

	if flag, err := s.finalProofFlag(r.Context(), p.UserID, p.TenantID); err == nil {
		writeJSON(w, http.StatusOK, map[string]any{"status": "complete", "flag": flag})
		return
	} else if !errors.Is(err, pgx.ErrNoRows) {
		writeJSON(w, 503, map[string]string{"error": "completion status temporarily unavailable"})
		return
	}

	var in struct {
		Proof finalProofBundle `json:"proof"`
	}
	r.Body = http.MaxBytesReader(w, r.Body, finalProofMaxBody)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&in); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid proof submission"})
		return
	}
	if decoder.Decode(&struct{}{}) != io.EOF {
		writeJSON(w, 400, map[string]string{"error": "invalid proof submission"})
		return
	}
	if !in.Proof.complete() {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "proof is missing required fields"})
		return
	}

	result, err := s.validateFinalProof(r.Context(), in.Proof)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "final validation is temporarily unavailable"})
		return
	}
	if !result.BlackVeil {
		writeJSON(w, http.StatusOK, map[string]any{"status": "incomplete", "error": "proof rejected"})
		return
	}

	canonical, _ := json.Marshal(in.Proof)
	digest := sha256.Sum256(canonical)
	_, err = s.db.Exec(r.Context(),
		`INSERT INTO final_proof_completions(user_id,tenant_id,proof_sha256,flag) VALUES($1,$2,$3,$4)
		 ON CONFLICT (user_id) DO NOTHING`,
		p.UserID, p.TenantID, digest[:], result.Flag)
	if err != nil {
		writeError(w, err)
		return
	}
	_, _ = s.db.Exec(r.Context(),
		`INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) VALUES($1,$2,'lab.final_proof.completed','challenge','black-veil')`,
		p.TenantID, p.UserID)
	writeJSON(w, http.StatusOK, map[string]any{"status": "complete", "flag": result.Flag})
}

func (s *Server) finalProofStatus(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	flag, err := s.finalProofFlag(r.Context(), p.UserID, p.TenantID)
	if errors.Is(err, pgx.ErrNoRows) {
		writeJSON(w, 200, map[string]any{"status": "pending"})
		return
	}
	if err != nil {
		writeJSON(w, 503, map[string]string{"error": "completion status temporarily unavailable"})
		return
	}
	writeJSON(w, 200, map[string]any{"status": "complete", "flag": flag})
}

func (s *Server) finalProofFlag(ctx context.Context, userID, tenantID string) (string, error) {
	var flag string
	err := s.db.QueryRow(ctx, `SELECT flag FROM final_proof_completions WHERE user_id=$1 AND tenant_id=$2`, userID, tenantID).Scan(&flag)
	return flag, err
}

func (s *Server) allowFinalProof(ctx context.Context, userID string) bool {
	count, err := s.cache.Eval(ctx, `local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n`, []string{"finalproof:rate:" + userID}, int(finalProofWindow.Seconds())).Int64()
	return err == nil && count <= finalProofRateLimit
}

type validatorResult struct {
	BlackVeil bool     `json:"black_veil"`
	Flag      string   `json:"flag"`
	Missing   []string `json:"missing"`
}

func (s *Server) validateFinalProof(ctx context.Context, proof finalProofBundle) (validatorResult, error) {
	body, err := json.Marshal(proof)
	if err != nil {
		return validatorResult{}, err
	}
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, s.validatorURL+"/validate", bytes.NewReader(body))
	if err != nil {
		return validatorResult{}, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer "+s.validatorToken)
	response, err := s.validatorClient.Do(request)
	if err != nil {
		return validatorResult{}, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return validatorResult{}, errors.New("validator rejected the request")
	}
	var result validatorResult
	if err := json.NewDecoder(http.MaxBytesReader(nil, response.Body, 4096)).Decode(&result); err != nil {
		return validatorResult{}, err
	}
	if result.BlackVeil && result.Flag == "" {
		return validatorResult{}, errors.New("validator missing reward")
	}
	return result, nil
}
