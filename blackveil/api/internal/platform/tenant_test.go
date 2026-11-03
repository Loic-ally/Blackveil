package platform

import "testing"

func TestMigrationLookupNumber(t *testing.T) {
	const requested, canonical = 4101, 4102
	if got, ok := migrationLookupNumber("challenge", requested, canonical); !ok || got != requested {
		t.Fatalf("challenge: got (%d,%v), want (%d,true)", got, ok, requested)
	}
	if got, ok := migrationLookupNumber("patched", requested, canonical); !ok || got != canonical {
		t.Fatalf("patched: got (%d,%v), want (%d,true)", got, ok, canonical)
	}
	if _, ok := migrationLookupNumber("", requested, canonical); ok {
		t.Fatal("unconfigured mode must not resolve a number")
	}
}
