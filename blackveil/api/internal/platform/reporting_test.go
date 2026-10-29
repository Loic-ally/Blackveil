package platform

import "testing"

func TestEnrollmentBindingOK(t *testing.T) {
	const caller, foreign = "caller-uuid", "north-works-uuid"
	// Challenge mode accepts a foreign installation's receipt: the Stage 04 flaw.
	if ok, configured := sourceBindingOK("challenge", foreign, caller); !configured || !ok {
		t.Fatalf("challenge foreign receipt: ok=%v configured=%v, want both true", ok, configured)
	}
	// Patched mode binds the receipt's installation to the caller.
	if ok, _ := sourceBindingOK("patched", foreign, caller); ok {
		t.Fatal("patched mode accepted a foreign installation receipt")
	}
	if ok, configured := sourceBindingOK("patched", caller, caller); !configured || !ok {
		t.Fatal("patched mode rejected the caller's own installation receipt")
	}
	// Unknown mode fails closed.
	if _, configured := sourceBindingOK("", caller, caller); configured {
		t.Fatal("unconfigured mode must not enroll")
	}
}
