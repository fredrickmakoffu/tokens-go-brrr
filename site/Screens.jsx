const { ExtHeader, ExtStats, ExtButton, ExtSection, ExtMeterRow, ExtListRow, ExtFooter, ExtSessionRow, ExtWindowPicker, ExtFilterChips, ExtGuideItem, ProviderIcon } = window.AIUsageDesignSystem_480680;
const byId = (id) => PROVIDERS.find((p) => p.id === id);
const sessionsOf = (id) => SESSIONS.filter((s) => s.p === id);
const sessionMeta = (s) => [s.model ? t("session.via", { model: s.model, via: s.via }) : null, s.tty, s.paused ? t("session.paused") : null].filter(Boolean).join(" · ");

function useFocusNote() {
  const [note, setNote] = React.useState(null);
  const focus = (s) => { setNote({ key: s.p + s.tty, text: t("focus.note", { project: s.project, tty: s.tty }) }); clearTimeout(window.__ft); window.__ft = setTimeout(() => setNote(null), 2200); };
  return [note, focus];
}

function LandingScreen({ insId, fromEarlier, go }) {
  const ins = INSIGHTS.find((i) => i.id === insId);
  return (<>
    <ExtHeader kicker={t("landing.kicker", { kind: ins.kind })} meta={ins.time} title={ins.title} sub={ins.sub} onBack={fromEarlier ? () => go({ screen: "earlier" }) : undefined} />
    <ExtStats items={ins.stats} />
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 18px", fontSize: 12, color: "var(--muted)" }}>
      <ProviderIcon provider="claude" size={13} /><span>{t("landing.by")}</span>
    </div>
    <div style={{ display: "flex", gap: 8, padding: "4px 18px 18px" }}>
      <ExtButton variant="primary" block label={t("landing.continue")} onClick={() => go({ screen: "list" })} />
      <ExtButton variant="secondary" label={t("landing.earlier")} onClick={() => go({ screen: "earlier" })} />
    </div>
  </>);
}

function EarlierScreen({ go }) {
  return (<>
    <ExtHeader kicker={t("earlier.kicker")} meta={t("earlier.meta")} title={t("earlier.title")} sub={t("earlier.sub")} onBack={() => go({ screen: "list" })} />
    <ExtSection>
      {INSIGHTS.map((i) => <ExtListRow key={i.id} kicker={i.kind + " · " + i.time} title={i.title} meta={t("earlier.by")} onClick={() => go({ screen: "landing", ins: i.id, fromEarlier: true })} />)}
    </ExtSection>
    <ExtFooter text={t("earlier.next")} />
  </>);
}

function ListScreen({ go, showPace, win, setWin }) {
  const running = SESSIONS.filter((s) => !s.paused);
  const projects = new Set(running.map((s) => s.project)).size;
  return (<>
    <ExtHeader kicker={t("list.kicker")} meta="15:00" title={t("list.title")} sub={t("list.sub", { n: running.length, m: projects })} />
    <ExtSection>
      {PROVIDERS.map((p) => {
        const w = p.windows.find((x) => x.kind === win) || p.windows.find((x) => x.key === p.binding);
        return <ExtMeterRow key={p.id} icon={p.id} label={p.name} tag={p.via ? t("list.via", { via: p.via }) : w.label} value={w.value} elapsed={w.elapsed}
          status={p.via ? "ok" : w.status} muted={!!p.via} showPace={showPace}
          sub={p.via ? t("list.shares", { win: w.label.toLowerCase(), value: w.value }) : w.sub}
          onClick={() => go({ screen: "detail", prov: p.id })} />;
      })}
    </ExtSection>
    <ExtWindowPicker options={WINDOWS} value={win} onChange={setWin} />
    <ExtFooter text={t("list.updated")} actionLabel={t("list.latest")} onAction={() => go({ screen: "landing", ins: "act", fromEarlier: false })}
      actions={[{ label: t("list.guide"), onClick: () => go({ screen: "guide" }) }, { label: t("list.about"), onClick: () => go({ screen: "about" }) }]} />
  </>);
}

