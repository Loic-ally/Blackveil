"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import styles from "./lab.module.scss";

type Me = { role: string; display_name: string };

export default function LinuxLab() {
  const router = useRouter();
  const outputRef = useRef<HTMLPreElement>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const historyRef = useRef<string[]>([]);
  const historyIndex = useRef(0);
  const [role, setRole] = useState("");
  const [state, setState] = useState("Checking workspace access");
  const [output, setOutput] = useState("");
  const [command, setCommand] = useState("");
  const [proof, setProof] = useState("");
  const [proofState, setProofState] = useState<"pending" | "complete" | "working">("pending");
  const [proofFlag, setProofFlag] = useState("");
  const [proofFeedback, setProofFeedback] = useState("");

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    fetch("/api/me", { credentials: "include" })
      .then(async response => {
        if (response.status === 401) {
          router.replace("/login");
          throw new Error("Sign in to continue.");
        }
        if (!response.ok) throw new Error("Unable to check workspace access.");
        return response.json() as Promise<Me>;
      })
      .then(me => {
        if (!active) return;
        setRole(me.role);
        if (me.role !== "system_admin") {
          setState("Linux lab access is not enabled for this identity.");
          return;
        }
        setState("Opening restricted operator session");
        fetch("/api/v2/lab/final-proof", { credentials: "include" })
          .then(response => (response.ok ? response.json() : null))
          .then(status => {
            if (!active || !status) return;
            if (status.status === "complete") {
              setProofState("complete");
              setProofFlag(status.flag || "");
            }
          })
          .catch(() => undefined);
        const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(`${scheme}//${window.location.host}/api/lab/terminal`);
        socketRef.current = socket;
        socket.onopen = () => setState("Connected · disposable Debian guest · operator");
        socket.onmessage = event => setOutput(current => (current + String(event.data)).slice(-120_000));
        socket.onerror = () => setState("The Linux lab connection failed.");
        socket.onclose = () => setState("Session closed");
      })
      .catch(error => {
        if (active && error instanceof Error) setState(error.message);
      });
    return () => {
      active = false;
      socket?.close();
      socketRef.current = null;
    };
  }, [router]);

  useEffect(() => {
    const screen = outputRef.current;
    if (screen) screen.scrollTop = screen.scrollHeight;
  }, [output]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const socket = socketRef.current;
    if (!command.trim() || socket?.readyState !== WebSocket.OPEN) return;
    historyRef.current.unshift(command);
    historyRef.current = historyRef.current.slice(0, 40);
    historyIndex.current = 0;
    socket.send(`${command}\r`);
    setCommand("");
  }

  async function submitProof(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let parsed: unknown;
    try {
      parsed = JSON.parse(proof);
    } catch {
      setProofFeedback("Proof must be valid JSON.");
      return;
    }
    setProofState("working");
    setProofFeedback("");
    try {
      const response = await fetch("/api/v2/lab/final-proof", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proof: parsed }),
      });
      const result = await response.json();
      if (response.ok && result.status === "complete") {
        setProofState("complete");
        setProofFlag(result.flag || "");
      } else if (result.status === "incomplete") {
        setProofState("pending");
        setProofFeedback("Proof rejected. Check your complete evidence bundle and try again.");
      } else {
        setProofState("pending");
        setProofFeedback(result.error || "Submission could not be validated.");
      }
    } catch {
      setProofState("pending");
      setProofFeedback("Submission failed. Try again shortly.");
    }
  }

  function keyDown(event: KeyboardEvent<HTMLInputElement>) {
    const socket = socketRef.current;
    if (event.key === "ArrowUp" && historyRef.current.length) {
      event.preventDefault();
      const next = Math.min(historyIndex.current + 1, historyRef.current.length);
      historyIndex.current = next;
      setCommand(historyRef.current[next - 1] || "");
    } else if (event.key === "ArrowDown" && historyIndex.current > 0) {
      event.preventDefault();
      const next = historyIndex.current - 1;
      historyIndex.current = next;
      setCommand(next === 0 ? "" : historyRef.current[next - 1] || "");
    } else if (event.ctrlKey && event.key.toLowerCase() === "c" && socket?.readyState === WebSocket.OPEN) {
      event.preventDefault();
      socket.send("\u0003");
      setCommand("");
    }
  }

  return <main className={styles.page}>
    <header className={styles.header}>
      <Link className={styles.brand} href="/workspace"><span className={styles.mark}>A</span><span>AETHER <small>INDUSTRIAL INTELLIGENCE</small></span></Link>
      <span className={styles.eyebrow}>RESTRICTED OPERATIONS CONSOLE</span>
      <Link className={styles.back} href="/workspace">← Workspace</Link>
    </header>
    <section className={styles.content}>
      <p className={styles.kicker}>AETHER / LINUX LAB / SESSION 01</p>
      <h1>Maintenance environment</h1>
      <p className={styles.lede}>A short lived shell on the isolated Debian guest. This session uses the restricted operator identity.</p>
      <div className={styles.terminal}>
        <div className={styles.terminalHead}><span><i className={role === "system_admin" && state.startsWith("Connected") ? styles.live : ""} />{state}</span><span>DEBIAN 13 · AARCH64</span></div>
        <pre ref={outputRef} className={styles.output} aria-label="Linux shell output">{output || (role === "system_admin" && state.startsWith("Connected") ? "" : "Access to this console is granted by the AETHER identity service.")}</pre>
        {role === "system_admin" && <form className={styles.command} onSubmit={submit}>
          <span aria-hidden="true">›</span>
          <input autoFocus aria-label="Linux shell command" autoComplete="off" spellCheck={false} value={command} onChange={event => setCommand(event.target.value)} onKeyDown={keyDown} placeholder={state.startsWith("Connected") ? "Enter a command" : "Waiting for guest"} disabled={!state.startsWith("Connected")} />
          <button type="submit" disabled={!state.startsWith("Connected") || !command.trim()}>Send</button>
        </form>}
      </div>
      <p className={styles.footnote}>Guest filesystem and services are disposable. The console does not expose host or Docker controls.</p>
      {role === "system_admin" && <div className={styles.finalProof}>
        <div className={styles.terminalHead}><span>FINAL PROOF SUBMISSION</span><span>BLACK VEIL</span></div>
        {proofState === "complete"
          ? <div className={styles.proofDone}>
              <p>Challenge complete. Final proof accepted.</p>
              <code>{proofFlag}</code>
            </div>
          : <form className={styles.proofForm} onSubmit={submitProof}>
              <label htmlFor="final-proof">Submit your assembled final proof (JSON). It is validated by an isolated service; the flag is issued only on a complete, correct proof.</label>
              <textarea id="final-proof" aria-label="Final proof JSON" spellCheck={false} value={proof}
                onChange={event => setProof(event.target.value)}
                placeholder={'{ "attestation": "…", "veil_tag": "…", "manifest": "…", "pivot_number": …, "tenant_uuid": "…" }'} />
              <button type="submit" disabled={proofState === "working" || !proof.trim()}>{proofState === "working" ? "Validating…" : "Submit final proof"}</button>
              {proofFeedback && <p className={styles.proofFeedback}>{proofFeedback}</p>}
            </form>}
      </div>}
    </section>
  </main>;
}
