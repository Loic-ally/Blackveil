"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function JoinPage() {
  const router=useRouter();
  const [token,setToken]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{setToken(window.location.hash.slice(1));window.history.replaceState(null,"","/join")},[]);
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();setBusy(true);setError("");
    const data=new FormData(event.currentTarget);
    try {
      const response=await fetch("/api/auth/invitations/accept",{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({token,email:data.get("email"),name:data.get("name"),password:data.get("password")})});
      const result=await response.json();if(!response.ok)throw new Error(result.error||"Unable to join workspace");router.push("/workspace");
    } catch(e) {setError(e instanceof Error?e.message:"Unable to join workspace")}
    finally {setBusy(false)}
  }
  return <main className="auth-page"><section className="auth-panel"><Link className="brand" href="/">AETHER</Link><div className="auth-copy"><p className="eyebrow">WORKSPACE INVITATION</p><h1>Join your team.</h1><p>Use the email address your administrator invited.</p></div><form className="auth-form" onSubmit={submit}><label>Full name<input name="name" autoComplete="name" required/></label><label>Work email<input name="email" type="email" autoComplete="email" required/></label><label>Password<input name="password" type="password" autoComplete="new-password" minLength={12} maxLength={72} required/></label>{error&&<p role="alert">{error}</p>}{!token&&<p>Open the complete invitation link provided by your administrator.</p>}<button className="button button-dark" disabled={busy||!token}>{busy?"Joining…":"Join workspace"}</button></form><Link href="/login">Already have an account? Sign in</Link></section></main>;
}
