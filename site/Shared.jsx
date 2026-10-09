const DS = window.AIUsageDesignSystem_480680;
const { ExtPopover, ExtHeader, ExtSection, ExtMeterRow, ExtFooter, ExtButton, ExtStats, ExtFilterChips, ExtPanelIndicator, ExtIcon } = DS;
const HEAD = { fontFamily: "var(--font-heading)", fontWeight: 600 };
const KICK = { ...HEAD, fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--muted)" };
const MONO = { fontFamily: "ui-monospace, 'JetBrains Mono', 'DejaVu Sans Mono', monospace", fontSize: 13 };
const stColor = (s) => "var(--st-" + s + ")";
const Corners = () => <><i className="corner tl"></i><i className="corner tr"></i><i className="corner bl"></i><i className="corner br"></i></>;
const goTo = (id) => { const el = document.getElementById(id); if (el) window.scrollTo({ top: el.getBoundingClientRect().top + scrollY - 50, behavior: "smooth" }); };

function TopBar({ b, onToggle, open }) {
  const [clock, setClock] = React.useState(() => new Date());
  React.useEffect(() => { const t = setInterval(() => setClock(new Date()), 15000); return () => clearInterval(t); }, []);
  const date = clock.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + " " + clock.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const urgent = b.status === "crit";
  return (
    <div data-theme="light" style={{ position: "sticky", top: 0, zIndex: 50, height: 30, background: "var(--topbar-bg)", display: "flex", alignItems: "center", padding: "0 12px", gap: 14, color: "var(--color-neutral-100)", fontSize: 13 }}>
      <span style={{ fontWeight: 600 }}>Activities</span>
      <span style={{ flex: 1, textAlign: "center", fontWeight: 600 }}>{date}</span>
      {b.brrr && <span className="tgb-brrr" style={{ ...HEAD, fontSize: 13, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--indicator-dot)" }}>brrr</span>}
      <button onClick={onToggle} title="This page's usage" style={{ display: "flex", border: 0, padding: 0, background: open ? "color-mix(in srgb, var(--color-neutral-100) 14%, transparent)" : "transparent", cursor: "pointer" }} className={b.brrr ? "tgb-shake" : ""}>
        <ExtPanelIndicator variant={urgent ? "quiet" : "tightest"} urgent={urgent} name="This page" value={b.limited ? "out" : b.eta ? "~" + fmtDur(b.eta) : b.pct + "%"} dot={b.status === "warn"} />
      </button>
      <ExtIcon name="wifi" size={15} /><ExtIcon name="battery" size={15} />
    </div>
  );
}

function PagePopover({ b, dark }) {
  return (
    <ExtPopover dark={dark} signal>
      <ExtHeader kicker="This page" meta="5-minute window" title={b.title} sub={b.sub} />
      <ExtSection>
        <ExtMeterRow label="Tokens go brrr" tag="tightest" value={b.pct} elapsed={b.elapsedPct} status={b.status} showPace sub={b.rate > 50 ? "Burning " + fmtTok(b.rate) + " tokens/s" : "Idle · even pace marked by the tick"} />
      </ExtSection>
      <ExtSection label="Spent on">
        {b.parts.map((p) => <ExtMeterRow key={p.key} label={p.label} value={p.value} status={statusOf(p.value)} sub={p.sub} muted={p.value === 0} />)}
      </ExtSection>
      <ExtFooter text={b.limited ? "Rate limited" : "Updated just now"} actionLabel="Reset window" onAction={b.reset} showSettings={false} />
    </ExtPopover>
  );
}

function SectionHead({ id, n, kicker, title, b }) {
  const ref = React.useRef(null);
  const [cost, setCost] = React.useState(0);
  React.useEffect(() => {
    const sec = ref.current && ref.current.parentElement; if (!sec) return;
    const m = () => { const max = document.documentElement.scrollHeight - innerHeight; setCost(sec.offsetHeight * 0.82 * LIMIT / Math.max(600, max)); };
    m(); const ro = new ResizeObserver(m); ro.observe(sec); ro.observe(document.body);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 28 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, borderTop: "1px solid var(--color-divider)", paddingTop: 10 }}>
        <span style={KICK}>{n + " · " + kicker}</span>
        <span style={{ ...KICK, fontVariantNumeric: "tabular-nums" }}>{"Costs ~" + fmtTok(cost) + " to scroll"}</span>
      </div>
      <h2 style={{ ...HEAD, fontSize: "clamp(34px, 4.4vw, 52px)", lineHeight: 1.02, margin: 0, textWrap: "balance" }}>{title}</h2>
    </div>
  );
}

const GALLERY = [
  { value: "landing", label: "Insight", nav: { screen: "landing", ins: "act", fromEarlier: false }, cap: "Two or three times a day the popover opens on one written insight. The daemon decides whether anything is worth interrupting for." },
  { value: "list", label: "Agents", nav: { screen: "list" }, cap: "Every provider with its limit meter. The tick marks even pace, and the window picker sets 5-hour, weekly or monthly for every row." },
  { value: "detail", label: "Provider", nav: { screen: "detail", prov: "claude" }, cap: "Each window with its reset, and the terminal sessions running against it. Focus raises the terminal." },
  { value: "sessions", label: "Sessions", nav: { screen: "sessions", prov: "cursor", filter: "active" }, cap: "Running and paused sessions. A session suspended with Ctrl+Z spends nothing, so it is counted apart." },
  { value: "guide", label: "Guide", nav: { screen: "guide" }, cap: "Healthy under 70%, caution to 89%, critical from 90%. The percentage is always written beside the bar." },
];
function Gallery({ dark }) {
  const [nav, setNav] = React.useState(GALLERY[0].nav);
  const [win, setWin] = React.useState("rolling");
  const go = (patch) => setNav((n) => ({ ...n, ...patch }));
  const tab = nav.screen === "earlier" ? "landing" : nav.screen;
  const cur = GALLERY.find((g) => g.value === tab) || GALLERY[0];
  const W = window;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 40, alignItems: "flex-start" }}>
      <div style={{ flex: "1 1 240px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
        <ExtFilterChips options={GALLERY.map((g) => ({ value: g.value, label: g.label }))} value={tab} onChange={(v) => setNav(GALLERY.find((g) => g.value === v).nav)} />
        <p style={{ margin: 0, fontSize: 16, maxWidth: 420, textWrap: "pretty" }}>{cur.cap}</p>
        <p style={{ margin: 0, fontSize: 13, color: "var(--muted)" }}>The popover is live. Rows, Back and Focus work.</p>
      </div>
      <div style={{ flex: "0 0 auto", padding: 6 }}>
        <ExtPopover dark={dark} signal>
          {nav.screen === "landing" && <W.LandingScreen insId={nav.ins || "act"} fromEarlier={nav.fromEarlier} go={go} />}
          {nav.screen === "earlier" && <W.EarlierScreen go={go} />}
          {nav.screen === "list" && <W.ListScreen go={go} showPace win={win} setWin={setWin} />}
          {nav.screen === "detail" && <W.DetailScreen provId={nav.prov} go={go} showPace />}
          {nav.screen === "sessions" && <W.SessionsScreen provId={nav.prov} filter={nav.filter || "active"} go={go} />}
          {nav.screen === "guide" && <W.GuideScreen go={go} />}
          {nav.screen === "about" && <W.AboutScreen go={go} />}
        </ExtPopover>
      </div>
    </div>
  );
}

