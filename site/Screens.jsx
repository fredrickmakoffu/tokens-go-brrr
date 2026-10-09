const { ExtHeader, ExtStats, ExtButton, ExtSection, ExtMeterRow, ExtListRow, ExtFooter, ExtSessionRow, ExtWindowPicker, ExtFilterChips, ExtGuideItem, ProviderIcon } = window.AIUsageDesignSystem_480680;
const byId = (id) => PROVIDERS.find((p) => p.id === id);
const sessionsOf = (id) => SESSIONS.filter((s) => s.p === id);
const sessionMeta = (s) => [s.model ? s.model + " via " + s.via : null, s.tty, s.paused ? "paused" : null].filter(Boolean).join(" · ");

function useFocusNote() {
  const [note, setNote] = React.useState(null);
  const focus = (s) => { setNote({ key: s.p + s.tty, text: "Focused " + s.project + " · " + s.tty }); clearTimeout(window.__ft); window.__ft = setTimeout(() => setNote(null), 2200); };
  return [note, focus];
}

function LandingScreen({ insId, fromEarlier, go }) {
  const ins = INSIGHTS.find((i) => i.id === insId);
  return (<>
    <ExtHeader kicker={"Insight · " + ins.kind} meta={ins.time} title={ins.title} sub={ins.sub} onBack={fromEarlier ? () => go({ screen: "earlier" }) : undefined} />
    <ExtStats items={ins.stats} />
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 18px", fontSize: 12, color: "var(--muted)" }}>
      <ProviderIcon provider="claude" size={13} /><span>Written by Claude Code from your token data</span>
    </div>
    <div style={{ display: "flex", gap: 8, padding: "4px 18px 18px" }}>
      <ExtButton variant="primary" block label="Continue to agents" onClick={() => go({ screen: "list" })} />
      <ExtButton variant="secondary" label="Earlier" onClick={() => go({ screen: "earlier" })} />
    </div>
  </>);
}

function EarlierScreen({ go }) {
  return (<>
    <ExtHeader kicker="Insights" meta="3 today" title="Earlier insights" sub="Written two or three times a day from your token data." onBack={() => go({ screen: "list" })} />
    <ExtSection>
      {INSIGHTS.map((i) => <ExtListRow key={i.id} kicker={i.kind + " · " + i.time} title={i.title} meta="Written by Claude Code" onClick={() => go({ screen: "landing", ins: i.id, fromEarlier: true })} />)}
    </ExtSection>
    <ExtFooter text="Next insight around 21:00" />
  </>);
}

function ListScreen({ go, showPace, win, setWin }) {
  const running = SESSIONS.filter((s) => !s.paused);
  const projects = new Set(running.map((s) => s.project)).size;
  return (<>
    <ExtHeader kicker="AI usage" meta="15:00" title="Claude Code runs out in ~40m." sub={"OpenCode has room. " + running.length + " agents running across " + projects + " projects."} />
    <ExtSection>
      {PROVIDERS.map((p) => {
        const w = p.windows.find((x) => x.kind === win) || p.windows.find((x) => x.key === p.binding);
        return <ExtMeterRow key={p.id} icon={p.id} label={p.name} tag={p.via ? "via " + p.via : w.label} value={w.value} elapsed={w.elapsed}
          status={p.via ? "ok" : w.status} muted={!!p.via} showPace={showPace}
          sub={p.via ? "Shares OpenCode limits · " + w.label.toLowerCase() + " " + w.value + "%" : w.sub}
          onClick={() => go({ screen: "detail", prov: p.id })} />;
      })}
    </ExtSection>
    <ExtWindowPicker options={WINDOWS} value={win} onChange={setWin} />
    <ExtFooter text="Updated 2m ago" actionLabel="Latest insight" onAction={() => go({ screen: "landing", ins: "act", fromEarlier: false })}
      actions={[{ label: "Guide", onClick: () => go({ screen: "guide" }) }, { label: "About", onClick: () => go({ screen: "about" }) }]} />
  </>);
}