function DetailScreen({ provId, go, showPace }) {
  const p = byId(provId);
  const sess = sessionsOf(p.id);
  const active = sess.filter((s) => !s.paused);
  const [note, focus] = useFocusNote();
  return (<>
    <ExtHeader kicker={p.name} meta={p.plan} title={p.title} sub={p.sub} onBack={() => go({ screen: "list" })} />
    <ExtSection label={p.via ? t("detail.limitsShared") : t("detail.limits")}>
      {p.windows.map((w) => <ExtMeterRow key={w.key} label={w.label} tag={w.key === p.binding ? t("detail.tightest") : ""} value={w.value} elapsed={w.elapsed} status={w.status} sub={w.sub} muted={!!p.via} showPace={showPace} />)}
    </ExtSection>
    {sess.length > 0 && (
      <ExtSection label={t("detail.sessions", { n: active.length })}>
        {active.map((s) => <ExtSessionRow key={s.tty} project={s.project} focused={!!note && note.key === s.p + s.tty} meta={sessionMeta(s)} onFocus={() => focus(s)} />)}
        <ExtListRow kicker={t("detail.sessionsKicker")} title={t("detail.viewAll")} meta={t("detail.counts", { a: active.length, p: sess.length - active.length })} onClick={() => go({ screen: "sessions", prov: p.id, filter: "active" })} />
      </ExtSection>
    )}
    <ExtFooter text={note ? note.text : t("list.updated")} actionLabel={t("detail.dashboard")} />
  </>);
}

function SessionsScreen({ provId, filter, go }) {
  const p = byId(provId);
  const sess = sessionsOf(p.id);
  const active = sess.filter((s) => !s.paused);
  const paused = sess.filter((s) => s.paused);
  const shown = filter === "paused" ? paused : active;
  const [note, focus] = useFocusNote();
  return (<>
    <ExtHeader kicker={p.name} meta={t("sessions.meta")} title={t("sessions.title", { name: p.name, n: active.length })} sub={t("sessions.sub", { a: active.length, p: paused.length, t: sess.length })} onBack={() => go({ screen: "detail", prov: p.id })} />
    <div style={{ padding: "0 18px 12px" }}>
      <ExtFilterChips options={[{ value: "active", label: t("sessions.active"), count: active.length }, { value: "paused", label: t("sessions.paused"), count: paused.length }]} value={filter} onChange={(f) => go({ filter: f })} />
    </div>
    <ExtSection>
      {shown.length ? shown.map((s) => <ExtSessionRow key={s.tty} project={s.project} paused={!!s.paused} focused={!!note && note.key === s.p + s.tty} meta={sessionMeta(s)} onFocus={() => focus(s)} />)
        : <div style={{ padding: "14px 18px", fontSize: 13, color: "var(--muted)" }}>{filter === "paused" ? t("sessions.noPaused") : t("sessions.noActive")}</div>}
    </ExtSection>
    <ExtFooter text={note ? note.text : t("list.updated")} />
  </>);
}

function GuideScreen({ go }) {
  return (<>
    <ExtHeader kicker={t("guide.kicker")} title={t("guide.title")} sub={t("guide.sub")} onBack={() => go({ screen: "list" })} />
    <ExtSection label={t("guide.status")}>
      <ExtGuideItem status="ok" title={t("guide.ok.t")} desc={t("guide.ok.d")} />
      <ExtGuideItem status="warn" title={t("guide.warn.t")} desc={t("guide.warn.d")} />
      <ExtGuideItem status="crit" title={t("guide.crit.t")} desc={t("guide.crit.d")} />
    </ExtSection>
    <ExtSection label={t("guide.meter")}>
      <ExtGuideItem marker="pace" title={t("guide.pace.t")} desc={t("guide.pace.d")} />
    </ExtSection>
    <ExtFooter text={t("list.updated")} />
  </>);
}

function AboutScreen({ go }) {
  return (<>
    <ExtHeader kicker={t("about.kicker")} title={t("about.title")} sub={t("about.sub")} onBack={() => go({ screen: "list" })} />
    <ExtSection>
      <ExtGuideItem title={t("about.ext")} desc={t("about.ver", { v: ABOUT.version, u: ABOUT.updated })} />
    </ExtSection>
    <div style={{ display: "flex", padding: "6px 18px 18px" }}>
      <ExtButton variant="secondary" block label={t("about.refresh")} />
    </div>
  </>);
}
if (window.__AIU_KIT__) Object.assign(window, { LandingScreen, EarlierScreen, ListScreen, DetailScreen, SessionsScreen, GuideScreen, AboutScreen });
