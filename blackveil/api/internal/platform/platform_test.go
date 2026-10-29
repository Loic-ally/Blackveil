package platform

import (
	"net/http"
	"net/http/httptest"
	"regexp"
	"testing"
)

func TestNewUUIDIsVersionFour(t *testing.T) {
	got := newUUID()
	pattern := regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)
	if !pattern.MatchString(got) {
		t.Fatalf("newUUID() = %q, not a canonical random UUID v4", got)
	}
}

func TestRandomTokenHasExpectedEntropyEncoding(t *testing.T) {
	got := randomToken(32)
	if len(got) != 64 {
		t.Fatalf("token length = %d, want 64 hexadecimal characters", len(got))
	}
	if _, err := regexp.Compile(`^[0-9a-f]{64}$`); err != nil {
		t.Fatal(err)
	}
	if matched, _ := regexp.MatchString(`^[0-9a-f]{64}$`, got); !matched {
		t.Fatalf("token %q is not lowercase hex", got)
	}
}

func TestOneOfIsExact(t *testing.T) {
	if !oneOf("acknowledged", "open", "acknowledged", "resolved") {
		t.Fatal("expected known status to be accepted")
	}
	if oneOf("Acknowledged", "open", "acknowledged", "resolved") {
		t.Fatal("status comparison must not silently normalize case")
	}
}

func TestSecurityHeaders(t *testing.T) {
	called := false
	handler := securityHeaders(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		called = true
		w.WriteHeader(http.StatusNoContent)
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if !called || recorder.Code != http.StatusNoContent {
		t.Fatal("wrapped handler did not run")
	}
	if got := recorder.Header().Get("X-Content-Type-Options"); got != "nosniff" {
		t.Fatalf("X-Content-Type-Options = %q", got)
	}
	if got := recorder.Header().Get("Content-Security-Policy"); got == "" {
		t.Fatal("Content-Security-Policy was not set")
	}
}
