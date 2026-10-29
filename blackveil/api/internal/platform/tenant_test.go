package platform

import "testing"

func TestMigrationLookupNumber(t *testing.T) {
	const requested, canonical = 4101, 4102
	// Challenge mode trusts the caller-supplied number: the Stage 03 flaw.
	if got, ok := migrationLookupNumber("challenge", requested, canonical); !ok || got != requested {
		t.Fatalf("challenge: got (%d,%v), want (%d,true)", got, ok, requested)
	}
	// Patched mode ignores the request and binds to the caller's own tenant.
	if got, ok := migrationLookupNumber("patched", requested, canonical); !ok || got != canonical {
		t.Fatalf("patched: got (%d,%v), want (%d,true)", got, ok, canonical)
	}
	// Unknown mode fails closed so the handler cannot disclose anything.
	if _, ok := migrationLookupNumber("", requested, canonical); ok {
		t.Fatal("unconfigured mode must not resolve a number")
	}
}
