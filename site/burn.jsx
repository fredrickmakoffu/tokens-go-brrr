const LIMIT = 200000;
const WINDOW_S = 300;
const BURN_KEY = "tgb-burn-v1";
const CLICK_COST = 1200;
const COPY_COST = 4000;

const fmtTok = (n) => n >= 1000 ? I18N.num(n / 1000, { minimumFractionDigits: n >= 100000 ? 0 : 1, maximumFractionDigits: n >= 100000 ? 0 : 1 }) + "k" : String(Math.round(n));
const fmtFull = (n) => I18N.num(Math.round(n));
const fmtDur = (s) => { s = Math.max(0, Math.round(s)); if (s < 60) return t("dur.s", { s }); const m = Math.floor(s / 60), r = s % 60; return r ? t("dur.ms", { m, s: r }) : t("dur.m", { m }); };
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
      const ts = Date.now(); setNow(ts);
      if (ts - wRef.current.start >= WINDOW_S * 1000) { samples.current = []; setW(freshWindow()); }
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
  if (limited) title = t("burn.limited");
  else if (status === "crit") title = eta ? t("burn.critEta", { dur: fmtDur(eta) }) : t("burn.critPct", { pct });
  else if (status === "warn") title = pct > elapsedPct ? t("burn.ahead") : t("burn.close");
  else if (pct < 8) title = t("burn.room");
  else title = pct > elapsedPct ? t("burn.ahead") : t("burn.under");
  const sub = t("burn.sub", { tokens: fmtFull(tokens), max: fmtFull(LIMIT), dur: fmtDur(resetIn) });

  const pctOf = (n) => Math.round(n / LIMIT * 100);
  const parts = [
    { key: "scroll", label: t("burn.scroll"), value: pctOf(w.scroll), sub: t("burn.scroll.sub", { tokens: fmtTok(w.scroll) }) },
    { key: "click", label: t("burn.clicks"), value: pctOf(w.click), sub: t("burn.clicks.sub", { n: w.clicks, cost: fmtTok(CLICK_COST) }) },
    { key: "copy", label: t("burn.copy"), value: pctOf(w.copy), sub: t("burn.copy.sub", { n: w.copies, cost: fmtTok(COPY_COST) }) },
  ];

  return {
    tokens, pct, status, elapsedPct, resetIn, rate, eta, limited, title, sub, parts, w,
    perPx: perPx.current, brrr: rate > 6000,
    spendCopy: () => add("copy", COPY_COST),
    reset: () => { samples.current = []; setW(freshWindow()); window.scrollTo({ top: 0 }); lastY.current = 0; },
  };
}

Object.assign(window, { LIMIT, WINDOW_S, CLICK_COST, COPY_COST, fmtTok, fmtFull, fmtDur, statusOf, useBurn });
