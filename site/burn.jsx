const LIMIT = 200000;
const WINDOW_S = 300;
const BURN_KEY = "tgb-burn-v1";
const CLICK_COST = 1200;
const COPY_COST = 4000;

const fmtTok = (n) => n >= 1000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1) + "k" : String(Math.round(n));
const fmtFull = (n) => Math.round(n).toLocaleString("en-US");
const fmtDur = (s) => { s = Math.max(0, Math.round(s)); if (s < 60) return s + "s"; const m = Math.floor(s / 60), r = s % 60; return r ? m + "m " + r + "s" : m + "m"; };
const statusOf = (pct) => pct >= 90 ? "crit" : pct >= 70 ? "warn" : "ok";

function freshWindow() { return { start: Date.now(), scroll: 0, click: 0, copy: 0, clicks: 0, copies: 0 }; }
function loadWindow() {
  try { const w = JSON.parse(localStorage.getItem(BURN_KEY)); if (w && Date.now() - w.start < WINDOW_S * 1000) return w; } catch (e) {}
  return freshWindow();
}

function useBurn(mult = 1) {
  const [w, setW] = React.useState(loadWindow);
  const [now, setNow] = React.useState(Date.now());
  const wRef = React.useRef(w); wRef.current = w;
  const multRef = React.useRef(mult); multRef.current = mult;
  const samples = React.useRef([]);
  const lastY = React.useRef(window.scrollY);
  const perPx = React.useRef(1);

  const total = (x) => x.scroll + x.click + x.copy;
  const add = (kind, n) => setW((x) => {
    if (total(x) >= LIMIT) return x;
    const room = LIMIT - total(x);
    const y = { ...x, [kind]: x[kind] + Math.min(room, n * multRef.current) };
    if (kind === "click") y.clicks = x.clicks + 1;
    if (kind === "copy") y.copies = x.copies + 1;
    return y;
  });

  React.useEffect(() => { try { localStorage.setItem(BURN_KEY, JSON.stringify(w)); } catch (e) {} }, [w]);

  React.useEffect(() => {
    const measure = () => { const max = document.documentElement.scrollHeight - innerHeight; perPx.current = 0.82 * LIMIT / Math.max(600, max); };
    measure();
    let raf = 0, pending = 0;
    const onScroll = () => {
      const y = window.scrollY; pending += Math.abs(y - lastY.current); lastY.current = y;
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; const px = pending; pending = 0; add("scroll", px * perPx.current); });
    };
    const onClick = () => add("click", CLICK_COST);
    const ro = new ResizeObserver(measure); ro.observe(document.body);
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("click", onClick, true);
    const tick = setInterval(() => {
      const t = Date.now(); setNow(t);
      if (t - wRef.current.start >= WINDOW_S * 1000) { samples.current = []; setW(freshWindow()); }
    }, 500);
    return () => { removeEventListener("scroll", onScroll); removeEventListener("click", onClick, true); clearInterval(tick); ro.disconnect(); };
  }, []);

  const tokens = total(w);
  samples.current.push({ t: now, v: tokens });
  samples.current = samples.current.filter((s) => now - s.t <= 4000);
  const first = samples.current[0];
  const rate = first && now - first.t > 300 ? Math.max(0, (tokens - first.v) / ((now - first.t) / 1000)) : 0;
  const pct = Math.min(100, Math.round(tokens / LIMIT * 100));
  const elapsedS = Math.min(WINDOW_S, (now - w.start) / 1000);
  const elapsedPct = Math.round(elapsedS / WINDOW_S * 100);
  const resetIn = WINDOW_S - elapsedS;
  const eta = rate > 50 ? (LIMIT - tokens) / rate : null;
  const status = statusOf(pct);
  const limited = tokens >= LIMIT - 1;

  let title;
  if (limited) title = "This page is out of tokens.";
  else if (status === "crit") title = eta ? "This page runs out in ~" + fmtDur(eta) + "." : "This page is at " + pct + "%.";
  else if (status === "warn") title = pct > elapsedPct ? "This page is ahead of pace." : "This page is getting close.";
  else if (pct < 8) title = "This page has plenty of room.";
  else title = pct > elapsedPct ? "This page is ahead of pace." : "This page is under pace.";
  const sub = fmtFull(tokens) + " of 200,000 tokens · resets in " + fmtDur(resetIn);

  const pctOf = (n) => Math.round(n / LIMIT * 100);
  const parts = [
    { key: "scroll", label: "Scrolling", value: pctOf(w.scroll), sub: fmtTok(w.scroll) + " tokens · scrolling back up is not refunded" },
    { key: "click", label: "Clicks", value: pctOf(w.click), sub: w.clicks + (w.clicks === 1 ? " click" : " clicks") + " · " + fmtTok(CLICK_COST) + " each" },
    { key: "copy", label: "Copying", value: pctOf(w.copy), sub: w.copies + (w.copies === 1 ? " command" : " commands") + " · " + fmtTok(COPY_COST) + " each" },
  ];

  return {
    tokens, pct, status, elapsedPct, resetIn, rate, eta, limited, title, sub, parts, w,
    perPx: perPx.current, brrr: rate > 6000,
    spendCopy: () => add("copy", COPY_COST),
    reset: () => { samples.current = []; setW(freshWindow()); window.scrollTo({ top: 0 }); lastY.current = 0; },
  };
}

const SITE = {
  privacy: [
    ["No cookies, no scraping", "Each provider reuses a login already on disk: Cursor's IDE state, Claude Code's OAuth file, OpenCode's API key."],
    ["Read, never written", "Claude Code owns its token refresh. The file is opened read-only, so the daemon cannot sign you out of the CLI."],
    ["The extension holds nothing", "It has no credentials and makes no network calls. It reads state from the daemon over the session bus."],
    ["History stays in ~/.local", "Polls and the usage ledger are kept in ~/.local/share/cursor-spend-monitor for 90 days. Set history_days to 0 to stop recording."],
    ["Only numbers travel", "Insight wording is a template unless you turn on llm_notifications. When it is on, no transcript text, prompts or file contents are sent."],
  ],
  faq: [
    ["Which tools does it track?", "Cursor, Claude Code, OpenCode and Codex report their own limits. Pi is a harness, so it borrows the meters of whichever account its sessions bill to."],
    ["Why does a row sometimes show no bar?", "xAI publishes no usage endpoint and Cline reports a credit balance, not a window. An empty bar at 0% would read as plenty left, so the row shows its sessions and no percentage."],
    ["Does a paused session count?", "No. A session suspended with Ctrl+Z spends nothing until you resume it, so it stays out of the top-bar count and shows as paused in the provider's detail screen."],
    ["Does opening the popover hit five APIs every time?", "It asks for a refresh, and the daemon drops the request if it polled in the last 60 seconds. Anthropic returns 429 on its usage route long before any quota is spent."],
    ["Can I use it from a status bar or a script?", "Yes. status prints the published state in about 0.1s with no network call. check exits non-zero when quota is low, and best names the provider with the most left."],
    ["Which GNOME versions?", "GNOME Shell 45 or newer. Log out and back in after installing so the shell picks up the extension."],
    ["Windows or macOS?", "Both are coming. Fedora and Debian/Ubuntu packages are available now."],
  ],
};

Object.assign(window, { LIMIT, WINDOW_S, CLICK_COST, COPY_COST, fmtTok, fmtFull, fmtDur, statusOf, useBurn, SITE });
