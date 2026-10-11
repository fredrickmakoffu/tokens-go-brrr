// tokens-go-brrr — GNOME Shell indicator matching design/menu-bar-concept.html.
// Data comes from the tokens-go-brrr daemon over D-Bus.

import Clutter from "gi://Clutter";
import GLib from "gi://GLib";
import GObject from "gi://GObject";
import Gio from "gi://Gio";
import Pango from "gi://Pango";
import St from "gi://St";

import * as Main from "resource:///org/gnome/shell/ui/main.js";
import * as PanelMenu from "resource:///org/gnome/shell/ui/panelMenu.js";
import * as PopupMenu from "resource:///org/gnome/shell/ui/popupMenu.js";
import { Extension } from "resource:///org/gnome/shell/extensions/extension.js";

import {
    duration,
    errorText,
    formatTokens,
    lcFirst,
    metricLabel,
    metricTag,
    resetsText,
    tr,
    ucFirst,
} from "./i18n.js";

const BUS_NAME = "io.github.fredrickmakoffu.TokensGoBrrr";
const OBJECT_PATH = "/io/github/fredrickmakoffu/TokensGoBrrr";
const IFACE_XML = `
<node>
  <interface name="io.github.fredrickmakoffu.TokensGoBrrr">
    <property name="Version" type="s" access="read"/>
    <method name="GetState"><arg type="s" direction="out" name="json"/></method>
    <method name="Refresh"/>
    <method name="SetPrimary">
      <arg type="s" direction="in" name="provider"/>
      <arg type="s" direction="in" name="metric"/>
    </method>
    <method name="Acknowledge">
      <arg type="u" direction="in" name="id"/>
    </method>
    <method name="LlmLog">
      <arg type="s" direction="in" name="day"/>
      <arg type="s" direction="out" name="json"/>
    </method>
    <method name="ClearLlmLog"/>
    <method name="Quit"/>
    <signal name="StateChanged"><arg type="s" name="json"/></signal>
  </interface>
</node>`;
const UsageProxy = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);

// Status colours and the two text colours set inline from JS. The stylesheet
// carries the rest, and its light overrides sit under .tokens-go-brrr-light; this table
// is the same split for the colours that are not in CSS. The light values are the
// website's, darkened until each reads at 4.5:1 on the paper surface.
const PALETTES = {
    dark: {
        ok: "#94bce3",
        wait: "#f0ba59",
        crit: "#fd7562",
        error: "#7a7a7d",
        muted: "#5d5d60",
        text: "#f5f5f8",
        mutedText: "#98989b",
    },
    light: {
        ok: "#416180",
        wait: "#a45900",
        crit: "#c83122",
        error: "#7a7a7d",
        muted: "#98989b",
        text: "#1d1f20",
        mutedText: "#5d5d60",
    },
};
// Mutated in place so every reader sees the active palette on its next render.
const COLOR = { ...PALETTES.dark };
const BADGE_FILES = {
    cursor: "cursor.png",
    claude: "claude.svg",
    codex: "codex.svg",
    opencode: "opencode.svg",
    pi: "pi.svg",
};
const CONFIG_PATH = GLib.build_filenamev([
    GLib.get_user_config_dir(),
    "tokens-go-brrr",
    "config.json",
]);
const SCREEN_EASE = 160;
// A row arrives just after the one above it, so the list reads as settling into
// place rather than being stamped down all at once.
const ROW_STAGGER = 34;
const ROW_EASE = 210;
const BAR_GROW = 420;

const CAUTION_AT = 70;
const CRITICAL_AT = 90;

function colorFor(pct) {
    if (pct >= CRITICAL_AT) return COLOR.crit;
    if (pct >= CAUTION_AT) return COLOR.wait;
    return COLOR.ok;
}

// The top bar sits on GNOME's panel, which is dark whatever the popover is.
function panelColorFor(pct) {
    if (pct >= CRITICAL_AT) return PALETTES.dark.crit;
    if (pct >= CAUTION_AT) return PALETTES.dark.wait;
    return PALETTES.dark.ok;
}

// The number is the headline of a meter, so it takes the status colour only
// once the meter is worth attention; a healthy figure stays in plain text, as
// in the design, where colour is kept for the rows that need it.
function statusTextColor(pct, muted = false) {
    if (muted) return COLOR.mutedText;
    return pct >= CAUTION_AT ? colorFor(pct) : COLOR.text;
}

// "5-hour limit" -> "5-hour": the tag sits beside the name, where "limit" is
// already understood.
function tagText(text) {
    return metricTag(text);
}

// How long until the meter runs out. The daemon sends seconds; a daemon older
// than this extension sends only an English label, which stands in for it.
function etaText(m) {
    if (Number.isFinite(m?.etaSeconds) && m.etaSeconds > 0)
        return duration(m.etaSeconds);
    return m?.eta || "";
}

// "Out in ~40m · resets in 2h 15m", the line under every meter.
function meterSub(m) {
    if (!m) return "";
    const parts = [];
    const eta = etaText(m);
    if (eta && clampPct(m.value) >= CAUTION_AT)
        parts.push(tr("meter.out", { dur: eta }));
    const resets = resetsText(m);
    if (resets) parts.push(parts.length ? lcFirst(resets) : resets);
    return ucFirst(parts.join(" · "));
}

// Window names shortened for the list screen, where every row carries one chip
// per window and the longest name decides how much room is left for the rest.
// The detail screen keeps the full name: it has the width, and an abbreviation
// with nothing beside it to decode it would just be a riddle.
const SHORT_LABELS = {
    "Rolling limit": "RL",
};

function shortLabel(text) {
    return SHORT_LABELS[text] ?? text ?? "—";
}

function activeSessions(tool) {
    return tool.instances?.active ?? 0;
}

// A harness (Pi) holds no subscription: it spends against whichever LLM account
// its sessions selected. `via` names that account, and `via.borrowed` means the
// meters on this tool are a copy of that account's own provider row.
function viaOf(tool) {
    return tool?.via ?? null;
}

// True when the row has a real limit to draw. A harness pointed at an account we
// cannot meter (xAI, Cline) is healthy and running, but has no percentage, and
// drawing an empty bar at 0% would read as "plenty left" rather than "unknown".
function hasMeters(tool) {
    return Array.isArray(tool?.metrics) && tool.metrics.length > 0;
}

// The account's own row already contributes these numbers, so a borrowed copy
// must not be counted a second time.
function ownsMeters(tool) {
    return hasMeters(tool) && !viaOf(tool)?.borrowed;
}

function sessionRows(tool) {
    const rows = tool.instances?.sessions;
    if (Array.isArray(rows) && rows.length) return rows;
    // Older daemons only shipped aggregated name lists.
    const out = [];
    for (const project of tool.instances?.projects ?? [])
        out.push({ project, paused: false });
    for (const project of tool.instances?.suspendedProjects ?? [])
        out.push({ project, paused: true });
    return out;
}

function sessionLabel(session) {
    if (session?.project) return session.project;
    if (session?.kind === "editor") return tr("session.desktop");
    return tr("session.generic");
}

function titleMentionsProject(title, project) {
    const idx = title.indexOf(project);
    if (idx < 0) return false;
    const before = idx === 0 ? "" : title[idx - 1];
    const afterIdx = idx + project.length;
    const after = afterIdx >= title.length ? "" : title[afterIdx];
    const isBoundary = (c) =>
        !c ||
        c === "/" ||
        c === "\\" ||
        c === ":" ||
        c === "~" ||
        c === "-" ||
        /\s/.test(c);
    return isBoundary(before) && isBoundary(after);
}

// Markers that usually appear in the window/tab title when that provider is the
// foreground process (agents often rewrite the title to their argv). A bare
// shell sitting in the same cwd must not light up the project chip.
const PROVIDER_TITLE_HINTS = {
    cursor: ["cursor-agent", "/bin/agent", " bin/agent", "agent --", "agent —"],
    claude: ["claude"],
    codex: ["codex"],
    opencode: ["opencode"],
};

function titleHasProviderProcess(title, toolId) {
    if (!title) return false;
    const hints = PROVIDER_TITLE_HINTS[toolId];
    if (!hints) return false;
    const lower = title.toLowerCase();
    return hints.some((hint) => lower.includes(hint.toLowerCase()));
}

// Classic GNOME Terminal plus Ptyxis (Fedora's current GNOME Terminal app).
// Anything else is ignored — better no project than a wrong one.
function isGnomeTerminalWindow(win) {
    if (!win) return false;
    const wm = (win.get_wm_class?.() || "").toLowerCase();
    const instance = (win.get_wm_class_instance?.() || "").toLowerCase();
    const appId = (win.get_gtk_application_id?.() || "").toLowerCase();
    return (
        appId === "org.gnome.terminal" ||
        appId === "org.gnome.ptyxis" ||
        wm === "gnome-terminal" ||
        wm === "org.gnome.terminal" ||
        wm === "ptyxis" ||
        wm === "org.gnome.ptyxis" ||
        instance === "gnome-terminal" ||
        instance === "org.gnome.terminal" ||
        instance === "ptyxis" ||
        instance === "org.gnome.ptyxis"
    );
}

function scoreTitleMatch(title, session) {
    if (!title || !session) return 0;
    const directory = session.directory || "";
    if (directory.length > 1 && title.includes(directory))
        return 1000 + directory.length;
    // Expand ~/path relative to home so shell titles match session directories.
    if (directory.length > 1) {
        const home = GLib.get_home_dir();
        if (home && directory.startsWith(home + "/")) {
            const tilde = `~/${directory.slice(home.length + 1)}`;
            if (title.includes(tilde)) return 900 + tilde.length;
        }
    }
    const project = session.project || "";
    if (project.length >= 2 && titleMentionsProject(title, project))
        return project.length;
    return 0;
}

function truncateProject(name, max = 18) {
    if (!name || name.length <= max) return name;
    return `${name.slice(0, Math.max(1, max - 1))}\u2026`;
}

function readCtxtSwitches(pid) {
    if (!pid) return -1;
    try {
        const [, bytes] = GLib.file_get_contents(`/proc/${pid}/status`);
        const text = new TextDecoder().decode(bytes);
        const vol = text.match(/voluntary_ctxt_switches:\s*(\d+)/);
        const non = text.match(/nonvoluntary_ctxt_switches:\s*(\d+)/);
        const a = vol ? parseInt(vol[1], 10) : 0;
        const b = non ? parseInt(non[1], 10) : 0;
        return a + b;
    } catch (e) {
        return -1;
    }
}

// The windows a provider can be asked to show. "other" is deliberately absent:
// Cursor's spend on non-included models is not a window, so it is never
// something to switch every row to.
const WINDOW_KINDS = [
    { kind: "rolling", key: "win.rolling" },
    { kind: "weekly", key: "win.weekly" },
    { kind: "monthly", key: "win.monthly" },
];

