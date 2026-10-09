const PROVIDERS = [
  { id: "cursor", name: "Cursor", binding: "monthly", plan: "Pro",
    windows: [
      { key: "monthly", kind: "monthly", label: "Monthly", value: 74, elapsed: 60, sub: "Ahead of pace · out in ~6d, resets in 12d", status: "warn" },
      { key: "other", kind: "other", label: "Other models", value: 31, elapsed: 60, sub: "Resets in 12d", status: "ok" },
    ],
    title: "Cursor is ahead of pace.", sub: "74% of the monthly limit is used with 12 days left. At this rate it runs out in about 6 days." },
  { id: "claude", name: "Claude Code", binding: "5h", plan: "Max",
    windows: [
      { key: "5h", kind: "rolling", label: "5-hour", value: 93, elapsed: 55, sub: "Out in ~40m · resets in 2h 15m", status: "crit" },
      { key: "weekly", kind: "weekly", label: "Weekly", value: 81, elapsed: 43, sub: "Resets in 4d", status: "warn" },
    ],
    title: "Claude Code runs out in ~40m.", sub: "The 5-hour window is at 93% and resets in 2h 15m. Weekly is at 81%." },
  { id: "opencode", name: "OpenCode", binding: "weekly", plan: "Go", windows: null,
    title: "OpenCode has plenty of room.", sub: "Its tightest window is weekly at 33%, under pace. Resets in 2 days." },
  { id: "pi", name: "Pi", binding: "weekly", via: "OpenCode Go", plan: "", windows: null,
    title: "Pi spends OpenCode Go.", sub: "api-server meters against OpenCode’s limits. web-app runs on xAI, which has no tracked limit." },
];
const OC_WINDOWS = [
  { key: "5h", kind: "rolling", label: "5-hour", value: 15, elapsed: 3, sub: "Resets in 4h 50m", status: "ok" },
  { key: "weekly", kind: "weekly", label: "Weekly", value: 33, elapsed: 71, sub: "Under pace · resets in 2d", status: "ok" },
  { key: "monthly", kind: "monthly", label: "Monthly", value: 23, elapsed: 33, sub: "Resets in 20d", status: "ok" },
];
PROVIDERS.forEach((p) => { if (!p.windows) p.windows = OC_WINDOWS; });
const SESSIONS = [
  { p: "claude", project: "mobile-app", tty: "pts/7" },
  { p: "cursor", project: "mobile-app", tty: "pts/2" },
  { p: "cursor", project: "api-server", tty: "pts/3" },
  { p: "cursor", project: "cursor-folder", tty: "pts/4", paused: true },
  { p: "pi", project: "api-server", tty: "pts/5", model: "deepseek-v4-flash", via: "OpenCode Go" },
  { p: "pi", project: "web-app", tty: "pts/6", model: "grok-4.6", via: "xAI" },
];
const INSIGHTS = [
  { id: "act", kind: "Actionable", time: "Today 14:00",
    title: "Move to OpenCode before Claude Code’s 5-hour window closes.",
    sub: "Claude Code is at 93% and will hit its limit in about 40 minutes, well before the 2h 15m reset. OpenCode has 67% of its weekly limit free.",
    stats: [{ value: "93%", label: "Claude 5-hour" }, { value: "~40m", label: "until it runs out" }, { value: "67%", label: "OpenCode free" }] },
  { id: "cost", kind: "Model & cost", time: "Today 09:00",
    title: "deepseek-v4-flash did Pi’s heaviest work for $0.40.",
    sub: "It handled 2.1M tokens on api-server this week. The same tokens on grok-4.6 would have cost about $3.10.",
    stats: [{ value: "2.1M", label: "tokens" }, { value: "$0.40", label: "spent" }, { value: "7.8×", label: "cheaper than grok-4.6" }] },
  { id: "recap", kind: "Recap", time: "Yesterday 21:00",
    title: "This month: 154 sessions across 11 projects.",
    sub: "Claude Code did 71% of the work. 8.4M tokens in total, most of them on api-server.",
    stats: [{ value: "154", label: "sessions" }, { value: "8.4M", label: "tokens" }, { value: "71%", label: "by Claude Code" }] },
];
const WINDOWS = [{ value: "rolling", label: "5-hour" }, { value: "weekly", label: "Weekly" }, { value: "monthly", label: "Monthly" }];
const ABOUT = { version: "0.4.0", updated: "just now" };
if (window.__AIU_KIT__) Object.assign(window, { PROVIDERS, SESSIONS, INSIGHTS, WINDOWS, ABOUT });
