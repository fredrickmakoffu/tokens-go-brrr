const REL_REPO = "fredrickmakoffu/cursor-spend-monitor-releases";
const REL_URL = "https://github.com/" + REL_REPO + "/releases";
const PLATFORMS = [
  { id: "fedora", name: "Fedora", kindKey: "dl.kind.rpm", ext: ".rpm", cmd: (f) => "sudo dnf install ./" + f },
  { id: "debian", name: "Debian / Ubuntu", kindKey: "dl.kind.deb", ext: ".deb", cmd: (f) => "sudo apt install ./" + f },
  { id: "windows", name: "Windows", kindKey: "dl.kind.installer" },
  { id: "macos", name: "macOS", kindKey: "dl.kind.dmg" },
];
const FALLBACK_RELEASES = [{
  tag: "v0.6.1", date: "2026-10-09", url: REL_URL + "/tag/v0.6.1", notes: [],
  assets: [
    { name: "cursor-spend-monitor-0.6.1-1.fc44.noarch.rpm", size: 257000, url: REL_URL + "/download/v0.6.1/cursor-spend-monitor-0.6.1-1.fc44.noarch.rpm", sha: null },
    { name: "cursor-spend-monitor_0.6.1_all.deb", size: 106000, url: REL_URL + "/download/v0.6.1/cursor-spend-monitor_0.6.1_all.deb", sha: null },
  ],
}];
const fmtSize = (b) => b >= 1e6 ? I18N.num(b / 1e6, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " MB" : Math.round(b / 1000) + " KB";
const parseNotes = (body) => (body || "").split(/\r?\n/).map((l) => l.trim()).filter((l) => /^[-*] /.test(l)).map((l) => l.slice(2).replace(/\*\*|`/g, ""));

function useReleases() {
  const [rel, setRel] = React.useState({ list: FALLBACK_RELEASES, live: false });
  React.useEffect(() => {
    fetch("https://api.github.com/repos/" + REL_REPO + "/releases?per_page=10").then((r) => r.ok ? r.json() : Promise.reject())
      .then((data) => {
        const list = data.filter((r) => !r.draft).map((r) => ({
          tag: r.tag_name, date: (r.published_at || "").slice(0, 10), url: r.html_url, notes: parseNotes(r.body), prerelease: r.prerelease,
          assets: (r.assets || []).map((a) => ({ name: a.name, size: a.size, url: a.browser_download_url, sha: a.digest ? a.digest.replace(/^sha256:/, "") : null })),
        }));
        if (list.length) setRel({ list, live: true });
      }).catch(() => {});
  }, []);
  const latest = rel.list.find((r) => !r.prerelease) || rel.list[0];
  return { ...rel, latest };
}

function CopyLine({ text, b, dense }) {
  const [done, setDone] = React.useState(false);
  const copy = () => { try { navigator.clipboard.writeText(text); } catch (e) {} b.spendCopy(); setDone(true); setTimeout(() => setDone(false), 1600); };
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 8, border: "1px solid var(--color-divider)", padding: dense ? "8px 10px" : "10px 12px", background: "var(--color-surface, transparent)" }}>
      <code style={{ ...MONO, flex: 1, minWidth: 0, overflowWrap: "anywhere", lineHeight: 1.5 }}>{text}</code>
      <button onClick={copy} className="ext-row-hover" style={{ flex: "none", border: 0, background: "transparent", padding: "2px 4px", cursor: "pointer", ...HEAD, fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: done ? "var(--st-ok)" : "var(--muted)" }}>{done ? t("copy.copied") : t("copy.copy")}</button>
    </div>
  );
}

function PlatformCard({ p, asset, b }) {
  const [sha, setSha] = React.useState(false);
  const soon = !asset;
  return (
    <div className="blueprint" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14, minWidth: 0, opacity: soon ? 0.75 : 1 }}>
      <Corners />
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ ...HEAD, fontSize: 24, textTransform: "uppercase", letterSpacing: "0.02em" }}>{p.name}</span>
        <span style={{ fontSize: 13, color: "var(--muted)" }}>{t(p.kindKey) + (asset ? " · " + fmtSize(asset.size) : "")}</span>
      </div>
      {soon ? (
        <div style={{ border: "1px dashed var(--color-divider)", padding: "11px 12px", textAlign: "center", fontSize: 14, fontWeight: 600, color: "var(--muted)" }}>{t("dl.soon")}</div>
      ) : (<>
        <ExtButton variant="primary" block label={t("dl.button", { ext: p.ext })} onClick={() => window.open(asset.url, "_blank")} />
        <CopyLine text={p.cmd(asset.name)} b={b} dense />
        <button onClick={() => setSha(!sha)} style={{ alignSelf: "flex-start", border: 0, background: "transparent", padding: 0, cursor: "pointer", fontSize: 13, color: "var(--muted)", fontFamily: "var(--font-body)" }}>{(sha ? "▾ " : "▸ ") + t("dl.checksum")}</button>
        {sha && <code style={{ ...MONO, fontSize: 12, overflowWrap: "anywhere", color: "var(--muted)", marginTop: -6 }}>{asset.sha || t("dl.checksumFallback")}</code>}
      </>)}
    </div>
  );
}

function Downloads({ b, rel }) {
  const r = rel.latest;
  const find = (ext) => ext && r.assets.find((a) => a.name.endsWith(ext));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 16 }}>
        {PLATFORMS.map((p) => <PlatformCard key={p.id} p={p} asset={find(p.ext)} b={b} />)}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--color-divider)", paddingTop: 12 }}>
          <span style={KICK}>{t("dl.then1")}</span>
          <span style={{ fontSize: 15 }}>{t("dl.then1.text")}</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--color-divider)", paddingTop: 12 }}>
          <span style={KICK}>{t("dl.then2")}</span>
          <CopyLine text="cursor-spend-monitor setup" b={b} />
        </div>
      </div>
    </div>
  );
}

/* ---------- Releases ---------- */

const fileKind = (n) => /\.rpm$/.test(n) ? "RPM" : /\.deb$/.test(n) ? "DEB" : /\.(exe|msi)$/.test(n) ? "EXE" : /\.dmg$/.test(n) ? "DMG" : /sha256/i.test(n) ? "SUM" : "FILE";
const relAge = (d) => {
  const days = Math.floor((Date.now() - new Date(d + "T00:00:00Z").getTime()) / 864e5);
  if (!(days >= 0)) return "";
  if (days === 0) return t("age.today");
  if (days === 1) return t("age.yesterday");
  if (days < 31) return t("age.days", { n: days });
  const m = Math.round(days / 30.4);
  return m < 12 ? t("age.months", { n: m }) : t("age.years", { n: Math.round(m / 12) });
};

function Badge({ children, color }) {
  return <span style={{ ...KICK, color: color || "var(--muted)", border: "1px solid " + (color || "var(--color-divider)"), padding: "2px 6px", lineHeight: 1.2, flex: "none" }}>{children}</span>;
}

function FileRow({ a, b }) {
  const [copied, setCopied] = React.useState(false);
  const copySha = () => { try { navigator.clipboard.writeText(a.sha); } catch (e) {} b.spendCopy(); setCopied(true); setTimeout(() => setCopied(false), 1600); };
  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "6px 12px", padding: "9px 0", borderTop: "1px solid var(--color-divider)" }}>
      <Badge>{fileKind(a.name)}</Badge>
      <a href={a.url} style={{ ...MONO, fontSize: 12, flex: "1 1 220px", minWidth: 0, overflowWrap: "anywhere" }}>{a.name}</a>
      <span style={{ fontSize: 13, color: "var(--muted)", fontVariantNumeric: "tabular-nums", flex: "none" }}>{fmtSize(a.size)}</span>
      {a.sha && <button onClick={copySha} className="ext-row-hover" title={a.sha} style={{ flex: "none", border: 0, background: "transparent", padding: "2px 4px", cursor: "pointer", ...HEAD, fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: copied ? "var(--st-ok)" : "var(--muted)" }}>{copied ? t("rel.copied") : t("rel.copySha")}</button>}
    </div>
  );
}

function NoteList({ r }) {
  if (!r.notes.length) return <p style={{ margin: 0, fontSize: 14, color: "var(--muted)" }}>{t("rel.noNotes")}</p>;
  return (
    <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 8 }}>
      {r.notes.map((n) => (
        <li key={n} style={{ display: "flex", gap: 10, fontSize: 15, lineHeight: 1.45, textWrap: "pretty" }}>
          <span aria-hidden="true" style={{ ...HEAD, color: "var(--st-ok)", flex: "none" }}>+</span><span>{n}</span>
        </li>
      ))}
    </ul>
  );
}

function LatestRelease({ r, b }) {
  return (
    <div className="blueprint" style={{ padding: "clamp(18px, 3vw, 28px)", display: "flex", flexDirection: "column", gap: 20, minWidth: 0 }}>
      <Corners />
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ ...KICK, color: "var(--st-ok)" }}>{t("rel.latest")}</span>
          <span style={{ ...HEAD, fontSize: "clamp(48px, 7vw, 84px)", lineHeight: 0.9, letterSpacing: "-0.01em" }}>{r.tag}</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
          <span style={{ fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{r.date}</span>
          <span style={{ fontSize: 13, color: "var(--muted)" }}>{relAge(r.date)}</span>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <span style={KICK}>{t("rel.changed")}</span>
        <NoteList r={r} />
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span style={{ ...KICK, marginBottom: 8 }}>{t("rel.files", { n: r.assets.length })}</span>
        {r.assets.map((a) => <FileRow key={a.name} a={a} b={b} />)}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
        <ExtButton variant="secondary" label={t("rel.page")} onClick={() => window.open(r.url, "_blank")} />
        <span style={{ fontSize: 13, color: "var(--muted)" }}>{t("rel.verify")}</span>
      </div>
    </div>
  );
}

function PastRelease({ r, last, b }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "28px minmax(0, 1fr)", columnGap: 14 }}>
      <div aria-hidden="true" style={{ position: "relative" }}>
        <span style={{ position: "absolute", left: 13, top: 0, bottom: last ? "auto" : 0, height: last ? 22 : "auto", width: 1, background: "var(--color-divider)" }}></span>
        <span style={{ position: "absolute", left: 8, top: 18, width: 11, height: 11, boxSizing: "border-box", border: "2px solid " + (open ? "var(--st-ok)" : "var(--muted)"), background: "var(--color-bg)", transition: "border-color 150ms" }}></span>
      </div>
      <div style={{ minWidth: 0, paddingBottom: last ? 0 : 6 }}>
        <button className="ext-row-hover" aria-expanded={open} onClick={() => setOpen(!open)} style={{ width: "100%", display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "4px 14px", padding: "12px 0", border: 0, background: "transparent", color: "var(--color-text)", textAlign: "left", cursor: "pointer" }}>
          <span style={{ ...HEAD, fontSize: 26, lineHeight: 1 }}>{r.tag}</span>
          {r.prerelease && <Badge color="var(--st-warn)">{t("rel.pre")}</Badge>}
          <span style={{ fontSize: 13, color: "var(--muted)", fontVariantNumeric: "tabular-nums", flex: 1 }}>{r.date + " · " + relAge(r.date)}</span>
          <span style={{ ...HEAD, fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)" }}>{open ? t("rel.close") : t("rel.nFiles", { n: r.assets.length })}</span>
        </button>
        {open && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: "4px 0 20px" }}>
            <NoteList r={r} />
            <div>{r.assets.map((a) => <FileRow key={a.name} a={a} b={b} />)}</div>
            <a href={r.url} target="_blank" style={{ fontSize: 13 }}>{t("rel.page")}</a>
          </div>
        )}
      </div>
    </div>
  );
}

function Releases({ rel, b }) {
  const [all, setAll] = React.useState(false);
  const [head, ...past] = rel.list;
  const shown = all ? past : past.slice(0, 3);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <LatestRelease r={head} b={b} />
      {past.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ ...KICK, paddingBottom: 6 }}>{t("rel.earlier")}</span>
          {shown.map((r, i) => <PastRelease key={r.tag} r={r} b={b} last={i === shown.length - 1 && (all || past.length <= 3)} />)}
          {past.length > 3 && (
            <button className="ext-row-hover" onClick={() => setAll(!all)} style={{ alignSelf: "flex-start", marginLeft: 42, marginTop: 8, border: 0, background: "transparent", padding: "4px 0", cursor: "pointer", ...HEAD, fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)" }}>{all ? t("rel.fewer") : t("rel.more", { n: past.length - 3 })}</button>
          )}
        </div>
      )}
      <a href={REL_URL} target="_blank" style={{ fontSize: 14, paddingTop: 14, borderTop: "1px solid var(--color-divider)" }}>{t("rel.all")}</a>
    </div>
  );
}

const FACT_KEYS = ["bar", "popover", "insights"];
function Facts() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0 32px", marginBottom: 40 }}>
      {FACT_KEYS.map((k) => [t("fact." + k + ".t"), t("fact." + k + ".d")]).map(([title, d]) => (
        <div key={title} style={{ display: "flex", flexDirection: "column", gap: 6, padding: "14px 0", borderTop: "1px solid var(--color-divider)" }}>
          <span style={{ fontSize: 15, fontWeight: 600 }}>{title}</span>
          <span style={{ fontSize: 14, color: "var(--muted)", textWrap: "pretty" }}>{d}</span>
        </div>
      ))}
    </div>
  );
}

Object.assign(window, { REL_URL, useReleases, Downloads, Releases, Facts });