// A daemon that predates the kind field publishes none, and the daemon is a
// separate install from the extension — pip and a directory copy, updated at
// different times. Losing the whole picker in that window would look like the
// feature is broken rather than the daemon being behind, so the key and then
// the label stand in until it catches up. The daemon's own value always wins.
const KIND_BY_KEY = {
    five_hour: "rolling",
    rolling: "rolling",
    session: "rolling",
    daily: "rolling",
    seven_day: "weekly",
    seven_day_opus: "weekly",
    seven_day_sonnet: "weekly",
    weekly: "weekly",
    monthly: "monthly",
};

function kindOfMetric(m) {
    if (!m) return "other";
    if (m.kind) return m.kind;
    const byKey = KIND_BY_KEY[m.key];
    if (byKey) return byKey;
    const text = (m.label || "").toLowerCase();
    if (text.includes("week")) return "weekly";
    if (text.includes("month")) return "monthly";
    if (
        text.includes("hour") ||
        text.includes("rolling") ||
        text.includes("daily")
    )
        return "rolling";
    return "other";
}

function kindOf(tool) {
    return kindOfMetric(primaryOf(tool));
}

function windowsOffered(tools) {
    // Only offer a window some provider can actually show.
    const seen = new Set();
    for (const tool of tools)
        for (const m of tool.metrics ?? []) seen.add(kindOfMetric(m));
    return WINDOW_KINDS.filter((w) => seen.has(w.kind));
}

function selectedWindow(tools) {
    // Derived from what the rows are showing rather than stored separately, so
    // the picker cannot disagree with the panel it sits under — including after
    // a daemon restart, where the primaries come back from its config and any
    // remembered UI state would be a second, stale opinion.
    const tally = new Map();
    for (const tool of tools) {
        if (!hasMeters(tool) || !ownsMeters(tool)) continue;
        const kind = kindOf(tool);
        if (kind === "other") continue;
        tally.set(kind, (tally.get(kind) ?? 0) + 1);
    }
    let best = null;
    for (const [kind, count] of tally)
        if (!best || count > best[1]) best = [kind, count];
    return best ? best[0] : null;
}

function metric(tool, key) {
    return (tool.metrics ?? []).find((m) => m.key === key) ?? null;
}

function primaryOf(tool) {
    return metric(tool, tool.primary) ?? tool.metrics?.[0] ?? null;
}

function clampPct(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(100, n));
}

function relativeTime(iso) {
    if (!iso) return tr("time.never");
    const then = GLib.DateTime.new_from_iso8601(iso, null);
    if (!then) return tr("time.unknown");
    const secs = Math.max(
        0,
        Math.round(GLib.DateTime.new_now_utc().difference(then) / 1e6),
    );
    if (secs < 60) return tr("time.justNow");
    if (secs < 3600) return tr("time.minAgo", { n: Math.round(secs / 60) });
    if (secs < 86400) return tr("time.hourAgo", { n: Math.round(secs / 3600) });
    return tr("time.dayAgo", { n: Math.round(secs / 86400) });
}

function label(text, styleClass, extra = {}) {
    const l = new St.Label({ text, style_class: styleClass, ...extra });
    // St measures a label without its letter-spacing, so a tracked kicker comes
    // out a few pixels short of its own text and gets an ellipsis it does not
    // need. These are short and never wrap, so they are never truncated.
    l.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return l;
}

function wrappedLabel(text, styleClass, extra = {}) {
    const l = label(text, styleClass, { x_expand: true, ...extra });
    l.clutter_text.line_wrap = true;
    l.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
    l.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return l;
}

// Thin progress bar: .bar / .bar-fill in the mockup.
const Bar = GObject.registerClass(
    class TokensGoBrrrBar extends St.Widget {
        _init(pct, color, elapsed = null) {
            super._init({ style_class: "tokens-go-brrr-bar", x_expand: true });
            this._fill = new St.Widget({ style_class: "tokens-go-brrr-bar-fill" });
            this.add_child(this._fill);
            // The pace tick marks how far through its window the meter is: a
            // fill past the tick is spending faster than time is passing. Too
            // close to the left edge it says nothing, so it is left out.
            this._elapsed =
                Number.isFinite(elapsed) && elapsed > 8
                    ? Math.min(elapsed, 100)
                    : null;
            if (this._elapsed !== null) {
                this._tick = new St.Widget({ style_class: "tokens-go-brrr-bar-tick" });
                this.add_child(this._tick);
            }
            this.setValue(pct, color);
        }

        setValue(pct, color) {
            this._pct = clampPct(pct);
            this._fill.style = `background-color: ${color};`;
            this.queue_relayout();
        }

        prepareGrow() {
            // Collapsed just before the entry is scheduled, never on
            // construction: a screen is built on every daemon poll, and only
            // the path that also plays the entry is allowed to hide anything.
            this._fill.set_pivot_point(0, 0.5);
            this._fill.scale_x = 0;
        }

        settle() {
            this._fill.remove_all_transitions();
            this._fill.scale_x = 1;
        }

        grow() {
            // The fill is allocated at its true width and scaled in from the
            // left, so the animation never draws a value the meter does not
            // have. Deliberately an ease-out with no overshoot: a bar that
            // springs past its mark shows more usage than the provider
            // reported, and a quota display has no business exaggerating even
            // for a sixth of a second.
            if (!St.Settings.get().enable_animations) return;
            this._fill.ease({
                scale_x: 1,
                duration: BAR_GROW,
                mode: Clutter.AnimationMode.EASE_OUT_CUBIC,
            });
        }

        vfunc_allocate(box) {
            this.set_allocation(box);
            const content = this.get_theme_node().get_content_box(box);
            const width = Math.round(
                ((content.x2 - content.x1) * this._pct) / 100,
            );
            const childBox = new Clutter.ActorBox({
                x1: content.x1,
                y1: content.y1,
                x2: content.x1 + width,
                y2: content.y2,
            });
            this._fill.allocate(childBox);
            if (this._tick) {
                const x = Math.round(
                    content.x1 + ((content.x2 - content.x1) * this._elapsed) / 100,
                );
                this._tick.allocate(
                    new Clutter.ActorBox({
                        x1: x - 1,
                        y1: content.y1 - 3,
                        x2: x,
                        y2: content.y2 + 3,
                    }),
                );
            }
        }
    },
);

const BADGE_COLUMN_SPACING = 7;
const BADGE_ROW_SPACING = 4;

// Badges wrap onto further lines rather than overflowing the row. A provider can
// report more windows than fit across 360px (Claude adds Opus and Sonnet buckets),
// and Clutter's own FlowLayout stacks them at the same x instead of wrapping.
const BadgeFlow = GObject.registerClass(
    class TokensGoBrrrBadgeFlow extends St.Widget {
        _init() {
            super._init({ style_class: "tokens-go-brrr-meta", x_expand: true });
        }

        _badges() {
            return this.get_children().filter((child) => child.visible);
        }

        // Greedy line breaking, shared by height reporting and allocation so the two
        // can never disagree about how many lines there are.
        _lines(width) {
            const lines = [];
            let current = [];
            let used = 0;
            let lineHeight = 0;
            let total = 0;

            for (const child of this._badges()) {
                const [, childWidth] = child.get_preferred_width(-1);
                const [, childHeight] = child.get_preferred_height(childWidth);
                const needed = current.length
                    ? used + BADGE_COLUMN_SPACING + childWidth
                    : childWidth;

                if (current.length && needed > width) {
                    lines.push({ items: current, height: lineHeight });
                    total += lineHeight + BADGE_ROW_SPACING;
                    current = [];
                    used = 0;
                    lineHeight = 0;
                }

                used = current.length
                    ? used + BADGE_COLUMN_SPACING + childWidth
                    : childWidth;
                lineHeight = Math.max(lineHeight, childHeight);
                current.push({ child, width: childWidth, height: childHeight });
            }

            if (current.length) {
                lines.push({ items: current, height: lineHeight });
                total += lineHeight;
            }
            return { lines, height: total };
        }

        vfunc_get_preferred_width(_forHeight) {
            let min = 0;
            let natural = 0;
            this._badges().forEach((child, index) => {
                const [, childWidth] = child.get_preferred_width(-1);
                min = Math.max(min, childWidth); // never narrower than one badge
                natural += childWidth + (index ? BADGE_COLUMN_SPACING : 0);
            });
            return this.get_theme_node().adjust_preferred_width(min, natural);
        }

        vfunc_get_preferred_height(forWidth) {
            const themeNode = this.get_theme_node();
            const inner = themeNode.adjust_for_width(
                forWidth < 0 ? 0 : forWidth,
            );
            const { height } = this._lines(inner);
            return themeNode.adjust_preferred_height(height, height);
        }

        vfunc_allocate(box) {
            this.set_allocation(box);
            const content = this.get_theme_node().get_content_box(box);
            const { lines } = this._lines(content.x2 - content.x1);
            let y = content.y1;
            for (const line of lines) {
                let x = content.x1;
                for (const { child, width, height } of line.items) {
                    child.allocate(
                        new Clutter.ActorBox({
                            x1: x,
                            y1: y + Math.round((line.height - height) / 2),
                            x2: x + width,
                            y2:
                                y +
                                Math.round((line.height - height) / 2) +
                                height,
                        }),
                    );
                    x += width + BADGE_COLUMN_SPACING;
                }
                y += line.height + BADGE_ROW_SPACING;
            }
        }
    },
);

