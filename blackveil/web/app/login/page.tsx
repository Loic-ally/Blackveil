import Link from "next/link";
import { AuthForm } from "../auth-form";

export default function LoginPage() {
  return <main className="auth-page"><section className="auth-panel"><Link className="brand" href="/"><span className="brand-mark">A</span><span>AETHER <small>INDUSTRIAL INTELLIGENCE</small></span></Link><div className="auth-copy"><p className="eyebrow">AETHER WORKSPACE</p><h1>Welcome back.</h1><p>Sign in to review your equipment and operating activity.</p></div><AuthForm mode="login" /><p className="auth-switch">New to AETHER? <Link href="/register">Create a workspace</Link></p><Link className="back-link" href="/">← Back to AETHER</Link></section><aside className="auth-aside"><div><span className="eyebrow">OPERATIONS, IN CONTEXT</span><h2>Every signal has a story.<br /><em>Keep it connected.</em></h2></div><span className="aside-bottom">AETHER INDUSTRIAL INTELLIGENCE PLATFORM <b>·</b> LOCAL CHALLENGE ENVIRONMENT</span></aside></main>;
}
