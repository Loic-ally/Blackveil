package platform

import "testing"

func TestEnrollmentBindingOK(t *testing.T) {
	const caller, foreign = "caller-uuid", "north-works-uuid"
	if ok, configured := sourceBindingOK("challenge", foreign, caller); !configured || !ok {
		t.Fatalf("challenge foreign receipt: ok=%v configured=%v, want both true", ok, configured)
	}
	if ok, _ := sourceBindingOK("patched", foreign, caller); ok {
		t.Fatal("patched mode accepted a foreign installation receipt")
	}
	if ok, configured := sourceBindingOK("patched", caller, caller); !configured || !ok {
		t.Fatal("patched mode rejected the caller's own installation receipt")
	}
	if _, configured := sourceBindingOK("", caller, caller); configured {
		t.Fatal("unconfigured mode must not enroll")
	}
}