// Provider row (.row in the mockup). Activation navigates instead of closing the menu.
const Row = GObject.registerClass(
    {
        Signals: {
            navigate: {},
            select: { param_types: [GObject.TYPE_STRING] },
        },
    },
    class TokensGoBrrrRow extends PopupMenu.PopupBaseMenuItem {
        _init(icons, tool, bump, selectedKind = null) {
            const ok = !tool.status || tool.status === "ok";
            super._init({
                style_class: "tokens-go-brrr-row",
                reactive: ok,
                activate: ok,
                hover: ok,
                can_focus: ok,
            });
            if (!ok) this.add_style_class_name("tokens-go-brrr-row-disabled");

            const primary = primaryOf(tool);
            const pct = clampPct(primary?.value ?? 0);
            const via = viaOf(tool);
            // A borrowed meter belongs to another account, so it is drawn
            // quiet: the number is real, but it is not this tool's to spend.
            const muted = !!via?.borrowed;
            const color = muted ? COLOR.muted : colorFor(pct);
            // A harness with no reachable limit is fine, not broken: it keeps its
            // row and its session count, and simply shows no bar and no number.
            const metered = ok && hasMeters(tool);

            this.add_child(
                new St.Bin({
                    style_class: "tokens-go-brrr-badge",
                    y_align: Clutter.ActorAlign.START,
                    child: new St.Icon({
                        style_class: "tokens-go-brrr-badge-icon",
                        gicon: icons.badge(tool.icon),
                        icon_size: 15,
                        x_align: Clutter.ActorAlign.CENTER,
                        y_align: Clutter.ActorAlign.CENTER,
                    }),
                }),
            );

            const info = new St.BoxLayout({
                style_class: "tokens-go-brrr-info",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
                y_align: Clutter.ActorAlign.CENTER,
            });
            const nameRow = new St.BoxLayout({
                style_class: "tokens-go-brrr-name-row",
                x_expand: true,
            });
            nameRow.add_child(
                label(tool.name, "tokens-go-brrr-name", {
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            );
            const tag = via
                ? tr("row.via", { via: via.name })
                : metered
                  ? tagText(primary?.label)
                  : "";
            if (tag) {
                nameRow.add_child(
                    label(tag.toUpperCase(), "tokens-go-brrr-tag", {
                        y_align: Clutter.ActorAlign.CENTER,
                    }),
                );
            }
            nameRow.add_child(new St.Widget({ x_expand: true }));
            if (metered) {
                // Only a metered row has a number to show; an unmetered one
                // still opens, because its detail screen lists the sessions.
                this._value = label(`${Math.round(pct)}%`, "tokens-go-brrr-value", {
                    style: `color: ${statusTextColor(pct, muted)};`,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                nameRow.add_child(this._value);
            }
            info.add_child(nameRow);

            if (metered) {
                this._bar = new Bar(pct, color, primary?.elapsed);
                info.add_child(this._bar);
            }

            const running = ok ? activeSessions(tool) : 0;
            const sub = ok
                ? metered
                    ? via?.borrowed
                        ? tr("row.shares", { via: via.name })
                        : meterSub(primary)
                    : errorText(tool.error) || tool.status || tr("row.noLimits")
                : errorText(tool.error) || tool.status || tr("row.noLimits");
            const subText = [sub, running ? tr("row.running", { n: running }) : ""]
                .filter(Boolean)
                .join(" · ");
            if (subText) {
                info.add_child(
                    wrappedLabel(
                        subText,
                        pct >= CRITICAL_AT && metered && !muted
                            ? "tokens-go-brrr-sub crit"
                            : "tokens-go-brrr-sub",
                        pct >= CRITICAL_AT && metered && !muted
                            ? { style: `color: ${color};` }
                            : {},
                    ),
                );
            }
            this.add_child(info);

            if (ok) {
                this.add_child(
                    new St.Icon({
                        style_class: "tokens-go-brrr-chevron",
                        gicon: icons.chevronRight,
                        icon_size: 14,
                        y_align: Clutter.ActorAlign.START,
                    }),
                );
                if (metered && bump) this._bump();
                // The pointer taking over clears the keyboard accent, but never sets it.
                this.connect("notify::hover", () => {
                    if (this.hover) this._setKeyboardFocus(false);
                });
            } else {
                this.opacity = 140;
            }
        }

        // Mockup shows the accent bar only for :focus-visible, i.e. keyboard focus.
        // Driven purely by focus events: during key-focus-out the stage still reports
        // this actor as focused, so asking it there would re-add the class on the row
        // the pointer just left.
        _setKeyboardFocus(on) {
            if (on) this.add_style_class_name("tokens-go-brrr-keyboard-focus");
            else this.remove_style_class_name("tokens-go-brrr-keyboard-focus");
        }

        vfunc_key_focus_in() {
            super.vfunc_key_focus_in();
            this._setKeyboardFocus(!this.hover);
        }

        vfunc_key_focus_out() {
            super.vfunc_key_focus_out();
            this._setKeyboardFocus(false);
        }

        // .value.bump keyframes: scale to 1.14 and back over ~220ms.
        _bump() {
            const v = this._value;
            v.set_pivot_point(0.5, 0.5);
            v.ease({
                scale_x: 1.14,
                scale_y: 1.14,
                duration: 100,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                onComplete: () =>
                    v.ease({
                        scale_x: 1,
                        scale_y: 1,
                        duration: 120,
                        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                    }),
            });
        }

        activate(_event) {
            // Clicks on a badge belong to the badge (mockup: e.stopPropagation()).
            this.emit("navigate");
        }

        prepareEntry() {
            this.opacity = 0;
            this.translation_y = 6;
        }

        settle() {
            // Final state without animating, for any path that hid these
            // actors and then found it could not play the entry.
            this.remove_all_transitions();
            this.opacity = 255;
            this.translation_y = 0;
            this._bar?.settle?.();
        }

        enter(index) {
            // Each row arrives a beat after the one above it. The bar grows
            // once its row has landed, so the eye follows the list down and
            // then watches the meters fill, rather than everything moving at
            // once.
            this._bar?.grow?.();
            if (!St.Settings.get().enable_animations) return;
            const delay = index * ROW_STAGGER;
            this.ease({
                opacity: 255,
                translation_y: 0,
                delay,
                duration: ROW_EASE,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        }
    },
);

// What the featured AI's role means, in words the panel owns. The role itself
// is decided by the daemon from the ledger, never here.
// "2 active · 1 paused", each count agreeing with its own number.
function sessionCounts(active, paused) {
    return `${tr("sessions.nActive", { n: active })} · ${tr("sessions.nPaused", { n: paused })}`;
}

function kindCopy(kind) {
    return tr(`kind.${["actionable", "informative", "shareable", "fun"].includes(kind) ? kind : "other"}`);
}

// The first sentence of an insight is its title, the rest its sub line. The
// daemon writes one block of prose; the design sets it as a headline and a body.
function splitInsight(text) {
    const body = (text ?? "").trim();
    const m = body.match(/^(.+?[.!?])(\s+|$)/s);
    if (!m) return { title: body, sub: "" };
    return { title: m[1], sub: body.slice(m[0].length).trim() };
}

// "Today 14:00", "Yesterday 21:00", then the weekday and date.
function insightWhen(epoch) {
    if (!epoch) return "";
    const at = GLib.DateTime.new_from_unix_local(epoch);
    const now = GLib.DateTime.new_now_local();
    const time = at.format("%H:%M");
    const sameDay = at.format("%F") === now.format("%F");
    if (sameDay) return tr("time.today", { time });
    const yesterday = now.add_days(-1);
    if (at.format("%F") === yesterday.format("%F"))
        return tr("time.yesterday", { time });
    return `${at.format("%a %e %b")} ${time}`;
}

const ROLES = ["suggested", "leading", "value", "featured"];
function roleCopy(role) {
    return ROLES.includes(role) ? tr(`role.${role}`) : "";
}

// The message the way the daemon's template wrote it, in the user's language.
// Null when there is nothing to render from (a model reworded it, or the
// template is newer than this extension), and the stored English text is shown
// as written instead.
function templateText(template) {
    const p = template?.params ?? {};
    switch (template?.id) {
        case "digest": {
            const parts = [
                tr("tpl.digest.main", {
                    n: p.sessions ?? 0,
                    head: tr(`tpl.digest.head.${p.period}`),
                    tokens: formatTokens(p.tokens),
                }),
            ];
            if (p.leader)
                parts.push(tr("tpl.digest.leader", p.leader));
            if (p.topProject)
                parts.push(
                    tr("tpl.digest.project", {
                        n: p.topProject.sessions,
                        project: p.topProject.project,
                        tokens: formatTokens(p.topProject.tokens),
                    }),
                );
            if (p.topModel) parts.push(tr("tpl.digest.model", { model: p.topModel }));
            let text = `${parts.join(". ")}.`;
            if (p.estimate) text += tr("tpl.digest.estimate");
            if (p.vsLastMonth)
                text += tr(`tpl.digest.${p.vsLastMonth.dir === "down" ? "down" : "up"}`, {
                    pct: p.vsLastMonth.pct,
                });
            return text;
        }
        case "warm": {
            const work = p.sessions
                ? tr("tpl.warm.main", {
                      n: p.sessions,
                      hours: p.hours,
                      tokens: formatTokens(p.tokens),
                  }) +
                  (p.project ? tr("tpl.warm.project", { project: p.project }) : "") +
                  "."
                : tr("tpl.warm.none", { hours: p.hours });
            // Usage the meters saw and this machine did not: said first, because
            // it is the part a person could not have known.
            const away = p.elsewhere
                ? tr("tpl.warm.elsewhere", {
                      points: p.elsewhere.points,
                      provider: p.elsewhere.provider,
                      label: metricLabel(p.elsewhere.label),
                      time: GLib.DateTime.new_from_unix_local(p.elsewhere.since).format(
                          "%H:%M",
                      ),
                  })
                : "";
            let text = [away, work].filter(Boolean).join(" ");
            if (p.meter)
                text += tr("tpl.warm.meter", {
                    provider: p.meter.provider,
                    label: metricLabel(p.meter.label),
                    pct: p.meter.pct,
                });
            return text;
        }
        case "insight.cache":
            return tr(p.high ? "tpl.insight.cache.high" : "tpl.insight.cache.low", {
                pct: p.pct,
                days: p.days,
            });
        case "insight.week":
            return tr(`tpl.insight.week.${["up", "down"].includes(p.dir) ? p.dir : "flat"}`, {
                pct: p.pct,
                limit: p.limit,
            });
        case "insight.peak":
            return tr("tpl.insight.peak", {
                hour: `${String(p.hour).padStart(2, "0")}:00`,
                day: tr(`tpl.insight.day.${p.weekday}`),
            });
        case "insight.focus":
            return tr("tpl.insight.focus", {
                project: p.project,
                pct: p.pct,
                days: p.days,
            });
        case "insight.rhythm":
            return tr("tpl.insight.rhythm", { pct: p.pct });
        case "fun.cache":
            return tr("tpl.fun.cache", { pct: p.pct, tokens: formatTokens(p.tokens) });
        case "fun.streak":
            return tr("tpl.fun.streak", { n: p.current, longest: p.longest });
        case "fun.longest":
            return tr(p.project ? "tpl.fun.longest" : "tpl.fun.longestAnon", {
                dur: duration((p.minutes ?? 0) * 60),
                project: p.project,
            });
        case "share":
            return `${tr("tpl.share", {
                sessions: p.sessions,
                tokens: formatTokens(p.tokens),
            })}${p.model ? tr("tpl.share.model", { model: p.model }) : ""}.`;
        case "actionable": {
            const vars = {
                provider: p.provider,
                label: metricLabel(p.label),
                pct: p.percent,
            };
            let text = p.spent
                ? tr("tpl.actionable.spent", vars)
                : tr("tpl.actionable.at", vars) +
                  (p.etaSeconds
                      ? tr("tpl.actionable.eta", { dur: duration(p.etaSeconds) })
                      : "") +
                  ".";
            if (p.better) text += tr("tpl.actionable.better", { better: p.better });
            return text;
        }
        default:
            return null;
    }
}

function messageText(message) {
    return (
        (message?.template ? templateText(message.template) : null) ??
        message?.text ??
        ""
    );
}

// What Copy puts on the clipboard. A template-built share line is the same
// sentence as the message; otherwise the daemon's stored line is used.
function shareText(message) {
    if (message?.template?.id === "share") {
        const text = templateText(message.template);
        if (text) return text;
    }
    return message?.share ?? "";
}

const Indicator = GObject.registerClass(
    class TokensGoBrrrIndicator extends PanelMenu.Button {
        destroy() {
            if (this._schemeId) {
                this._interface.disconnect(this._schemeId);
                this._schemeId = 0;
            }
            if (this._noteId) {
                GLib.source_remove(this._noteId);
                this._noteId = 0;
            }
            super.destroy();
        }

        // Light only when GNOME says prefer-light. "default" is what most installs
        // sit on and it means no preference, and the shell's own panel and popups
        // stay dark either way, so dark is the safer reading of "default".
        _watchColorScheme() {
            this._interface = new Gio.Settings({
                schema_id: "org.gnome.desktop.interface",
            });
            const apply = (rerender) => {
                const light =
                    this._interface.get_string("color-scheme") === "prefer-light";
                Object.assign(COLOR, light ? PALETTES.light : PALETTES.dark);
                if (light) this.menu.actor.add_style_class_name("tokens-go-brrr-light");
                else this.menu.actor.remove_style_class_name("tokens-go-brrr-light");
                if (rerender) this._render(false);
            };
            this._schemeId = this._interface.connect(
                "changed::color-scheme",
                () => apply(true),
            );
            apply(false);
        }

        _init(ext) {
            super._init(0.5, tr("brand"), false);
            this.add_style_class_name("tokens-go-brrr-panel-button");
            this._ext = ext;
            this._icons = ext.icons;
            this._state = null; // parsed daemon state, or null when the daemon is away
            this._screen = "list";
            this._toolId = null;
            this._sessionsFilter = "active"; // 'active' | 'paused' on the sessions screen
            this._llmLog = null; // the daemon's LLM log payload for the day on screen
            this._llmOpen = new Set(); // entries expanded on the LLM activity screen
            this._lastSwapped = null;
            this._firstRender = true;
            this._probedMatch = null; // {toolId, project, title} from async pid probe
            this._probeTimeoutId = 0;
            this._probeSerial = 0;
            // The landing page opens once per message per session. Closing it
            // without pressing Continue must not make it nag on the next open,
            // so the id is recorded when it is shown, not when it is dismissed.
            this._landingShownId = null;
            this._landingMode = "fresh"; // "fresh" | "latest" | "message" (picked from Earlier)
            this._pickedMessage = null;
            this._footerNote = null;
            this._noteId = 0;
            // At most one landing page per open. The daemon is asked for state
            // when the popover opens, so a new message can arrive a moment
            // later; without this, Continue would show the *next* message
            // immediately instead of returning to the list.
            this._landingShownThisOpen = false;

            this._dot = new St.Widget({
                style_class: "tokens-go-brrr-dot",
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });
            // Sessions appear beside the dot only while something is running, so the
            // panel stays a bare dot when it has nothing to say.
            this._sessions = new St.BoxLayout({
                style_class: "tokens-go-brrr-sessions",
                y_align: Clutter.ActorAlign.CENTER,
            });
            // The dot keeps the mockup's bare look, so the usual full-height panel pill
            // is suppressed. This pill carries hover, press and focus instead, and it
            // wraps the session chips too: they are part of the same button, so the
            // whole indicator has to light up as one target.
            this._halo = new St.BoxLayout({
                style_class: "tokens-go-brrr-dot-halo",
                y_align: Clutter.ActorAlign.CENTER,
                accessible_name: tr("brand"),
            });
            this._halo.add_child(this._dot);
            this._halo.add_child(this._sessions);
            this.add_child(this._halo);

            // Focused GNOME Terminal → project name on the chip. Title notify covers
            // cd / tab renames without waiting for the daemon poll.
            this._focusWindowId = global.display.connect(
                "notify::focus-window",
                () => {
                    this._retargetFocusedTerminal();
                    this._updateSessions();
                },
            );
            this._focusedWin = null;
            this._focusTitleId = 0;
            this._retargetFocusedTerminal();
            this.connect("destroy", () => this._disconnectFocusWatch());

            this.menu.actor.add_style_class_name("tokens-go-brrr-menu");
            this._watchColorScheme();
            this.menu.connect("open-state-changed", (_menu, open) => {
                if (open) {
                    this._ext.refresh();
                    this._landingShownThisOpen = false;
                    const billboard = this._state?.billboard;
                    // The daemon decides whether anything is worth interrupting
                    // for: `billboard` is set only while a message is
                    // unacknowledged and still fresh. The once-per-session guard
                    // here is the only routing the extension does.
                    if (billboard && billboard.id !== this._landingShownId) {
                        this._landingShownId = billboard.id;
                        this._landingShownThisOpen = true;
                        this._landingMode = "fresh";
                        this._navigate("landing");
                    } else if (this._screen === "list") {
                        this._beginEntry();
                    } else {
                        this._navigate("list");
                    }
                } else if (this._entryId) {
                    GLib.source_remove(this._entryId);
                    this._entryId = 0;
                }
            });

            this._entryId = 0;
            this._entryRows = [];
            this._entryBars = [];
            this._render(false);
        }

        _disconnectFocusWatch() {
            if (this._focusWindowId) {
                global.display.disconnect(this._focusWindowId);
                this._focusWindowId = 0;
            }
            if (this._focusedWin && this._focusTitleId) {
                this._focusedWin.disconnect(this._focusTitleId);
                this._focusTitleId = 0;
            }
            this._focusedWin = null;
            this._cancelFocusProbe();
            this._probedMatch = null;
        }

        _cancelFocusProbe() {
            if (this._probeTimeoutId) {
                GLib.source_remove(this._probeTimeoutId);
                this._probeTimeoutId = 0;
            }
            this._probeSerial++;
        }

        _retargetFocusedTerminal() {
            this._cancelFocusProbe();
            if (this._focusedWin && this._focusTitleId) {
                this._focusedWin.disconnect(this._focusTitleId);
                this._focusTitleId = 0;
            }
            this._focusedWin = null;
            const win = global.display.focus_window;
            if (!isGnomeTerminalWindow(win)) {
                this._probedMatch = null;
                return;
            }
            this._focusedWin = win;
            this._focusTitleId = win.connect("notify::title", () =>
                this._updateSessions(),
            );
        }

        _focusedTerminalProject(tool) {
            const match = this._focusedTerminalMatch();
            return match?.toolId === tool.id ? match.project : null;
        }

        // Cursor agent titles are often "Chat name — /path/to/agent …" with no project
        // path, while OpenCode is usually the only session so a sole fallback works.
        // When the title clearly names a provider but not a folder, probe /proc ctxt
        // switches: focusing a Ptyxis tab SIGWINCHes that tab's process, which bumps
        // switches on the matching pid.
        _focusedTerminalMatch() {
            const win = global.display.focus_window;
            if (!isGnomeTerminalWindow(win)) {
                this._probedMatch = null;
                return null;
            }
            const title = win.get_title?.() || "";
            if (!title) {
                this._probedMatch = null;
                return null;
            }

            let best = null;
            const hintedTools = [];
            for (const tool of this.tools) {
                if (!activeSessions(tool)) continue;
                if (!titleHasProviderProcess(title, tool.id)) continue;
                hintedTools.push(tool);

                for (const session of sessionRows(tool)) {
                    if (session.paused) continue;
                    const score = scoreTitleMatch(title, session);
                    if (!score) continue;
                    if (!best || score > best.score)
                        best = {
                            toolId: tool.id,
                            project: session.project,
                            score,
                        };
                }
                if (!best || best.toolId !== tool.id) {
                    const running = sessionRows(tool).filter(
                        (s) => !s.paused && s.project,
                    );
                    if (running.length === 1) {
                        const score = 1;
                        if (!best || score > best.score)
                            best = {
                                toolId: tool.id,
                                project: running[0].project,
                                score,
                            };
                    }
                }
            }

            if (best?.project) {
                this._probedMatch = null;
                this._cancelFocusProbe();
                return best;
            }

            if (
                this._probedMatch &&
                this._probedMatch.title === title &&
                hintedTools.some((t) => t.id === this._probedMatch.toolId)
            )
                return this._probedMatch;

            if (hintedTools.length)
                this._scheduleFocusProbe(title, hintedTools);
            else this._probedMatch = null;

            return null;
        }

        _scheduleFocusProbe(title, tools) {
            this._cancelFocusProbe();
            const serial = this._probeSerial;
            const candidates = [];
            for (const tool of tools) {
                for (const session of sessionRows(tool)) {
                    if (session.paused || !session.project || !session.pid)
                        continue;
                    const before = readCtxtSwitches(session.pid);
                    if (before < 0) continue;
                    candidates.push({
                        toolId: tool.id,
                        project: session.project,
                        pid: session.pid,
                        before,
                    });
                }
            }
            if (!candidates.length) return;

            this._probeTimeoutId = GLib.timeout_add(
                GLib.PRIORITY_DEFAULT,
                140,
                () => {
                    this._probeTimeoutId = 0;
                    if (serial !== this._probeSerial) return GLib.SOURCE_REMOVE;
                    const win = global.display.focus_window;
                    if (
                        !isGnomeTerminalWindow(win) ||
                        (win.get_title?.() || "") !== title
                    )
                        return GLib.SOURCE_REMOVE;

                    let winner = null;
                    for (const c of candidates) {
                        const after = readCtxtSwitches(c.pid);
                        if (after < 0) continue;
                        const delta = after - c.before;
                        if (delta <= 0) continue;
                        if (!winner || delta > winner.delta)
                            winner = { ...c, delta };
                    }
                    if (winner) {
                        this._probedMatch = {
                            toolId: winner.toolId,
                            project: winner.project,
                            title,
                            score: winner.delta,
                        };
                        this._updateSessions();
                    }
                    return GLib.SOURCE_REMOVE;
                },
            );
        }

        setState(state) {
            this._state = state;
            const tools = this.tools;
            const onToolScreen =
                this._screen === "detail" || this._screen === "sessions";
            if (
                onToolScreen &&
                !tools.find(
                    (t) =>
                        t.id === this._toolId &&
                        (!t.status || t.status === "ok"),
                )
            ) {
                this._screen = "list";
                this._toolId = null;
            }
            this._updateDot();
            this._updateSessions();

            // The daemon is asked for state on open, so the answer -- possibly
            // carrying a message generated seconds ago -- lands after the
            // popover has already rendered the list. Take the turn then, but
            // only once per open and only from the list.
            const billboard = state?.billboard;
            if (
                this.menu.isOpen &&
                !this._landingShownThisOpen &&
                this._screen === "list" &&
                billboard &&
                billboard.id !== this._landingShownId
            ) {
                this._landingShownId = billboard.id;
                this._landingShownThisOpen = true;
                this._landingMode = "fresh";
                this._navigate("landing");
                return;
            }
            this._render(false);
        }

        get tools() {
            return Array.isArray(this._state?.tools) ? this._state.tools : [];
        }

        _updateDot() {
            // Only rows that own their meters vote. A harness borrowing another
            // account's limits would otherwise give that subscription two votes.
            const values = this.tools
                .filter(
                    (t) => (!t.status || t.status === "ok") && ownsMeters(t),
                )
                .map((t) => clampPct(primaryOf(t)?.value ?? 0));
            let level = "error";
            if (values.length) {
                const worst = Math.max(...values);
                level =
                    worst >= 90 ? "critical" : worst >= 70 ? "caution" : "ok";
            }
            for (const cls of ["caution", "critical", "error"])
                this._dot.remove_style_class_name(cls);
            if (level !== "ok") this._dot.add_style_class_name(level);
            // A quiet hint that the popover has something to say, so the
            // landing page is discoverable rather than a surprise.
            if (this._state?.billboard)
                this._dot.add_style_class_name("has-update");
            else this._dot.remove_style_class_name("has-update");
        }

        // The percentage rides along only once a provider reaches caution. Below that
        // the number is noise, and three providers' worth of it would crowd the bar.
        // When the focused window is GNOME Terminal (or Ptyxis) and its title maps to
        // a known session, the project name sits between the icon and ×N.
        _updateSessions() {
            this._sessions.destroy_all_children();
            for (const tool of this.tools) {
                const running = activeSessions(tool);
                if (!running) continue;

                const chip = new St.BoxLayout({
                    style_class: "tokens-go-brrr-session",
                    y_align: Clutter.ActorAlign.CENTER,
                });
                chip.add_child(this._sessionBadge(tool));

                const project = this._focusedTerminalProject(tool);
                if (project) {
                    chip.add_child(
                        label(
                            truncateProject(project),
                            "tokens-go-brrr-session-project",
                            {
                                y_align: Clutter.ActorAlign.CENTER,
                            },
                        ),
                    );
                }

                // No meters means no number: a harness on an account we cannot poll
                // still shows that it is running, and says nothing it cannot know.
                const pct = clampPct(primaryOf(tool)?.value ?? 0);
                if (hasMeters(tool) && pct >= CAUTION_AT) {
                    chip.add_child(
                        label(`${Math.round(pct)}%`, "tokens-go-brrr-session-pct", {
                            style: `color: ${panelColorFor(pct)};`,
                            y_align: Clutter.ActorAlign.CENTER,
                        }),
                    );
                }
                chip.add_child(
                    label(`\u00d7${running}`, "tokens-go-brrr-session-count", {
                        y_align: Clutter.ActorAlign.CENTER,
                    }),
                );
                this._sessions.add_child(chip);
            }
        }

        // A harness gets its own logo with the backend's logo tucked into the corner,
        // so the bar answers both "what am I running" and "whose quota is it" in the
        // width of one icon. A backend with no logo of its own just gets the harness.
        _sessionBadge(tool) {
            const icon = () =>
                new St.Icon({
                    style_class: "tokens-go-brrr-session-icon",
                    gicon: this._icons.badge(tool.icon),
                    icon_size: 14,
                    y_align: Clutter.ActorAlign.CENTER,
                });

            const via = viaOf(tool);
            const backendIcon = via?.providerId
                ? BADGE_FILES[via.providerId]
                : null;
            if (!backendIcon) return icon();

            const stack = new St.Widget({
                layout_manager: new Clutter.BinLayout(),
                style_class: "tokens-go-brrr-session-stack",
                y_align: Clutter.ActorAlign.CENTER,
            });
            stack.add_child(icon());
            stack.add_child(
                new St.Icon({
                    style_class: "tokens-go-brrr-session-via",
                    gicon: this._icons.badge(via.providerId),
                    icon_size: 9,
                    x_align: Clutter.ActorAlign.END,
                    y_align: Clutter.ActorAlign.END,
                }),
            );
            return stack;
        }

        _navigate(screen, toolId = null) {
            this._screen = screen;
            if (toolId !== null && toolId !== undefined) this._toolId = toolId;
            if (screen === "sessions") this._sessionsFilter = "active";
            this._render(true);
        }

        _render(animate) {
            this.menu.box.destroy_all_children();
            this._entryRows = [];
            this._entryBars = [];
            const screen = new St.BoxLayout({
                style_class: "tokens-go-brrr-screen",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            if (this._screen === "detail") this._renderDetail(screen);
            else if (this._screen === "sessions") this._renderSessions(screen);
            else if (this._screen === "landing") this._renderLanding(screen);
            else if (this._screen === "earlier") this._renderEarlier(screen);
            else if (this._screen === "guide") this._renderGuide(screen);
            else if (this._screen === "about") this._renderAbout(screen);
            else if (this._screen === "llmlog") this._renderLlmLog(screen);
            else this._renderList(screen);
            this.menu.box.add_child(screen);

            // .screen.enter → opacity 0 / translateY(4px) → settle over 160ms
            if (animate && this.menu.isOpen) {
                screen.opacity = 0;
                screen.translation_y = 4;
                screen.ease({
                    opacity: 255,
                    translation_y: 0,
                    duration: SCREEN_EASE,
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                });
                this._beginEntry();
            }
        }

        _beginEntry() {
            // Hiding and revealing must be governed by one condition. They were
            // not: rows were hidden on every render and revealed only on the
            // animated path, so each daemon poll rebuilt the list invisible and
            // left it that way until the menu was reopened.
            if (!this.menu.isOpen) return;
            if (!St.Settings.get().enable_animations) return;
            for (const row of this._entryRows ?? []) row.prepareEntry();
            for (const bar of this._entryBars ?? []) bar.prepareGrow();
            this._queueEntry();
        }

        _queueEntry() {
            // One turn of the loop later, so the rows have been allocated. An
            // ease started on an actor that has not been laid out yet settles
            // on its first frame, which is how this animation silently did
            // nothing at all until it was measured.
            if (this._entryId) return;
            this._entryId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                this._entryId = 0;
                this._playEntry();
                return GLib.SOURCE_REMOVE;
            });
        }

        _playEntry() {
            const rows = this._entryRows ?? [];
            const bars = this._entryBars ?? [];
            if (!this.menu.isOpen) {
                // Closed before the entry could run. These actors were hidden
                // for it, so put them back rather than leaving them invisible.
                for (const row of rows) row.settle();
                for (const bar of bars) bar.settle();
                return;
            }
            rows.forEach((row, index) => row.enter(index));
            for (const bar of bars) bar.grow();
        }

        // -- shared screen parts, after the design system's Ext components ----

        // ExtHeader: kicker and meta on one line, then a sentence title and a
        // sub line. The back arrow, when there is one, leads the kicker.
        _screenHeader({ kicker, meta = "", title, sub = "", back = null }) {
            const box = new St.BoxLayout({
                style_class: "tokens-go-brrr-hdr",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            const top = new St.BoxLayout({
                style_class: "tokens-go-brrr-hdr-top",
                x_expand: true,
            });
            if (back) {
                const button = new St.Button({
                    style_class: "tokens-go-brrr-back",
                    can_focus: true,
                    accessible_name: tr("ui.back"),
                    y_align: Clutter.ActorAlign.CENTER,
                    child: new St.Icon({
                        style_class: "tokens-go-brrr-back-icon",
                        gicon: this._icons.chevronLeft,
                        icon_size: 16,
                    }),
                });
                button.connect("clicked", back);
                top.add_child(button);
            }
            top.add_child(
                // The product name is a name, not a label: it keeps its own case.
                label(kicker === tr("brand") ? kicker : kicker.toUpperCase(), "tokens-go-brrr-kicker", {
                    x_expand: true,
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            );
            if (meta)
                top.add_child(
                    label(meta.toUpperCase(), "tokens-go-brrr-kicker", {
                        y_align: Clutter.ActorAlign.CENTER,
                    }),
                );
            box.add_child(top);
            box.add_child(wrappedLabel(title, "tokens-go-brrr-title"));
            if (sub) box.add_child(wrappedLabel(sub, "tokens-go-brrr-hdr-sub"));
            return box;
        }

        // ExtSection: a group of rows under a top rule, with an optional label.
        _section(text = "") {
            const box = new St.BoxLayout({
                style_class: "tokens-go-brrr-section",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            if (text) box.add_child(label(text.toUpperCase(), "tokens-go-brrr-section-label"));
            return box;
        }

        // ExtFooter: status text on the left, ghost actions, then Settings.
        _footer(text, actions = [], withSettings = false) {
            const bar = new St.BoxLayout({
                style_class: "tokens-go-brrr-footer",
                x_expand: true,
            });
            bar.add_child(
                label(text, "tokens-go-brrr-footer-text", {
                    x_expand: true,
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            );
            const add = (text_, cb) => {
                const b = new St.Button({
                    style_class: "tokens-go-brrr-ghost-btn",
                    label: text_,
                    can_focus: true,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                b.connect("clicked", cb);
                bar.add_child(b);
            };
            for (const { label: text_, cb } of actions) add(text_, cb);
            if (withSettings) add(tr("ui.settings"), () => this._openSettings());
            return bar;
        }

        // ExtListRow: kicker, title and meta, with a chevron. For drill-downs
        // that are not meters.
        _listRow(kicker, title, meta, cb) {
            const row = new St.Button({
                style_class: "tokens-go-brrr-list-row",
                can_focus: true,
                x_expand: true,
            });
            const box = new St.BoxLayout({ x_expand: true });
            const text = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            text.add_child(label(kicker.toUpperCase(), "tokens-go-brrr-kicker"));
            text.add_child(wrappedLabel(title, "tokens-go-brrr-list-title"));
            if (meta) text.add_child(wrappedLabel(meta, "tokens-go-brrr-sub"));
            box.add_child(text);
            box.add_child(
                new St.Icon({
                    style_class: "tokens-go-brrr-chevron",
                    gicon: this._icons.chevronRight,
                    icon_size: 14,
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            );
            row.set_child(box);
            row.connect("clicked", cb);
            return row;
        }

        // ExtGuideItem: a mark, a title and a description.
        _guideItem(color, title, desc, mark = "square") {
            const item = new St.BoxLayout({
                style_class: "tokens-go-brrr-guide-item",
                x_expand: true,
            });
            if (mark === "pace") {
                item.add_child(
                    new St.Widget({
                        style_class: "tokens-go-brrr-guide-tick",
                        y_align: Clutter.ActorAlign.START,
                    }),
                );
            } else if (color) {
                item.add_child(
                    new St.Widget({
                        style_class: "tokens-go-brrr-guide-dot",
                        style: `background-color: ${color};`,
                        y_align: Clutter.ActorAlign.START,
                        y_expand: false,
                    }),
                );
            }
            const text = new St.BoxLayout({
                style_class: "tokens-go-brrr-guide-text",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            text.add_child(label(title, "tokens-go-brrr-guide-title"));
            text.add_child(wrappedLabel(desc, "tokens-go-brrr-guide-desc"));
            item.add_child(text);
            return item;
        }

        _clock() {
            return GLib.DateTime.new_now_local().format("%H:%M");
        }

        _updatedText() {
            return tr("ui.updated", { ago: relativeTime(this._state?.updated_at) });
        }

        // The tightest meter across providers that own their numbers, with the
        // sentence the list and the detail screens open on.
        _tightest(tools) {
            let found = null;
            for (const tool of tools) {
                if (!ownsMeters(tool) || (tool.status && tool.status !== "ok"))
                    continue;
                for (const m of tool.metrics) {
                    const pct = clampPct(m.value);
                    if (!found || pct > found.pct) found = { tool, m, pct };
                }
            }
            return found;
        }

        _tightestMetric(tool) {
            return [...(tool.metrics ?? [])].sort((a, b) => b.value - a.value)[0] ?? null;
        }

        _meterSentence(tool, metric = null) {
            const via = viaOf(tool);
            if (via?.borrowed) {
                return {
                    title: tr("tool.spends", { name: tool.name, via: via.name }),
                    sub: tr("tool.spendsSub", { via: via.name }),
                };
            }
            const primary = metric ?? this._tightestMetric(tool);
            if (!hasMeters(tool) || !primary) {
                return {
                    title: tr("tool.noLimits", { name: tool.name }),
                    sub: errorText(tool.error) || tr("tool.noLimitsSub"),
                };
            }
            const pct = Math.round(clampPct(primary.value));
            const others = tool.metrics
                .filter((m) => m.key !== primary.key)
                .sort((a, b) => b.value - a.value)[0];
            const tail = others
                ? ` ${tr("sent.at", {
                      label: metricLabel(others.label),
                      pct: Math.round(clampPct(others.value)),
                  })}`
                : "";
            const label = metricLabel(primary.label);
            let window;
            if (Number.isFinite(primary.resetsSeconds)) {
                window =
                    primary.resetsSeconds > 0
                        ? tr("sent.atResets", {
                              label,
                              pct,
                              dur: duration(primary.resetsSeconds),
                          })
                        : tr("sent.atSoon", { label, pct });
            } else {
                window = tr("sent.at", { label, pct });
            }
            const eta = etaText(primary);
            if (eta && pct >= CAUTION_AT)
                return {
                    title: tr("tool.runsOut", { name: tool.name, dur: eta }),
                    sub: `${window}${tail}`,
                };
            if (pct >= CRITICAL_AT)
                return {
                    title: tr("tool.at", { name: tool.name, pct }),
                    sub: `${window}${tail}`,
                };
            if (pct >= CAUTION_AT)
                return {
                    title: tr("tool.close", { name: tool.name }),
                    sub: `${window}${tail}`,
                };
            return {
                title: tr("tool.room", { name: tool.name }),
                sub: `${window}${tail}`,
            };
        }

        _note(text) {
            // A short confirmation in the footer, then back to the status line.
            this._footerNote = text;
            if (this._noteId) GLib.source_remove(this._noteId);
            this._noteId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2200, () => {
                this._noteId = 0;
                this._footerNote = null;
                if (this._screen === "detail" || this._screen === "sessions")
                    this._render(false);
                return GLib.SOURCE_REMOVE;
            });
            this._render(false);
        }

        // Raise the terminal a session runs in. Windows are matched by their
        // title mentioning the project, the same way the top bar finds the
        // focused one; a session with no matching window says so.
        _focusSession(session) {
            const project = session?.project;
            const actors = project ? global.get_window_actors() : [];
            const win = actors
                .map((a) => a.meta_window)
                .find(
                    (w) =>
                        w &&
                        !w.is_skip_taskbar() &&
                        titleMentionsProject(w.get_title() ?? "", project),
                );
            if (!win) {
                this._note(
                    tr("session.noWindow", {
                        project: project ?? tr("session.thisSession"),
                    }),
                );
                return;
            }
            this.menu.close();
            Main.activateWindow(win);
        }

        _sessionMeta(session) {
            return [
                session.backend?.model
                    ? session.backend.name
                        ? tr("session.via", {
                              model: session.backend.model,
                              via: session.backend.name,
                          })
                        : session.backend.model
                    : null,
                session.tty || null,
                session.paused ? tr("session.paused") : null,
            ]
                .filter(Boolean)
                .join(" · ");
        }

        // ExtSessionRow: a status mark, the project, its facts, and Focus.
        _sessionRow(session) {
            const row = new St.BoxLayout({
                style_class: "tokens-go-brrr-session-row",
                x_expand: true,
            });
            row.add_child(
                new St.Widget({
                    style_class: session.paused
                        ? "tokens-go-brrr-session-mark paused"
                        : "tokens-go-brrr-session-mark",
                    y_align: Clutter.ActorAlign.START,
                }),
            );
            const text = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            text.add_child(label(sessionLabel(session), "tokens-go-brrr-session-name"));
            const meta = this._sessionMeta(session);
            if (meta) text.add_child(label(meta, "tokens-go-brrr-sub"));
            row.add_child(text);
            if (!session.paused && session.project) {
                const focus = new St.Button({
                    style_class: "tokens-go-brrr-focus-btn",
                    label: tr("ui.focus"),
                    can_focus: true,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                focus.connect("clicked", () => this._focusSession(session));
                row.add_child(focus);
            }
            return row;
        }

        // -- screens -----------------------------------------------------------

        _renderList(screen) {
            const tools = this.tools;
            const tight = this._tightest(tools);
            const running = tools.reduce((n, t) => n + activeSessions(t), 0);
            const projects = new Set(
                tools.flatMap((t) => t.instances?.projects ?? []),
            ).size;
            let title = tr("brand");
            let sub = this._updatedText();
            if (tight) {
                const s = this._meterSentence(tight.tool, tight.m);
                title = s.title;
                const others = tools.filter(
                    (t) => t !== tight.tool && ownsMeters(t) && hasMeters(t),
                );
                const roomy = others
                    .map((t) => ({ t, p: clampPct(primaryOf(t)?.value ?? 100) }))
                    .sort((a, b) => a.p - b.p)[0];
                sub = [
                    roomy && roomy.p < CAUTION_AT
                        ? tr("list.roomy", { name: roomy.t.name })
                        : "",
                    running
                        ? `${tr("list.agents", { n: running })}${
                              projects ? ` ${tr("list.projects", { n: projects })}` : ""
                          }.`
                        : "",
                ]
                    .filter(Boolean)
                    .join(" ");
                if (!sub) sub = s.sub;
            }
            screen.add_child(
                this._screenHeader({ kicker: tr("brand"), meta: this._clock(), title, sub }),
            );
            // The daemon is reading the last few hours behind this screen. Shown
            // only while it works (and for a few seconds at most), then a new
            // note may arrive; an unchanged picture simply makes the line vanish.
            if (this._state?.live?.catchingUp)
                screen.add_child(label(tr("live.catchingUp"), "tokens-go-brrr-sessions-empty"));
            if (!tools.length) {
                const text = this._state
                    ? tr("empty.noProviders")
                    : tr("empty.noDaemon", {
                          cmd: "systemctl --user start tokens-go-brrr",
                      });
                screen.add_child(wrappedLabel(text, "tokens-go-brrr-empty"));
                screen.add_child(this._footer("", [], true));
                return;
            }
            const section = this._section();
            const selectedKind = selectedWindow(tools);
            const rows = [];
            for (const tool of tools) {
                const row = new Row(
                    this._icons,
                    tool,
                    this._lastSwapped === tool.id,
                    selectedKind,
                );
                row.connect("navigate", () => this._navigate("detail", tool.id));
                row.connect("select", (_row, key) => this._select(tool, key));
                section.add_child(row);
                rows.push(row);
            }
            this._entryRows = rows;
            this._lastSwapped = null;
            screen.add_child(section);
            const picker = this._windowPicker(tools, selectedKind);
            if (picker) screen.add_child(picker);
            const actions = [];
            if (this._state?.latestMessage)
                actions.push({
                    label: tr("ui.latest"),
                    cb: () => {
                        this._landingMode = "latest";
                        this._navigate("landing");
                    },
                });
            actions.push({ label: tr("ui.guide"), cb: () => this._navigate("guide") });
            actions.push({ label: tr("ui.about"), cb: () => this._navigate("about") });
            screen.add_child(this._footer(this._updatedText(), actions, true));
        }

        _renderDetail(screen) {
            const tool = this.tools.find((t) => t.id === this._toolId);
            if (!tool) {
                this._screen = "list";
                this._renderList(screen);
                return;
            }
            const { title, sub } = this._meterSentence(tool);
            screen.add_child(
                this._screenHeader({
                    kicker: tool.name,
                    meta: tool.plan ?? "",
                    title,
                    sub,
                    back: () => this._navigate("list"),
                }),
            );

            const via = viaOf(tool);
            const muted = !!via?.borrowed;
            const bars = [];
            if (hasMeters(tool)) {
                const limits = this._section(
                    via?.borrowed
                        ? tr("detail.limitsShared", { via: via.name })
                        : tr("detail.limits"),
                );
                for (const m of tool.metrics) {
                    const pct = clampPct(m.value);
                    const color = muted ? COLOR.muted : colorFor(pct);
                    const block = new St.BoxLayout({
                        style_class: "tokens-go-brrr-limit-row",
                        orientation: Clutter.Orientation.VERTICAL,
                        x_expand: true,
                    });
                    const top = new St.BoxLayout({
                        style_class: "tokens-go-brrr-name-row",
                        x_expand: true,
                    });
                    top.add_child(
                        label(metricLabel(m.label), "tokens-go-brrr-name", {
                            y_align: Clutter.ActorAlign.CENTER,
                        }),
                    );
                    if (m === this._tightestMetric(tool) && tool.metrics.length > 1)
                        top.add_child(
                            label(tr("ui.tightest").toUpperCase(), "tokens-go-brrr-tag", {
                                y_align: Clutter.ActorAlign.CENTER,
                            }),
                        );
                    top.add_child(new St.Widget({ x_expand: true }));
                    top.add_child(
                        label(`${Math.round(pct)}%`, "tokens-go-brrr-value", {
                            style: `color: ${statusTextColor(pct, muted)};`,
                            y_align: Clutter.ActorAlign.CENTER,
                        }),
                    );
                    block.add_child(top);
                    const bar = new Bar(pct, color, m.elapsed);
                    bars.push(bar);
                    block.add_child(bar);
                    const text = meterSub(m);
                    if (text) {
                        const crit = pct >= CRITICAL_AT && !muted;
                        block.add_child(
                            wrappedLabel(text, crit ? "tokens-go-brrr-sub crit" : "tokens-go-brrr-sub", {
                                style: crit ? `color: ${color};` : "",
                            }),
                        );
                    }
                    limits.add_child(block);
                }
                screen.add_child(limits);
            } else if (via) {
                const note = new St.BoxLayout({
                    style_class: "tokens-go-brrr-limit-row",
                    x_expand: true,
                });
                note.add_child(
                    wrappedLabel(
                        `${via.name}${via.model ? ` · ${via.model}` : ""} — ${errorText(tool.error) || tr("tool.noLimitsAvailable")}`,
                        "tokens-go-brrr-sub",
                    ),
                );
                screen.add_child(note);
            }
            this._entryBars = bars;

            const sessions = sessionRows(tool);
            if (sessions.length) {
                const active = sessions.filter((s) => !s.paused);
                const block = this._section(
                    tr("sessions.running", { n: active.length }),
                );
                for (const session of active)
                    block.add_child(this._sessionRow(session));
                block.add_child(
                    this._listRow(
                        tr("sessions.kicker"),
                        tr("sessions.viewAll"),
                        sessionCounts(active.length, sessions.length - active.length),
                        () => this._navigate("sessions", tool.id),
                    ),
                );
                screen.add_child(block);
            }
            screen.add_child(
                this._footer(
                    this._footerNote ?? this._updatedText(),
                    [
                        {
                            label: tr("ui.openDashboard"),
                            cb: () =>
                                this._openUri(
                                    tool.dashboardUrl ||
                                        "https://cursor.com/dashboard",
                                ),
                        },
                    ],
                    false,
                ),
            );
        }

        _renderSessions(screen) {
            const tool = this.tools.find((t) => t.id === this._toolId);
            if (!tool) {
                this._screen = "list";
                this._renderList(screen);
                return;
            }
            const sessions = sessionRows(tool);
            const active = sessions.filter((s) => !s.paused);
            const paused = sessions.filter((s) => s.paused);
            screen.add_child(
                this._screenHeader({
                    kicker: tool.name,
                    meta: tr("sessions.kicker"),
                    title: tr("sessions.title", { name: tool.name, n: active.length }),
                    sub: `${sessionCounts(active.length, paused.length)} · ${tr("sessions.nTotal", { n: sessions.length })}`,
                    back: () => this._navigate("detail", tool.id),
                }),
            );

            // ExtFilterChips: square chips with counts.
            const filters = new St.BoxLayout({
                style_class: "tokens-go-brrr-sessions-filters",
                x_expand: true,
            });
            for (const [key, text] of [
                ["active", tr("sessions.active")],
                ["paused", tr("sessions.paused")],
            ]) {
                const selected = this._sessionsFilter === key;
                const count = key === "active" ? active.length : paused.length;
                const btn = new St.Button({
                    style_class: selected
                        ? "tokens-go-brrr-filter-chip active"
                        : "tokens-go-brrr-filter-chip",
                    label: `${text} ${count}`,
                    can_focus: true,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                btn.connect("clicked", () => {
                    if (this._sessionsFilter === key) return;
                    this._sessionsFilter = key;
                    this._render(false);
                });
                filters.add_child(btn);
            }
            screen.add_child(filters);

            const list = this._section();
            const shown = this._sessionsFilter === "paused" ? paused : active;
            if (shown.length) {
                for (const session of shown)
                    list.add_child(this._sessionRow(session));
            } else {
                list.add_child(
                    label(
                        this._sessionsFilter === "paused"
                            ? tr("sessions.noPaused")
                            : tr("sessions.noActive"),
                        "tokens-go-brrr-sessions-empty",
                    ),
                );
            }
            screen.add_child(list);
            screen.add_child(
                this._footer(this._footerNote ?? this._updatedText(), [], false),
            );
        }

        _renderGuide(screen) {
            screen.add_child(
                this._screenHeader({
                    kicker: tr("ui.guide"),
                    title: tr("guide.title"),
                    sub: tr("guide.sub"),
                    back: () => this._navigate("list"),
                }),
            );
            const status = this._section(tr("guide.status"));
            status.add_child(
                this._guideItem(COLOR.ok, tr("guide.ok.t"), tr("guide.ok.d")),
            );
            status.add_child(
                this._guideItem(COLOR.wait, tr("guide.warn.t"), tr("guide.warn.d")),
            );
            status.add_child(
                this._guideItem(COLOR.crit, tr("guide.crit.t"), tr("guide.crit.d")),
            );
            screen.add_child(status);
            const meter = this._section(tr("guide.meter"));
            meter.add_child(
                this._guideItem(null, tr("guide.pace.t"), tr("guide.pace.d"), "pace"),
            );
            screen.add_child(meter);
            screen.add_child(this._footer(this._updatedText(), [], false));
        }

        _renderAbout(screen) {
            screen.add_child(
                this._screenHeader({
                    kicker: tr("ui.about"),
                    title: tr("brand"),
                    sub: tr("about.sub"),
                    back: () => this._navigate("list"),
                }),
            );
            const daemon = this._state
                ? tr("about.daemon", {
                      v: this._state.version ?? "?",
                      ago: relativeTime(this._state.updated_at),
                  })
                : tr("about.daemonDown");
            const section = this._section();
            section.add_child(
                this._guideItem(
                    null,
                    tr("about.ext", { v: this._ext.metadata.version }),
                    this._state?.error ? `${daemon}\n${this._state.error}` : daemon,
                ),
            );
            screen.add_child(section);
            screen.add_child(
                this._listRow(tr("llm.kicker"), tr("llm.title"), tr("llm.sub"), () =>
                    this._openLlmLog(),
                ),
            );
            const refresh = new St.Button({
                style_class: "tokens-go-brrr-secondary-btn tokens-go-brrr-about-refresh",
                label: tr("ui.refresh"),
                can_focus: true,
                x_expand: true,
            });
            refresh.connect("clicked", () => this._ext.refresh());
            screen.add_child(refresh);
        }

        // -- the LLM activity log ----------------------------------------------

        _openLlmLog() {
            this._llmLog = null;
            this._llmOpen = new Set();
            this._loadLlmLog("");
            this._navigate("llmlog");
        }

        _loadLlmLog(day) {
            this._ext.fetchLlmLog(day, (data) => {
                this._llmLog = data ?? { unavailable: true };
                this._llmOpen = new Set();
                if (this._screen === "llmlog" && this.menu.isOpen)
                    this._render(false);
            });
        }

        _renderLlmLog(screen) {
            const data = this._llmLog;
            screen.add_child(
                this._screenHeader({
                    kicker: tr("llm.kicker"),
                    title: tr("llm.title"),
                    sub: tr("llm.sub"),
                    back: () => this._navigate("about"),
                }),
            );
            const note = (text) => {
                const box = this._section();
                box.add_child(label(text, "tokens-go-brrr-sessions-empty"));
                screen.add_child(box);
            };
            if (!data) {
                note(tr("llm.loading"));
                return;
            }
            if (data.unavailable) {
                note(tr("llm.unavailable"));
                return;
            }
            if (!data.enabled) {
                note(tr("llm.off"));
                return;
            }
            if (!data.days?.length) {
                note(tr("llm.emptyAll"));
                screen.add_child(this._llmFooter(data));
                return;
            }

            // Newest day first in `days`, so "earlier" is the next index.
            const at = data.days.indexOf(data.day);
            const earlier = data.days[at + 1];
            const later = at > 0 ? data.days[at - 1] : undefined;
            const nav = new St.BoxLayout({
                style_class: "tokens-go-brrr-sessions-filters",
                x_expand: true,
            });
            const step = (text, day) => {
                const btn = new St.Button({
                    style_class: "tokens-go-brrr-filter-chip",
                    label: text,
                    can_focus: day !== undefined,
                    reactive: day !== undefined,
                    opacity: day !== undefined ? 255 : 90,
                    accessible_name: text,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                if (day !== undefined)
                    btn.connect("clicked", () => this._loadLlmLog(day));
                return btn;
            };
            nav.add_child(step("‹", earlier));
            nav.add_child(
                label(data.day, "tokens-go-brrr-kicker", {
                    x_expand: true,
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            );
            nav.add_child(step("›", later));
            screen.add_child(nav);

            const summary = data.summary ?? {};
            screen.add_child(
                wrappedLabel(
                    tr("llm.summary", {
                        calls: summary.calls ?? 0,
                        failed: summary.failures ?? 0,
                        tin: formatTokens(summary.tokens_in ?? 0),
                        tout: formatTokens(summary.tokens_out ?? 0),
                    }),
                    "tokens-go-brrr-hdr-sub",
                ),
            );

            const list = this._section();
            const entries = [...(data.entries ?? [])].reverse();
            if (!entries.length) {
                list.add_child(label(tr("llm.empty"), "tokens-go-brrr-sessions-empty"));
            }
            entries.forEach((entry, i) => list.add_child(this._llmRow(entry, i)));
            screen.add_child(list);
            screen.add_child(this._llmFooter(data));
        }

        _llmRow(entry, index) {
            const open = this._llmOpen.has(index);
            const outcome = String(entry.outcome ?? "");
            const time = String(entry.ts ?? "").slice(11, 19);
            const who = [entry.provider, entry.model].filter(Boolean).join(" · ");
            const bits = [tr(`llm.outcome.${outcome}`)];
            if (outcome === "skipped" && entry.reason)
                bits.push(tr("llm.skipped", { reason: entry.reason }));
            if (entry.latency_ms !== undefined)
                bits.push(`${entry.latency_ms} ms`);
            if (entry.tokens_in !== undefined || entry.tokens_out !== undefined)
                bits.push(
                    `${formatTokens(entry.tokens_in ?? 0)} → ${formatTokens(entry.tokens_out ?? 0)}`,
                );

            const row = new St.Button({
                style_class: "tokens-go-brrr-list-row",
                can_focus: true,
                x_expand: true,
            });
            const box = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            box.add_child(
                label(
                    [time, entry.trigger].filter(Boolean).join(" · ").toUpperCase(),
                    "tokens-go-brrr-kicker",
                ),
            );
            box.add_child(wrappedLabel(who || "—", "tokens-go-brrr-list-title"));
            box.add_child(wrappedLabel(bits.join(" · "), "tokens-go-brrr-sub"));
            if (open) {
                const detail = (title, text) => {
                    if (!text) return;
                    box.add_child(
                        label(title.toUpperCase(), "tokens-go-brrr-section-label"),
                    );
                    box.add_child(wrappedLabel(String(text), "tokens-go-brrr-guide-desc"));
                };
                detail(tr("llm.prompt"), entry.prompt);
                detail(tr("llm.reply"), entry.reply);
                detail(tr("llm.error"), entry.error);
            }
            row.set_child(box);
            row.connect("clicked", () => {
                if (this._llmOpen.has(index)) this._llmOpen.delete(index);
                else this._llmOpen.add(index);
                this._render(false);
            });
            return row;
        }

        _llmFooter(data) {
            return this._footer(
                tr("llm.where", { dir: data.directory ?? "" }),
                [
                    {
                        label: tr("llm.clear"),
                        cb: () =>
                            this._ext.clearLlmLog(() => this._loadLlmLog("")),
                    },
                ],
                false,
            );
        }

        // -- the landing page and the insights behind it -----------------------

        _landingBillboard() {
            // Fresh for the routing case, the newest stored one for Latest, and
            // the one picked from the list for Earlier.
            if (this._landingMode === "message") return this._pickedMessage ?? null;
            return this._landingMode === "latest"
                ? (this._state?.latestMessage ?? null)
                : (this._state?.billboard ?? null);
        }

        _renderLanding(screen) {
            const billboard = this._landingBillboard();
            if (!billboard) {
                this._screen = "list";
                this._renderList(screen);
                return;
            }
            const { title, sub } = splitInsight(messageText(billboard));
            const fromEarlier = this._landingMode === "message";
            screen.add_child(
                this._screenHeader({
                    kicker: tr("insight.kicker", { kind: kindCopy(billboard.kind) }),
                    meta: insightWhen(billboard.createdAt),
                    title,
                    sub,
                    back: fromEarlier ? () => this._navigate("earlier") : null,
                }),
            );

            const featured = billboard.featured;
            if (featured?.name || featured?.providerId) {
                const row = new St.BoxLayout({
                    style_class: "tokens-go-brrr-landing-featured",
                    x_expand: true,
                });
                row.add_child(
                    new St.Icon({
                        style_class: "tokens-go-brrr-landing-icon",
                        gicon: this._icons.badge(featured.providerId ?? "cursor"),
                        icon_size: 16,
                        y_align: Clutter.ActorAlign.CENTER,
                    }),
                );
                const role = roleCopy(featured.role);
                row.add_child(
                    label(
                        `${featured.name ?? featured.providerId ?? ""}${role ? ` · ${role}` : ""}`,
                        "tokens-go-brrr-sub",
                        { y_align: Clutter.ActorAlign.CENTER },
                    ),
                );
                screen.add_child(row);
            }

            const actions = new St.BoxLayout({
                style_class: "tokens-go-brrr-landing-actions",
                x_expand: true,
            });
            const cont = new St.Button({
                style_class: "tokens-go-brrr-primary-btn",
                label: tr("ui.continue"),
                can_focus: true,
                x_expand: true,
            });
            cont.connect("clicked", () => this._leaveLanding());
            actions.add_child(cont);
            if ((this._state?.recentMessages ?? []).length > 1) {
                const earlier = new St.Button({
                    style_class: "tokens-go-brrr-secondary-btn",
                    label: tr("ui.earlier"),
                    can_focus: true,
                });
                earlier.connect("clicked", () => this._navigate("earlier"));
                actions.add_child(earlier);
            }
            if (billboard.share) {
                const copy = new St.Button({
                    style_class: "tokens-go-brrr-ghost-btn",
                    label: tr("ui.copy"),
                    can_focus: true,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                copy.connect("clicked", () =>
                    St.Clipboard.get_default().set_text(
                        St.ClipboardType.CLIPBOARD,
                        shareText(billboard),
                    ),
                );
                actions.add_child(copy);
            }
            screen.add_child(actions);
        }

        _renderEarlier(screen) {
            const messages = this._state?.recentMessages ?? [];
            screen.add_child(
                this._screenHeader({
                    kicker: tr("earlier.kicker"),
                    meta: tr("earlier.meta", { n: messages.length }),
                    title: tr("earlier.title"),
                    sub: tr("earlier.sub"),
                    back: () => this._navigate("list"),
                }),
            );
            const section = this._section();
            if (!messages.length)
                section.add_child(label(tr("earlier.empty"), "tokens-go-brrr-sessions-empty"));
            for (const m of messages) {
                section.add_child(
                    this._listRow(
                        `${kindCopy(m.kind)} · ${insightWhen(m.createdAt)}`,
                        splitInsight(messageText(m)).title,
                        "",
                        () => {
                            this._pickedMessage = m;
                            this._landingMode = "message";
                            this._navigate("landing");
                        },
                    ),
                );
            }
            screen.add_child(section);
            screen.add_child(this._footer(this._updatedText(), [], false));
        }

        _windowPicker(tools, selectedKind) {
            // One control for every row, because the windows are the same
            // question asked of each provider. Nothing to pick between when
            // only one window is on offer across all of them.
            const offered = windowsOffered(tools);
            if (offered.length < 2) return null;

            const bar = new St.BoxLayout({
                style_class: "tokens-go-brrr-windowbar",
                x_expand: true,
            });
            for (const { kind, key } of offered) {
                const text = tr(key);
                const active = kind === selectedKind;
                const button = new St.Button({
                    style_class: active
                        ? "tokens-go-brrr-window-btn selected"
                        : "tokens-go-brrr-window-btn",
                    label: text,
                    can_focus: true,
                    x_expand: true,
                });
                if (!active)
                    button.connect("clicked", () => this._selectWindow(kind));
                bar.add_child(button);
            }
            return bar;
        }

        _selectWindow(kind) {
            // A bulk chip swap. Routing it through the same SetPrimary the row
            // chips used means the choice persists in the daemon's config, and
            // the top bar, the alerts and the status dot follow it for free —
            // they all read the primary already. A provider with no meter of
            // this kind is left alone rather than switched to something it did
            // not offer.
            for (const tool of this.tools) {
                if (!hasMeters(tool) || !ownsMeters(tool)) continue;
                const match = (tool.metrics ?? []).find(
                    (m) => kindOfMetric(m) === kind,
                );
                if (!match || match.key === tool.primary) continue;
                this._ext.setPrimary(tool.id, match.key);
            }
        }

        _leaveLanding() {
            const billboard = this._landingBillboard();
            // Leave first. Getting out of this screen must not depend on a
            // D-Bus call succeeding: when the proxy's interface XML had no
            // Acknowledge, the missing method threw and stranded the user here.
            this._navigate("list");
            if (billboard?.id === undefined || billboard?.id === null) return;
            // Pressing Continue is the user saying they have seen it, so the
            // daemon records that and never offers this one again. The same
            // applies to reading it back through Latest.
            this._ext.acknowledge(billboard.id);
        }

        _select(tool, key) {
            if (!key || key === tool.primary) return;
            if (!(tool.metrics ?? []).some((m) => m.key === key)) return;
            tool.primary = key;
            this._lastSwapped = tool.id;
            this._ext.setPrimary(tool.id, key);
            this._updateDot();
            this._render(false);
        }

        _openUri(uri) {
            this.menu.close();
            try {
                Gio.AppInfo.launch_default_for_uri(
                    uri,
                    global.create_app_launch_context(0, -1),
                );
            } catch (e) {
                console.error(`[tokens-go-brrr] failed to open ${uri}: ${e.message}`);
            }
        }

        _openSettings() {
            const file = Gio.File.new_for_path(CONFIG_PATH);
            const target = file.query_exists(null) ? file : file.get_parent();
            this._openUri(target.get_uri());
        }
    },
);

export default class TokensGoBrrrExtension extends Extension {
    enable() {
        this.icons = {
            badge: (name) => this._badgeIcon(name),
            chevronRight: this._icon("chevron-right-symbolic"),
            chevronLeft: this._icon("chevron-left-symbolic"),
        };
        this._indicator = new Indicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator, 0, "right");

        this._cancellable = new Gio.Cancellable();
        this._proxy = null;
        this._stateSignalId = 0;
        this._ownerSignalId = 0;
        new UsageProxy(
            Gio.DBus.session,
            BUS_NAME,
            OBJECT_PATH,
            (proxy, error) => {
                if (error) {
                    if (!this._cancellable?.is_cancelled())
                        console.error(
                            `[tokens-go-brrr] D-Bus proxy failed: ${error.message}`,
                        );
                    return;
                }
                if (!this._indicator) return;
                this._proxy = proxy;
                this._stateSignalId = proxy.connectSignal(
                    "StateChanged",
                    (_p, _sender, [json]) => {
                        this._applyJson(json);
                    },
                );
                this._ownerSignalId = proxy.connect(
                    "notify::g-name-owner",
                    () => this._fetchState(),
                );
                this._fetchState();
            },
            this._cancellable,
            Gio.DBusProxyFlags.DO_NOT_AUTO_START,
        );
    }

    disable() {
        this._cancellable?.cancel();
        this._cancellable = null;
        if (this._proxy) {
            if (this._stateSignalId)
                this._proxy.disconnectSignal(this._stateSignalId);
            if (this._ownerSignalId)
                this._proxy.disconnect(this._ownerSignalId);
        }
        this._proxy = null;
        this._stateSignalId = 0;
        this._ownerSignalId = 0;
        this._indicator?.destroy();
        this._indicator = null;
        this.icons = null;
    }

    _icon(name) {
        return Gio.icon_new_for_string(`${this.path}/icons/${name}.svg`);
    }

    // Brand marks, taken from the apps themselves, so they keep their own colours.
    _badgeIcon(name) {
        const file = BADGE_FILES[name] ?? BADGE_FILES.cursor;
        return Gio.icon_new_for_string(`${this.path}/icons/${file}`);
    }

    _applyJson(json) {
        try {
            this._indicator?.setState(JSON.parse(json));
        } catch (e) {
            console.error(`[tokens-go-brrr] bad state payload: ${e.message}`);
        }
    }

    _fetchState() {
        if (!this._proxy || !this._indicator) return;
        if (!this._proxy.g_name_owner) {
            this._indicator.setState(null);
            return;
        }
        this._proxy.GetStateRemote((result, error) => {
            if (error) {
                if (!this._cancellable?.is_cancelled())
                    console.error(
                        `[tokens-go-brrr] GetState failed: ${error.message}`,
                    );
                return;
            }
            this._applyJson(result[0]);
        });
    }

    refresh() {
        if (this._proxy?.g_name_owner) this._proxy.RefreshRemote(() => {});
    }

    setPrimary(providerId, metricKey) {
        if (this._proxy?.g_name_owner)
            this._proxy.SetPrimaryRemote(providerId, metricKey, () => {});
    }

    // The LLM log is read through the daemon, never from its files. Defensive
    // for the same reason as acknowledge(): an older daemon has no such method,
    // and the screen should say so instead of breaking.
    fetchLlmLog(day, callback) {
        if (
            !this._proxy?.g_name_owner ||
            typeof this._proxy.LlmLogRemote !== "function"
        ) {
            callback(null);
            return;
        }
        try {
            this._proxy.LlmLogRemote(day, (result, error) => {
                if (error) {
                    callback(null);
                    return;
                }
                try {
                    callback(JSON.parse(result[0]));
                } catch (e) {
                    console.error(`[tokens-go-brrr] bad LLM log payload: ${e.message}`);
                    callback(null);
                }
            });
        } catch (e) {
            console.error(`[tokens-go-brrr] LLM log failed: ${e.message}`);
            callback(null);
        }
    }

    clearLlmLog(callback) {
        if (
            !this._proxy?.g_name_owner ||
            typeof this._proxy.ClearLlmLogRemote !== "function"
        ) {
            callback();
            return;
        }
        try {
            this._proxy.ClearLlmLogRemote(() => callback());
        } catch (e) {
            console.error(`[tokens-go-brrr] clearing the LLM log failed: ${e.message}`);
            callback();
        }
    }

    acknowledge(messageId) {
        // Durable by design: the daemon stores this, so a dismissal survives a
        // reload or a logout and the message cannot come back. Defensive on
        // purpose: the proxy only exposes AcknowledgeRemote if this file's
        // interface XML declares it, and a method that is missing or refused
        // must never break the caller.
        if (!this._proxy?.g_name_owner) return;
        if (typeof this._proxy.AcknowledgeRemote !== "function") return;
        try {
            this._proxy.AcknowledgeRemote(messageId, () => {});
        } catch (e) {
            console.error(`[tokens-go-brrr] acknowledge failed: ${e.message}`);
        }
    }
}
