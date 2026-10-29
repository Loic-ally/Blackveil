import Link from "next/link";

export default function Home() {
  return <main className="marketing">
    <header className="marketing-nav wrap">
      <Link className="brand" href="/" aria-label="AETHER home"><span className="brand-mark">A</span><span>AETHER <small>INDUSTRIAL INTELLIGENCE</small></span></Link>
      <nav><a href="#platform">Platform</a><a href="#operations">Operations</a><Link href="/api/docs">API reference</Link></nav>
      <div className="nav-actions"><Link className="text-link" href="/login">Sign in</Link><Link className="button button-dark" href="/register">Create workspace <span>↗</span></Link></div>
    </header>

    <section className="hero wrap">
      <div className="hero-copy">
        <p className="eyebrow"><i /> INDUSTRIAL INTELLIGENCE PLATFORM</p>
        <h1>Clarity for<br /><em>complex</em> operations.</h1>
        <p className="hero-lede">Bring equipment health, live operating signals, and maintenance work into one reliable view of your plant.</p>
        <div className="hero-actions"><Link className="button button-dark" href="/register">Open your workspace <span>↗</span></Link><a className="button button-light" href="#platform">Explore the platform <span>↓</span></a></div>
        <div className="hero-proof"><span className="proof-line" /> Built for teams that keep industry moving</div>
      </div>
      <div className="hero-visual" aria-label="Illustrative industrial process schematic">
        <div className="visual-top"><span>PROCESS SCHEMATIC / 04</span><span>EQUIPMENT CONTEXT</span></div>
        <div className="plant-diagram">
          <div className="pipe pipe-a" /><div className="pipe pipe-b" /><div className="pipe pipe-c" />
          <div className="node node-one"><span>01</span><b>FEED</b><small>P-101</small></div>
          <div className="node node-two"><span>02</span><b>COMPRESSION</b><small>C-204</small></div>
          <div className="node node-three"><span>03</span><b>RECOVERY</b><small>HX-018</small></div>
          <div className="flow-marker marker-one" /><div className="flow-marker marker-two" />
          <div className="diagram-note"><span className="status-dot" /> ASSET RELATIONSHIP <b>03 EQUIPMENT CLASSES</b></div>
        </div>
        <div className="visual-footer"><span>ILLUSTRATIVE PROCESS MODEL</span><span>AETHER PLATFORM</span></div>
      </div>
      <div className="hero-index">01 <span>/</span> 04</div>
    </section>

    <section className="signal-strip"><div className="wrap signal-grid"><span>ONE OPERATIONAL PICTURE</span><b>Equipment</b><b>Telemetry</b><b>Maintenance</b><b>Accountability</b></div></section>

    <section className="platform-section wrap" id="platform">
      <div className="section-heading"><div><p className="eyebrow">A BETTER OPERATING RHYTHM</p><h2>From signal to<br />work, without the gaps.</h2></div><p>Context matters as much as the measurement. AETHER connects equipment, historical trends, and maintenance follow-through so teams can act with confidence.</p></div>
      <div className="capability-grid">
        <article className="capability capability-wide"><span className="cap-number">01 / MONITOR</span><div className="cap-graphic telemetry-graphic"><div className="axis"><span>80</span><span>60</span><span>40</span><span>20</span></div><div className="sparkline"><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /></div><div className="chart-labels"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>NOW</span></div></div><h3>See the shape of your operation.</h3><p>Review equipment history alongside live operating context, with trends that make small changes easier to spot.</p></article>
        <article className="capability"><span className="cap-number">02 / RESPOND</span><div className="incident-graphic"><span className="incident-level">HIGH · OPEN</span><b>Seal pressure drift</b><small>P-101 · North process hall</small><div className="incident-rule"><i /></div><small>Assigned to maintenance team</small></div><h3>Keep work connected to evidence.</h3><p>Turn an operating signal into a tracked maintenance incident and leave a useful record for the next shift.</p></article>
        <article className="capability"><span className="cap-number">03 / ACCOUNT</span><div className="audit-graphic"><div><small>06:41:58</small><b>Incident acknowledged</b><span>Operator · P-101</span></div><div><small>06:37:12</small><b>Telemetry threshold crossed</b><span>System · Pump train</span></div><div><small>06:32:09</small><b>Shift handover completed</b><span>Maintenance · North line</span></div></div><h3>Understand what happened.</h3><p>Reports and audit history preserve the sequence of decisions across maintenance and operations.</p></article>
      </div>
    </section>

    <section className="operations-section" id="operations"><div className="wrap operations-inner"><div><p className="eyebrow">DESIGNED FOR REAL OPERATIONS</p><h2>One shared view.<br />Clear next steps.</h2></div><div className="operations-points"><p><b>01</b><span>Multi-organization workspaces keep each team's equipment and records scoped to its operation.</span></p><p><b>02</b><span>Historical telemetry, maintenance incidents, and generated reports use the same asset context.</span></p><p><b>03</b><span>Operational activity is recorded so handovers are based on a reliable history.</span></p></div></div></section>

    <footer className="marketing-footer wrap"><Link className="brand" href="/"><span className="brand-mark">A</span><span>AETHER <small>INDUSTRIAL INTELLIGENCE</small></span></Link><span>Operational intelligence, built for the long run.</span><div><Link href="/api/docs">API reference</Link><Link href="/login">Sign in</Link></div></footer>
  </main>;
}
