package platform

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestFinalProofBundleComplete(t *testing.T) {
	full := finalProofBundle{Attestation: "a", VeilTag: "veil/v0", Manifest: "deploy-4102", PivotNumber: 4102, TenantUUID: "u"}
	if !full.complete() {
		t.Fatal("complete bundle reported incomplete")
	}
	for _, missing := range []finalProofBundle{
		{VeilTag: "veil/v0", Manifest: "deploy-4102", PivotNumber: 4102, TenantUUID: "u"},
		{Attestation: "a", Manifest: "deploy-4102", PivotNumber: 4102, TenantUUID: "u"},
		{Attestation: "a", VeilTag: "veil/v0", PivotNumber: 4102, TenantUUID: "u"},
		{Attestation: "a", VeilTag: "veil/v0", Manifest: "deploy-4102", TenantUUID: "u"},
		{Attestation: "a", VeilTag: "veil/v0", Manifest: "deploy-4102", PivotNumber: 4102},
	} {
		if missing.complete() {
			t.Fatalf("incomplete bundle reported complete: %+v", missing)
		}
	}
}

func TestValidateFinalProofForwardsAndParses(t *testing.T) {
	var gotPath, gotBody string
	validator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		var b finalProofBundle
		_ = json.NewDecoder(r.Body).Decode(&b)
		gotBody = b.Manifest
		if b.Manifest == "deploy-4102" {
			_ = json.NewEncoder(w).Encode(validatorResult{BlackVeil: true, Flag: "BV{ok}"})
		} else {
			_ = json.NewEncoder(w).Encode(validatorResult{BlackVeil: false, Missing: []string{"manifest"}})
		}
	}))
	defer validator.Close()

	s := &Server{validatorURL: validator.URL, validatorClient: validator.Client()}

	ok, err := s.validateFinalProof(context.Background(),
		finalProofBundle{Attestation: "a", VeilTag: "veil/v0", Manifest: "deploy-4102", PivotNumber: 4102, TenantUUID: "u"})
	if err != nil || !ok.BlackVeil || ok.Flag != "BV{ok}" {
		t.Fatalf("expected success, got %+v err=%v", ok, err)
	}
	if gotPath != "/validate" || gotBody != "deploy-4102" {
		t.Fatalf("validator not called correctly: path=%q manifest=%q", gotPath, gotBody)
	}

	bad, err := s.validateFinalProof(context.Background(),
		finalProofBundle{Attestation: "a", VeilTag: "veil/v0", Manifest: "deploy-9999", PivotNumber: 4102, TenantUUID: "u"})
	if err != nil || bad.BlackVeil || len(bad.Missing) != 1 {
		t.Fatalf("expected reject with missing, got %+v err=%v", bad, err)
	}
}

func TestValidateFinalProofTimeoutIsError(t *testing.T) {
	validator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		time.Sleep(200 * time.Millisecond)
		_ = json.NewEncoder(w).Encode(validatorResult{BlackVeil: true, Flag: "BV{late}"})
	}))
	defer validator.Close()
	s := &Server{validatorURL: validator.URL, validatorClient: &http.Client{Timeout: 20 * time.Millisecond}}
	if _, err := s.validateFinalProof(context.Background(),
		finalProofBundle{Attestation: "a", VeilTag: "veil/v0", Manifest: "deploy-4102", PivotNumber: 4102, TenantUUID: "u"}); err == nil {
		t.Fatal("expected timeout error, got nil")
	}
}
