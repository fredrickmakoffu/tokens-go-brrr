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
  React.useEffect(() => { const id = setInterval(() => setClock(new Date()), 15000); return () => clearInterval(id); }, []);
  const date = clock.toLocaleDateString(I18N.locale(), { month: "short", day: "numeric" }) + " " + clock.toLocaleTimeString(I18N.locale(), { hour: "2-digit", minute: "2-digit", hour12: false });
  const urgent = b.status === "crit";
  return (
    <div data-theme="light" style={{ position: "sticky", top: 0, zIndex: 50, height: 30, background: "var(--topbar-bg)", display: "flex", alignItems: "center", padding: "0 12px", gap: 14, color: "var(--color-neutral-100)", fontSize: 13 }}>
      <span style={{ fontWeight: 600 }}>{t("bar.activities")}</span>
      <span style={{ flex: 1, textAlign: "center", fontWeight: 600 }}>{date}</span>
      {b.brrr && <span className="tgb-brrr" style={{ ...HEAD, fontSize: 13, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--indicator-dot)" }}>brrr</span>}
      <button onClick={onToggle} title={t("bar.usage")} style={{ display: "flex", border: 0, padding: 0, background: open ? "color-mix(in srgb, var(--color-neutral-100) 14%, transparent)" : "transparent", cursor: "pointer" }} className={b.brrr ? "tgb-shake" : ""}>
        <ExtPanelIndicator variant={urgent ? "quiet" : "tightest"} urgent={urgent} name={t("bar.name")} value={b.limited ? t("bar.out") : b.eta ? "~" + fmtDur(b.eta) : b.pct + "%"} dot={b.status === "warn"} />
      </button>
      <ThemeToggle />
      <LangSwitch bar />
      <ExtIcon name="wifi" size={15} /><ExtIcon name="battery" size={15} />
    </div>
  );
}

function PagePopover({ b, dark }) {
  return (
    <ExtPopover dark={dark} signal>
      <ExtHeader kicker={t("page.kicker")} meta={t("page.window")} title={b.title} sub={b.sub} />
      <ExtSection>
        <ExtMeterRow label="Tokens go brrr" tag={t("page.tightest")} value={b.pct} elapsed={b.elapsedPct} status={b.status} showPace sub={b.rate > 50 ? t("page.burning", { rate: fmtTok(b.rate) }) : t("page.idle")} />
      </ExtSection>
      <ExtSection label={t("page.spentOn")}>
        {b.parts.map((p) => <ExtMeterRow key={p.key} label={p.label} value={p.value} status={statusOf(p.value)} sub={p.sub} muted={p.value === 0} />)}
      </ExtSection>
      <ExtFooter text={b.limited ? t("page.limited") : t("page.updated")} actionLabel={t("page.reset")} onAction={b.reset} showSettings={false} />
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
        <span style={{ ...KICK, fontVariantNumeric: "tabular-nums" }}>{t("sec.cost", { n: fmtTok(cost) })}</span>
      </div>
      <h2 style={{ ...HEAD, fontSize: "clamp(34px, 4.4vw, 52px)", lineHeight: 1.02, margin: 0, textWrap: "balance" }}>{title}</h2>
    </div>
  );
}

const PRIVACY_KEYS = ["logins", "ext", "history", "prompts"];
const FAQ_KEYS = ["tools", "nobar", "paused", "poll", "script", "gnome", "os"];
const galleryItems = () => [
  { value: "landing", label: t("gal.insight"), nav: { screen: "landing", ins: "act", fromEarlier: false }, cap: t("gal.insight.cap") },
  { value: "list", label: t("gal.agents"), nav: { screen: "list" }, cap: t("gal.agents.cap") },
  { value: "detail", label: t("gal.provider"), nav: { screen: "detail", prov: "claude" }, cap: t("gal.provider.cap") },
  { value: "sessions", label: t("gal.sessions"), nav: { screen: "sessions", prov: "cursor", filter: "active" }, cap: t("gal.sessions.cap") },
  { value: "guide", label: t("gal.guide"), nav: { screen: "guide" }, cap: t("gal.guide.cap") },
];

function ThemeToggle() {
  const dark = THEME.resolved() === "dark";
  const p = { width: 15, height: 15, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };
  // The icon is the theme showing now; the label says what a click does.
  const icon = dark
    ? <svg {...p}><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" /></svg>
    : <svg {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></svg>;
  const label = t(dark ? "theme.toLight" : "theme.toDark");
  return <button onClick={() => THEME.toggle()} title={label} aria-label={label} style={{ display: "flex", border: 0, background: "transparent", padding: 2, cursor: "pointer", color: "inherit" }}>{icon}</button>;
}

function LangSwitch({ bar }) {
  const cur = I18N.locale();
  return (
    <span role="group" aria-label={t("lang.label")} style={{ display: "flex", gap: bar ? 8 : 12, fontSize: bar ? 13 : "inherit", fontWeight: bar ? 600 : "inherit" }}>
      {Object.entries(I18N.LOCALES).map(([code, l]) => (
        <button key={code} lang={code} onClick={() => I18N.setLocale(code)} aria-pressed={cur === code} title={l.label}
          style={{ border: 0, background: "transparent", padding: 0, cursor: "pointer", font: "inherit", textTransform: "uppercase", letterSpacing: "0.08em", color: bar ? "inherit" : cur === code ? "var(--color-text)" : "var(--muted)", opacity: bar && cur !== code ? 0.55 : 1, textDecoration: cur === code ? "underline" : "none", textUnderlineOffset: 4 }}>{l.short}</button>
      ))}
    </span>
  );
}

function Gallery({ dark }) {
  const GALLERY = galleryItems();
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
        <p style={{ margin: 0, fontSize: 13, color: "var(--muted)" }}>{t("gal.live")}</p>
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
      {PRIVACY_KEYS.map((k) => [t("privacy." + k + ".t"), t("privacy." + k + ".d")]).map(([title, d]) => (
        <div key={title} style={{ display: "flex", flexDirection: "column", gap: 6, padding: "16px 0", borderTop: "1px solid var(--color-divider)" }}>
          <span style={{ fontSize: 15, fontWeight: 600 }}>{title}</span>
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
      {FAQ_KEYS.map((k, i) => [t("faq." + k + ".q"), t("faq." + k + ".a")]).map(([q, a], i) => (
        <div key={q} style={{ borderTop: "1px solid var(--color-divider)" }}>
          <button className="ext-row-hover" onClick={() => setOpen(open === i ? -1 : i)} style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, padding: "14px 0", border: 0, background: "transparent", color: "var(--color-text)", textAlign: "left", fontFamily: "var(--font-body)", fontSize: 16, fontWeight: 600 }}>
            <span>{q}</span>
            <span style={{ ...HEAD, fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)", flex: "none" }}>{open === i ? t("faq.close") : t("faq.open")}</span>
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
      <span>{t("foot.line")}<a href={REL_URL} target="_blank">{t("foot.releases")}</a></span>
      <span>{t("foot.marks")}</span><LangSwitch />
    </footer>
  );
}

function LimitModal({ b, dark, onDismiss }) {
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 100, background: "color-mix(in srgb, #1d1f20 55%, transparent)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <ExtPopover dark={dark} signal>
        <ExtHeader kicker={t("modal.kicker")} meta={t("modal.meta", { dur: fmtDur(b.resetIn) })} title={t("modal.title")} sub={t("modal.sub")} />
        <div style={{ display: "flex", gap: 8, padding: "16px 18px 18px" }}>
          <ExtButton variant="primary" block label={t("modal.download")} onClick={() => { onDismiss(); setTimeout(() => goTo("download"), 50); }} />
          <ExtButton variant="secondary" label={t("modal.reset")} onClick={b.reset} />
        </div>
      </ExtPopover>
    </div>
  );
}

Object.assign(window, { HEAD, KICK, MONO, stColor, Corners, goTo, TopBar, PagePopover, SectionHead, Gallery, Privacy, Faq, SiteFooter, LimitModal });
