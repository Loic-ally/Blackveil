"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Member = { id:string; email:string; name:string; role:string };
type Invite = { id:string; email:string; role:string; expires_at:string; accepted_at:string|null; revoked_at:string|null };
const roles = ["operator", "maintenance", "tenant_admin"];

async function request(path:string, method="GET", body?:unknown) {
  const response = await fetch(path,{method,credentials:"include",headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
  const value = response.status===204 ? null : await response.json();
  if(!response.ok) throw new Error(value?.error||`Request failed (${response.status})`);
  return value;
}

export default function TeamPage() {
  const [members,setMembers]=useState<Member[]>([]);
  const [invites,setInvites]=useState<Invite[]>([]);
  const [self,setSelf]=useState("");
  const [allowed,setAllowed]=useState(false);
  const [error,setError]=useState("");
  const [url,setURL]=useState("");
  const [busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>{
    try {
      const me=await request("/api/me");setSelf(me.id);
      if(!["tenant_admin","system_admin"].includes(me.role)) {setAllowed(false);setError("Workspace administrator access is required.");return}
      setAllowed(true);
      const team=await request("/api/team");setMembers(team.users);setInvites(team.invitations);
    } catch(e) {setError(e instanceof Error?e.message:"Unable to load team")}
  },[]);
  useEffect(()=>{void refresh()},[refresh]);
  async function mutate(path:string,method:string,body?:unknown) {
    setBusy(true);setError("");
    try {const result=await request(path,method,body);await refresh();return result}
    catch(e) {setError(e instanceof Error?e.message:"Unable to save");return null}
    finally {setBusy(false)}
  }
  async function invite(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();const data=new FormData(event.currentTarget);
    const result=await mutate("/api/team/invitations","POST",{email:data.get("email"),role:data.get("role")});
    if(result) setURL(result.url);
  }
  return <main className="console-main"><div className="console-content">
    <Link href="/workspace">← Workspace</Link>
    <div className="page-title"><div><p className="eyebrow">AETHER / ADMINISTRATION</p><h1>Workspace team</h1><p>Manage membership and pending invitations.</p></div></div>
    {error&&<p role="alert" className="inline-error">{error}</p>}
    {allowed&&<>
      <section className="panel table-panel"><div className="panel-head"><h2>Members</h2></div>
        <div className="report-list">{members.map(member=><div className="report-row" key={member.id}><div><b>{member.name}</b><small>{member.email}</small></div>
          {member.role==="system_admin"?<span>system_admin</span>:<select aria-label={`Role for ${member.email}`} value={member.role} disabled={busy||member.id===self} onChange={event=>void mutate(`/api/team/users/${member.id}`,"PATCH",{role:event.target.value})}>{roles.map(role=><option key={role}>{role}</option>)}</select>}
        </div>)}</div>
      </section>
      <section className="panel table-panel"><div className="panel-head"><h2>Invite a teammate</h2></div>
        <form className="auth-form" onSubmit={invite} style={{padding:24}}><label>Work email<input name="email" type="email" required/></label><label>Workspace role<select name="role">{roles.map(role=><option key={role}>{role}</option>)}</select></label><button className="button button-dark" disabled={busy}>Create invitation</button>
          {url&&<label>Share this link with the invited teammate. It expires in 48 hours.<input readOnly value={url} onFocus={event=>event.target.select()}/></label>}
        </form>
      </section>
      <section className="panel table-panel"><div className="panel-head"><h2>Invitation history</h2></div><div className="report-list">
        {invites.length===0&&<p className="empty-state">No invitations created.</p>}
        {invites.map(item=><div className="report-row" key={item.id}><div><b>{item.email}</b><small>{item.role} · Expires {new Date(item.expires_at).toLocaleString()}</small></div><span>{item.accepted_at?"Accepted":item.revoked_at?"Revoked":Date.parse(item.expires_at)<Date.now()?"Expired":"Pending"}</span>{!item.accepted_at&&!item.revoked_at&&Date.parse(item.expires_at)>Date.now()&&<button className="button button-small" disabled={busy} onClick={()=>void mutate(`/api/team/invitations/${item.id}`,"DELETE")}>Revoke</button>}</div>)}
      </div></section>
    </>}
  </div></main>;
}