function DetailScreen({ provId, go, showPace }) {
  const p = byId(provId);
  const sess = sessionsOf(p.id);
  const active = sess.filter((s) => !s.paused);
  const [note, focus] = useFocusNote();
  return (<>
    <ExtHeader kicker={p.name} meta={p.plan} title={p.title} sub={p.sub} onBack={() => go({ screen: "list" })} />
    <ExtSection label={p.via ? "Limits · shared with OpenCode Go" : "Limits"}>
      {p.windows.map((w) => <ExtMeterRow key={w.key} label={w.label} tag={w.key === p.binding ? "tightest" : ""} value={w.value} elapsed={w.elapsed} status={w.status} sub={w.sub} muted={!!p.via} showPace={showPace} />)}
    </ExtSection>
    {sess.length > 0 && (
      <ExtSection label={"Sessions · " + active.length + " running"}>
        {active.map((s) => <ExtSessionRow key={s.tty} project={s.project} focused={!!note && note.key === s.p + s.tty} meta={sessionMeta(s)} onFocus={() => focus(s)} />)}
        <ExtListRow kicker="Sessions" title="View all sessions" meta={active.length + " active · " + (sess.length - active.length) + " paused"} onClick={() => go({ screen: "sessions", prov: p.id, filter: "active" })} />
      </ExtSection>
    )}
    <ExtFooter text={note ? note.text : "Updated 2m ago"} actionLabel="Open dashboard" />
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
    <ExtHeader kicker={p.name} meta="Sessions" title={p.name + " has " + active.length + (active.length === 1 ? " agent" : " agents") + " running."} sub={active.length + " active · " + paused.length + " paused · " + sess.length + " total"} onBack={() => go({ screen: "detail", prov: p.id })} />
    <div style={{ padding: "0 18px 12px" }}>
      <ExtFilterChips options={[{ value: "active", label: "Active", count: active.length }, { value: "paused", label: "Paused", count: paused.length }]} value={filter} onChange={(f) => go({ filter: f })} />
    </div>
    <ExtSection>
      {shown.length ? shown.map((s) => <ExtSessionRow key={s.tty} project={s.project} paused={!!s.paused} focused={!!note && note.key === s.p + s.tty} meta={sessionMeta(s)} onFocus={() => focus(s)} />)
        : <div style={{ padding: "14px 18px", fontSize: 13, color: "var(--muted)" }}>{filter === "paused" ? "No paused sessions" : "No active sessions"}</div>}
    </ExtSection>
    <ExtFooter text={note ? note.text : "Updated 2m ago"} />
  </>);
}

function GuideScreen({ go }) {
  return (<>
    <ExtHeader kicker="Guide" title="Status colours" sub="Every meter writes its percentage beside it. The colour says how close it is." onBack={() => go({ screen: "list" })} />
    <ExtSection label="Status">
      <ExtGuideItem status="ok" title="Healthy" desc="Plenty of headroom — under 70% used." />
      <ExtGuideItem status="warn" title="Caution" desc="Getting close — 70 to 89% used." />
      <ExtGuideItem status="crit" title="Critical" desc="At or near your limit — 90% and up." />
    </ExtSection>
    <ExtSection label="Meter">
      <ExtGuideItem marker="pace" title="Pace tick" desc="The tick on each bar marks even pace." />
    </ExtSection>
    <ExtFooter text="Updated 2m ago" />
  </>);
}

function AboutScreen({ go }) {
  return (<>
    <ExtHeader kicker="About" title="AI usage" sub="Local GNOME Shell indicator for AI coding limits." onBack={() => go({ screen: "list" })} />
    <ExtSection>
      <ExtGuideItem title="Extension v2" desc={"Daemon v" + ABOUT.version + " · updated " + ABOUT.updated} />
    </ExtSection>
    <div style={{ display: "flex", padding: "6px 18px 18px" }}>
      <ExtButton variant="secondary" block label="Refresh now" />
    </div>
  </>);
}
if (window.__AIU_KIT__) Object.assign(window, { LandingScreen, EarlierScreen, ListScreen, DetailScreen, SessionsScreen, GuideScreen, AboutScreen });
