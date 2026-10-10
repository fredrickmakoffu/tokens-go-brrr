// Demo data for the live popover. Rebuilt from the catalog whenever the locale
// changes (see loadData), so the arrays are mutated in place: the screens read
// them as globals.
const PROVIDERS = [];
const SESSIONS = [
  { p: "claude", project: "maarifa-project", tty: "pts/7" },
  { p: "cursor", project: "maarifa-project", tty: "pts/2" },
  { p: "cursor", project: "optimus", tty: "pts/3" },
  { p: "cursor", project: "cursor-folder", tty: "pts/4", paused: true },
  { p: "pi", project: "optimus", tty: "pts/5", model: "deepseek-v4-flash", via: "OpenCode Go" },
  { p: "pi", project: "sundeskv2", tty: "pts/6", model: "grok-4.6", via: "xAI" },
];
const INSIGHTS = [];
const WINDOWS = [];
const ABOUT = { version: "0.4.0" };

function loadData() {
  const win = (key, kind, value, elapsed, sub, status, label) => ({ key, kind, label: label || t("win." + kind), value, elapsed, sub, status });
  const ocWindows = [
    win("5h", "rolling", 15, 3, t("d.opencode.rolling"), "ok"),
    win("weekly", "weekly", 33, 71, t("d.opencode.weekly"), "ok"),
    win("monthly", "monthly", 23, 33, t("d.opencode.monthly"), "ok"),
  ];
  PROVIDERS.length = 0;
  PROVIDERS.push(
    { id: "cursor", name: "Cursor", binding: "monthly", plan: "Pro",
      windows: [
        win("monthly", "monthly", 74, 60, t("d.cursor.monthly"), "warn"),
        win("other", "other", 31, 60, t("d.cursor.other"), "ok"),
      ],
      title: t("d.cursor.title"), sub: t("d.cursor.sub") },
    { id: "claude", name: "Claude Code", binding: "5h", plan: "Max",
      windows: [
        win("5h", "rolling", 93, 55, t("d.claude.rolling"), "crit"),
        win("weekly", "weekly", 81, 43, t("d.claude.weekly"), "warn"),
      ],
      title: t("d.claude.title"), sub: t("d.claude.sub") },
    { id: "opencode", name: "OpenCode", binding: "weekly", plan: "Go", windows: ocWindows,
      title: t("d.opencode.title"), sub: t("d.opencode.sub") },
    { id: "pi", name: "Pi", binding: "weekly", via: "OpenCode Go", plan: "", windows: ocWindows,
      title: t("d.pi.title"), sub: t("d.pi.sub") },
  );
  INSIGHTS.length = 0;
  INSIGHTS.push(
    { id: "act", kind: t("d.act.kind"), time: t("d.act.time"), title: t("d.act.title"), sub: t("d.act.sub"),
      stats: [{ value: "93%", label: t("d.act.s1") }, { value: "~40m", label: t("d.act.s2") }, { value: "67%", label: t("d.act.s3") }] },
    { id: "cost", kind: t("d.cost.kind"), time: t("d.cost.time"), title: t("d.cost.title"), sub: t("d.cost.sub"),
      stats: [{ value: "2.1M", label: t("d.cost.s1") }, { value: "$0.40", label: t("d.cost.s2") }, { value: "7.8×", label: t("d.cost.s3") }] },
    { id: "recap", kind: t("d.recap.kind"), time: t("d.recap.time"), title: t("d.recap.title"), sub: t("d.recap.sub"),
      stats: [{ value: "154", label: t("d.recap.s1") }, { value: "8.4M", label: t("d.recap.s2") }, { value: "71%", label: t("d.recap.s3") }] },
  );
  WINDOWS.length = 0;
  WINDOWS.push(
    { value: "rolling", label: t("win.rolling") },
    { value: "weekly", label: t("win.weekly") },
    { value: "monthly", label: t("win.monthly") },
  );
  ABOUT.updated = t("about.updated");
}
loadData();
I18N.subscribe(loadData);
if (window.__AIU_KIT__) Object.assign(window, { PROVIDERS, SESSIONS, INSIGHTS, WINDOWS, ABOUT });
