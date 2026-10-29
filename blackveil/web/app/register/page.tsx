import Link from "next/link";
import { AuthForm } from "../auth-form";

export default function RegisterPage() {
  return <main className="auth-page"><section className="auth-panel"><Link className="brand" href="/"><span className="brand-mark">A</span><span>AETHER <small>INDUSTRIAL INTELLIGENCE</small></span></Link><div className="auth-copy"><p className="eyebrow">START A WORKSPACE</p><h1>Bring your plant into view.</h1><p>Create an operator account and workspace. You can add equipment and invite your team from inside AETHER.</p></div><AuthForm mode="register" /><p className="auth-switch">Already registered? <Link href="/login">Sign in</Link></p><Link className="back-link" href="/">← Back to AETHER</Link></section><aside className="auth-aside"><div><span className="eyebrow">A CLEARER OPERATING PICTURE</span><h2>Equipment.<br />History.<br /><em>Follow-through.</em></h2></div><span className="aside-bottom">MULTI-ORGANIZATION · ROLE-SCOPED · AUDITABLE</span></aside></main>;
}
