"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, InlineNotification, PasswordInput, TextInput } from "@carbon/react";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const registering = mode === "register";

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const payload: Record<string, string> = Object.fromEntries([...data.entries()].map(([k, v]) => [k, String(v)]));
    try {
      const response = await fetch(`/api/auth/${mode}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Unable to continue.");
      router.push("/workspace");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to continue."); }
    finally { setBusy(false); }
  }

  return <form className="auth-form" onSubmit={submit}>
    {registering && <><TextInput id="name" name="name" labelText="Full name" autoComplete="name" required /><TextInput id="company" name="company" labelText="Organization" autoComplete="organization" required /></>}
    <TextInput id="email" name="email" labelText="Work email" type="email" autoComplete="email" required />
    <PasswordInput id="password" name="password" labelText="Password" autoComplete={registering ? "new-password" : "current-password"} minLength={registering ? 12 : 1} required />
    {registering && <p className="form-note">Use at least 12 characters. Your workspace starts with ordinary operator access.</p>}
    {error && <InlineNotification kind="error" lowContrast title="Could not continue" subtitle={error} hideCloseButton />}
    <Button type="submit" size="lg" disabled={busy}>{busy ? "Working…" : registering ? "Create workspace" : "Sign in"}</Button>
  </form>;
}
