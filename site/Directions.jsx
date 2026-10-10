function Sections({ b, dark }) {
  const sec = { padding: "72px 0 24px" };
  const rel = useReleases();
  return (<>
    <section id="download" style={sec} data-screen-label="Download">
      <SectionHead n="01" kicker={t("sec.download.kicker")} title={t("sec.download.title", { tag: rel.latest.tag })} b={b} />
      <Downloads b={b} rel={rel} />
    </section>
    <section id="screens" style={sec} data-screen-label="What it does">
      <SectionHead n="02" kicker={t("sec.what.kicker")} title={t("sec.what.title")} b={b} />
      <Facts />
      <Gallery dark={dark} />
    </section>
    <section id="local" style={sec} data-screen-label="Local only">
      <SectionHead n="03" kicker={t("sec.privacy.kicker")} title={t("sec.privacy.title")} b={b} />
      <Privacy />
    </section>
    <section id="faq" style={sec} data-screen-label="FAQ">
      <SectionHead n="04" kicker={t("sec.faq.kicker")} title={t("sec.faq.title")} b={b} />
      <Faq />
    </section>
    <section id="releases" style={{ ...sec, paddingBottom: 72 }} data-screen-label="Releases">
      <SectionHead n="05" kicker={t("sec.releases.kicker")} title={t("sec.releases.title")} b={b} />
      <Releases rel={rel} b={b} />
    </section>
    <SiteFooter />
  </>);
}

const HeroButtons = () => (
  <div style={{ display: "flex", flexWrap: "wrap", gap: 12, padding: 6 }}>
    <ExtButton variant="primary" label={t("hero.download")} onClick={() => goTo("download")} style={{ minWidth: 200 }} />
    <ExtButton variant="secondary" label={t("hero.how")} onClick={() => goTo("screens")} />
  </div>
);

function Rail({ b }) {
  const c = stColor(b.status);
  const lab = { ...HEAD, fontSize: 12, letterSpacing: "0.08em", color: "var(--muted)", position: "absolute", left: 0, width: "100%", textAlign: "center" };
  return (
    <div style={{ position: "fixed", left: 0, top: 30, bottom: 0, width: 76, borderRight: "1px solid var(--color-divider)", zIndex: 5, background: "var(--color-bg)" }}>
      <span style={{ ...lab, top: 12 }}>0</span>
      <span style={{ ...lab, bottom: 12 }}>200k</span>
      <div style={{ position: "absolute", top: 40, bottom: 40, left: 26, width: 6, background: "var(--track)" }}>
        <div style={{ position: "absolute", left: 0, top: 0, width: "100%", height: b.pct + "%", background: c, transition: "height 200ms ease-out, background-color 300ms" }}></div>
        <div title={t("rail.pace")} style={{ position: "absolute", left: -5, width: 16, height: 1, top: b.elapsedPct + "%", background: "var(--color-text)" }}></div>
        <span style={{ ...HEAD, position: "absolute", left: 14, top: "calc(" + b.pct + "% - 9px)", fontSize: 15, fontVariantNumeric: "tabular-nums", color: "var(--color-text)", transition: "top 200ms ease-out" }}>{b.pct}</span>
      </div>
    </div>
  );
}

function Readout({ b }) {
  const cell = { display: "flex", flexDirection: "column", gap: 4, padding: "14px 18px", borderLeft: "1px solid var(--color-divider)", minWidth: 0 };
  const big = { ...HEAD, fontSize: "clamp(30px, 3.6vw, 44px)", lineHeight: 1, fontVariantNumeric: "tabular-nums" };
  return (
    <div className="blueprint" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
      <Corners />
      <div style={{ ...cell, borderLeft: 0 }}><span style={KICK}>{t("readout.spent")}</span><span style={{ ...big, color: stColor(b.status) }}>{fmtFull(b.tokens)}</span><span style={{ fontSize: 13, color: "var(--muted)" }}>{t("readout.of", { max: fmtFull(LIMIT) })}</span></div>
      <div style={cell}><span style={KICK}>{t("readout.burning")}</span><span style={big}>{b.rate > 50 ? fmtTok(b.rate) + "/s" : "0/s"}</span><span style={{ fontSize: 13, color: "var(--muted)" }}>{b.eta ? t("readout.out", { dur: fmtDur(b.eta) }) : t("readout.idle")}</span></div>
      <div style={cell}><span style={KICK}>{t("readout.window")}</span><span style={big}>{fmtDur(b.resetIn)}</span><span style={{ fontSize: 13, color: "var(--muted)" }}>{t("readout.reset")}</span></div>
    </div>
  );
}

function DirB({ b, dark }) {
  const [drop, setDrop] = React.useState(false);
  return (
    <div data-status="signal" style={{ background: "var(--color-bg)", color: "var(--color-text)", minHeight: "100vh" }}>
      <TopBar b={b} open={drop} onToggle={() => setDrop((d) => !d)} />
      {drop && <div style={{ position: "fixed", top: 40, right: 16, zIndex: 60 }}><PagePopover b={b} dark={dark} /></div>}
      <Rail b={b} />
      <div aria-hidden="true" style={{ position: "fixed", right: "-1vw", bottom: "-7vw", zIndex: 0, pointerEvents: "none", ...HEAD, fontSize: "40vw", lineHeight: 0.8, fontVariantNumeric: "tabular-nums", color: "transparent", WebkitTextStroke: "1px color-mix(in srgb, " + stColor(b.status) + " 50%, transparent)", transition: "-webkit-text-stroke-color 300ms" }}>{b.pct}</div>
      <div style={{ marginLeft: 76, position: "relative", zIndex: 1 }}>
        <div style={{ maxWidth: 980, padding: "0 clamp(20px, 5vw, 64px)" }}>
          <section data-screen-label="Hero" style={{ padding: "clamp(48px, 8vw, 96px) 0 24px", display: "flex", flexDirection: "column", gap: 32 }}>
            <span style={KICK}>{t("hero.kicker")}</span>
            <h1 style={{ ...HEAD, fontSize: "clamp(80px, 14vw, 220px)", lineHeight: 0.82, margin: 0, letterSpacing: "-0.015em" }}>Tokens<br />go <span style={{ color: stColor(b.status), transition: "color 300ms" }}>brrr.</span></h1>
            <Readout b={b} />
            <p style={{ margin: 0, fontSize: 20, lineHeight: 1.45, maxWidth: 600, textWrap: "pretty" }}>{t("hero.sub")}</p>
            <HeroButtons />
            <p style={{ margin: 0, fontSize: 14, color: "var(--muted)", maxWidth: 600 }}>{t("hero.rail")}</p>
          </section>
          <Sections b={b} dark={dark} />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { DirB });