function Privacy() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0 32px" }}>
      {SITE.privacy.map(([t, d]) => (
        <div key={t} style={{ display: "flex", flexDirection: "column", gap: 6, padding: "16px 0", borderTop: "1px solid var(--color-divider)" }}>
          <span style={{ fontSize: 15, fontWeight: 600 }}>{t}</span>
          <span style={{ fontSize: 14, color: "var(--muted)", textWrap: "pretty" }}>{d}</span>
        </div>
      ))}
    </div>
  );
}

function Faq() {
  const [open, setOpen] = React.useState(0);
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {SITE.faq.map(([q, a], i) => (
        <div key={q} style={{ borderTop: "1px solid var(--color-divider)" }}>
          <button className="ext-row-hover" onClick={() => setOpen(open === i ? -1 : i)} style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, padding: "14px 0", border: 0, background: "transparent", color: "var(--color-text)", textAlign: "left", fontFamily: "var(--font-body)", fontSize: 16, fontWeight: 600 }}>
            <span>{q}</span>
            <span style={{ ...HEAD, fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)", flex: "none" }}>{open === i ? "Close" : "−1.2k"}</span>
          </button>
          {open === i && <p style={{ margin: "0 0 16px", fontSize: 15, maxWidth: 620, color: "var(--muted)", textWrap: "pretty" }}>{a}</p>}
        </div>
      ))}
    </div>
  );
}

function SiteFooter() {
  return (
    <footer style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 16, padding: "20px 0 40px", borderTop: "1px solid var(--color-divider)", fontSize: 13, color: "var(--muted)" }}>
      <span>Tokens go brrr · the AI usage extension for GNOME Shell · <a href={REL_URL} target="_blank">Releases</a></span>
      <span>Provider names and marks belong to their owners and are used only to identify each service.</span>
    </footer>
  );
}

function LimitModal({ b, dark, onDismiss }) {
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 100, background: "color-mix(in srgb, #1d1f20 55%, transparent)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <ExtPopover dark={dark} signal>
        <ExtHeader kicker="429 · Rate limited" meta={"Resets in " + fmtDur(b.resetIn)} title="This page is out of tokens." sub="It spent its 5-minute window on scrolling, clicking and copying. Your real tools are probably fine. The extension can tell you which." />
        <ExtStats items={[{ value: "200k", label: "tokens spent" }, { value: String(b.w.clicks), label: "clicks" }, { value: fmtDur(b.resetIn), label: "until reset" }]} />
        <div style={{ display: "flex", gap: 8, padding: "16px 18px 18px" }}>
          <ExtButton variant="primary" block label="Download the extension" onClick={() => { onDismiss(); setTimeout(() => goTo("download"), 50); }} />
          <ExtButton variant="secondary" label="Reset window" onClick={b.reset} />
        </div>
      </ExtPopover>
    </div>
  );
}

Object.assign(window, { HEAD, KICK, MONO, stColor, Corners, goTo, TopBar, PagePopover, SectionHead, Gallery, Privacy, Faq, SiteFooter, LimitModal });
