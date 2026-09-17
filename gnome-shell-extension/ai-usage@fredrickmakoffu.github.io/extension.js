// AI Usage — GNOME Shell indicator matching design/menu-bar-concept.html.
// Data comes from the cursor-spend-monitor daemon over D-Bus.

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

const BUS_NAME = "io.github.fredrickmakoffu.AIUsage";
const OBJECT_PATH = "/io/github/fredrickmakoffu/AIUsage";
const IFACE_XML = `
<node>
  <interface name="io.github.fredrickmakoffu.AIUsage">
    <property name="Version" type="s" access="read"/>
    <method name="GetState"><arg type="s" direction="out" name="json"/></method>
    <method name="Refresh"/>
    <method name="SetPrimary">
      <arg type="s" direction="in" name="provider"/>
      <arg type="s" direction="in" name="metric"/>
    </method>
    <method name="Quit"/>
    <signal name="StateChanged"><arg type="s" name="json"/></signal>
  </interface>
</node>`;
const UsageProxy = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);

const COLOR = {
    ok: "#7fd68f",
    wait: "#e0b158",
    crit: "#e2726b",
    error: "#6c6d70",
};
const BADGE_FILES = {
    cursor: "cursor.png",
    claude: "claude.svg",
    codex: "codex.svg",
    opencode: "opencode.svg",
    pi: "pi.svg",
};
const CONFIG_PATH = GLib.build_filenamev([
    GLib.get_user_config_dir(),
    "cursor-spend-monitor",
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
    if (session?.kind === "editor") return "Desktop";
    return "Session";
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
    { kind: "rolling", label: "Rolling" },
    { kind: "weekly", label: "Weekly" },
    { kind: "monthly", label: "Monthly" },
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
    if (text.includes("hour") || text.includes("rolling") || text.includes("daily"))
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
    if (!iso) return "never";
    const then = GLib.DateTime.new_from_iso8601(iso, null);
    if (!then) return "unknown";
    const secs = Math.max(
        0,
        Math.round(GLib.DateTime.new_now_utc().difference(then) / 1e6),
    );
    if (secs < 60) return "just now";
    if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
    if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
    return `${Math.round(secs / 86400)}d ago`;
}

function label(text, styleClass, extra = {}) {
    return new St.Label({ text, style_class: styleClass, ...extra });
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
    class AiUsageBar extends St.Widget {
        _init(pct, color) {
            super._init({ style_class: "ai-usage-bar", x_expand: true });
            this._fill = new St.Widget({ style_class: "ai-usage-bar-fill" });
            this.add_child(this._fill);
            this.setValue(pct, color);
            // Collapsed from birth rather than at the start of the animation.
            // The entry runs one turn of the loop after the screen is built, and
            // anything visible in that gap flashes at full value first.
            if (St.Settings.get().enable_animations) {
                this._fill.set_pivot_point(0, 0.5);
                this._fill.scale_x = 0;
            }
        }

        setValue(pct, color) {
            this._pct = clampPct(pct);
            this._fill.style = `background-color: ${color};`;
            this.queue_relayout();
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
        }
    },
);

const BADGE_COLUMN_SPACING = 7;
const BADGE_ROW_SPACING = 4;

// Badges wrap onto further lines rather than overflowing the row. A provider can
// report more windows than fit across 360px (Claude adds Opus and Sonnet buckets),
// and Clutter's own FlowLayout stacks them at the same x instead of wrapping.
const BadgeFlow = GObject.registerClass(
    class AiUsageBadgeFlow extends St.Widget {
        _init() {
            super._init({ style_class: "ai-usage-meta", x_expand: true });
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
    class AiUsageRow extends PopupMenu.PopupBaseMenuItem {
        _init(icons, tool, bump, selectedKind = null) {
            const ok = !tool.status || tool.status === "ok";
            super._init({
                style_class: "ai-usage-row",
                reactive: ok,
                activate: ok,
                hover: ok,
                can_focus: ok,
            });
            if (!ok) this.add_style_class_name("ai-usage-row-disabled");

            const primary = primaryOf(tool);
            const pct = clampPct(primary?.value ?? 0);
            const color = colorFor(pct);
            const via = viaOf(tool);
            // A harness with no reachable limit is fine, not broken: it keeps its
            // row and its session count, and simply shows no bar and no number.
            const metered = ok && hasMeters(tool);

            const badge = new St.Bin({
                style_class: via
                    ? "ai-usage-badge ai-usage-badge-via"
                    : "ai-usage-badge",
                y_align: Clutter.ActorAlign.CENTER,
                child: new St.Icon({
                    style_class: "ai-usage-badge-icon",
                    gicon: icons.badge(tool.icon),
                    icon_size: 15,
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            });
            this.add_child(badge);

            const info = new St.BoxLayout({
                style_class: "ai-usage-info",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
                y_align: Clutter.ActorAlign.CENTER,
            });
            const nameRow = new St.BoxLayout({
                style_class: "ai-usage-name-row",
                x_expand: true,
            });
            nameRow.add_child(label(tool.name, "ai-usage-name"));
            if (via) {
                nameRow.add_child(
                    label(`via ${via.name}`, "ai-usage-via", {
                        y_align: Clutter.ActorAlign.CENTER,
                    }),
                );
            }
            const running = ok ? activeSessions(tool) : 0;
            if (running) {
                nameRow.add_child(
                    label(`${running} running`, "ai-usage-running", {
                        y_align: Clutter.ActorAlign.CENTER,
                    }),
                );
            }
            info.add_child(nameRow);

            const meta = new BadgeFlow();
            if (metered) {
                // The picker at the foot of the menu names the window every row
                // is showing, so a row that matches it says nothing — that is
                // the space this layout buys. A row only speaks up when it
                // cannot honour the choice: Cursor publishes no weekly and
                // Claude no monthly, so somebody is always the exception, and
                // an exception that stayed silent would read as though the
                // picker applied to it.
                const honoured = !selectedKind || kindOf(tool) === selectedKind;
                if (!honoured)
                    meta.add_child(
                        label(shortLabel(primary?.label), "ai-usage-limit", {
                            y_align: Clutter.ActorAlign.CENTER,
                        }),
                    );
            } else {
                meta.add_child(
                    label(
                        tool.error || tool.status || "No limits",
                        "ai-usage-limit",
                    ),
                );
            }
            info.add_child(meta);

            if (metered) {
                this._bar = new Bar(pct, color);
                info.add_child(this._bar);
            }
            this.add_child(info);

            if (ok) {
                // Only a metered row has a number to show; an unmetered one still
                // opens, because its detail screen lists the sessions.
                if (metered) {
                    this._value = label(
                        `${Math.round(pct)}%`,
                        "ai-usage-value",
                        {
                            style: `color: ${color};`,
                            y_align: Clutter.ActorAlign.CENTER,
                        },
                    );
                    this.add_child(this._value);
                }
                this.add_child(
                    new St.Icon({
                        style_class: "ai-usage-chevron",
                        gicon: icons.chevronRight,
                        icon_size: 14,
                        y_align: Clutter.ActorAlign.CENTER,
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
            if (on) this.add_style_class_name("ai-usage-keyboard-focus");
            else this.remove_style_class_name("ai-usage-keyboard-focus");
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

        activate(event) {
            // Clicks on a badge belong to the badge (mockup: e.stopPropagation()).
            this.emit("navigate");
        }

        prepareEntry() {
            if (!St.Settings.get().enable_animations) return;
            this.opacity = 0;
            this.translation_y = 6;
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

const Indicator = GObject.registerClass(
    class AiUsageIndicator extends PanelMenu.Button {
        _init(ext) {
            super._init(0.5, "AI usage", false);
            this.add_style_class_name("ai-usage-panel-button");
            this._ext = ext;
            this._icons = ext.icons;
            this._state = null; // parsed daemon state, or null when the daemon is away
            this._screen = "list";
            this._toolId = null;
            this._sessionsFilter = "active"; // 'active' | 'paused' on the sessions screen
            this._lastSwapped = null;
            this._firstRender = true;
            this._probedMatch = null; // {toolId, project, title} from async pid probe
            this._probeTimeoutId = 0;
            this._probeSerial = 0;

            this._dot = new St.Widget({
                style_class: "ai-usage-dot",
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });
            // Sessions appear beside the dot only while something is running, so the
            // panel stays a bare dot when it has nothing to say.
            this._sessions = new St.BoxLayout({
                style_class: "ai-usage-sessions",
                y_align: Clutter.ActorAlign.CENTER,
            });
            // The dot keeps the mockup's bare look, so the usual full-height panel pill
            // is suppressed. This pill carries hover, press and focus instead, and it
            // wraps the session chips too: they are part of the same button, so the
            // whole indicator has to light up as one target.
            this._halo = new St.BoxLayout({
                style_class: "ai-usage-dot-halo",
                y_align: Clutter.ActorAlign.CENTER,
                accessible_name: "AI usage",
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

            this.menu.actor.add_style_class_name("ai-usage-menu");
            this.menu.connect("open-state-changed", (_menu, open) => {
                if (open) {
                    this._ext.refresh();
                    if (this._screen !== "list") this._navigate("list");
                    else this._queueEntry();
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
                    style_class: "ai-usage-session",
                    y_align: Clutter.ActorAlign.CENTER,
                });
                chip.add_child(this._sessionBadge(tool));

                const project = this._focusedTerminalProject(tool);
                if (project) {
                    chip.add_child(
                        label(
                            truncateProject(project),
                            "ai-usage-session-project",
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
                        label(`${Math.round(pct)}%`, "ai-usage-session-pct", {
                            style: `color: ${colorFor(pct)};`,
                            y_align: Clutter.ActorAlign.CENTER,
                        }),
                    );
                }
                chip.add_child(
                    label(`\u00d7${running}`, "ai-usage-session-count", {
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
                    style_class: "ai-usage-session-icon",
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
                style_class: "ai-usage-session-stack",
                y_align: Clutter.ActorAlign.CENTER,
            });
            stack.add_child(icon());
            stack.add_child(
                new St.Icon({
                    style_class: "ai-usage-session-via",
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
                style_class: "ai-usage-screen",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            if (this._screen === "detail") this._renderDetail(screen);
            else if (this._screen === "sessions") this._renderSessions(screen);
            else if (this._screen === "guide") this._renderGuide(screen);
            else if (this._screen === "about") this._renderAbout(screen);
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
                this._queueEntry();
            }
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
            if (!this.menu.isOpen) return;
            (this._entryRows ?? []).forEach((row, index) => row.enter(index));
            for (const bar of this._entryBars ?? []) bar.grow();
        }

        _header(title, withSettings = false) {
            const header = new St.BoxLayout({
                style_class: "ai-usage-header",
                x_expand: true,
            });
            header.add_child(
                label(title, "ai-usage-header-title", {
                    x_expand: true,
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            );
            // Settings, Guide and About used to own the foot of the menu, which
            // is the most reachable row there is and was being spent on three
            // things you press once. They move up here into space the title was
            // not using, and the window picker takes the row instead.
            const add = (text, cb) => {
                const b = new St.Button({
                    style_class: "ai-usage-header-btn",
                    label: text,
                    can_focus: true,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                b.connect("clicked", cb);
                header.add_child(b);
            };
            if (withSettings) add("Settings", () => this._openSettings());
            add("Guide", () => this._navigate("guide"));
            add("About", () => this._navigate("about"));
            return header;
        }

        _detailHeader(title, icon, backScreen = "list") {
            const header = new St.BoxLayout({
                style_class: "ai-usage-detail-header",
                x_expand: true,
            });
            const back = new St.Button({
                style_class: "ai-usage-back",
                can_focus: true,
                accessible_name: "Back",
                y_align: Clutter.ActorAlign.CENTER,
                child: new St.Icon({
                    style_class: "ai-usage-back-icon",
                    gicon: this._icons.chevronLeft,
                    icon_size: 16,
                }),
            });
            back.connect("clicked", () => {
                if (backScreen === "detail")
                    this._navigate("detail", this._toolId);
                else this._navigate(backScreen);
            });
            header.add_child(back);
            if (icon) {
                header.add_child(
                    new St.Bin({
                        style_class: "ai-usage-badge",
                        y_align: Clutter.ActorAlign.CENTER,
                        child: new St.Icon({
                            style_class: "ai-usage-badge-icon",
                            gicon: this._icons.badge(icon),
                            icon_size: 15,
                            x_align: Clutter.ActorAlign.CENTER,
                            y_align: Clutter.ActorAlign.CENTER,
                        }),
                    }),
                );
            }
            header.add_child(
                label(title, "ai-usage-detail-title", {
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            );
            return header;
        }

        _sessionRow(session) {
            const row = new St.BoxLayout({
                style_class: "ai-usage-session-row",
                x_expand: true,
            });
            row.add_child(
                new St.Widget({
                    style_class: session.paused
                        ? "ai-usage-session-mark paused"
                        : "ai-usage-session-mark",
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            );
            row.add_child(
                label(sessionLabel(session), "ai-usage-session-name", {
                    x_expand: true,
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            );
            // Sessions of one harness can sit on different accounts at once, so each
            // row names its own rather than inheriting the provider's headline.
            if (session.backend?.model) {
                row.add_child(
                    label(session.backend.model, "ai-usage-session-model", {
                        y_align: Clutter.ActorAlign.CENTER,
                    }),
                );
            }
            row.add_child(
                label(
                    session.paused ? "paused" : "running",
                    session.paused
                        ? "ai-usage-session-state paused"
                        : "ai-usage-session-state",
                    { y_align: Clutter.ActorAlign.CENTER },
                ),
            );
            return row;
        }

        _renderList(screen) {
            screen.add_child(this._header("AI usage", true));
            const tools = this.tools;
            if (!tools.length) {
                const text = this._state
                    ? "No providers yet.\nSign in to Cursor and refresh."
                    : "Daemon not running.\nStart it with:\nsystemctl --user start cursor-spend-monitor";
                screen.add_child(wrappedLabel(text, "ai-usage-empty"));
                return;
            }
            const section = new St.BoxLayout({
                style_class: "ai-usage-section",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            const selectedKind = selectedWindow(tools);
            const rows = [];
            for (const tool of tools) {
                const row = new Row(
                    this._icons,
                    tool,
                    this._lastSwapped === tool.id,
                    selectedKind,
                );
                row.connect("navigate", () =>
                    this._navigate("detail", tool.id),
                );
                row.connect("select", (_row, key) => this._select(tool, key));
                row.prepareEntry();
                section.add_child(row);
                rows.push(row);
            }
            this._entryRows = rows;
            this._lastSwapped = null;
            screen.add_child(section);
            const picker = this._windowPicker(tools, selectedKind);
            if (picker) screen.add_child(picker);
        }

        _windowPicker(tools, selectedKind) {
            // One control for every row, because the windows are the same
            // question asked of each provider. Nothing to pick between when
            // only one window is on offer across all of them.
            const offered = windowsOffered(tools);
            if (offered.length < 2) return null;

            const bar = new St.BoxLayout({
                style_class: "ai-usage-windowbar",
                x_expand: true,
            });
            for (const { kind, label: text } of offered) {
                const active = kind === selectedKind;
                const button = new St.Button({
                    style_class: active
                        ? "ai-usage-window-btn selected"
                        : "ai-usage-window-btn",
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

        _renderDetail(screen) {
            const tool = this.tools.find((t) => t.id === this._toolId);
            if (!tool) {
                this._screen = "list";
                this._renderList(screen);
                return;
            }
            screen.add_child(this._detailHeader(tool.name, tool.icon));

            const body = new St.BoxLayout({
                style_class: "ai-usage-detail-body",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            const via = viaOf(tool);
            if (via) {
                // These meters are not this tool's own, so the screen says so before
                // showing them. Without this the numbers look like Pi's own quota.
                const note = via.borrowed
                    ? `Spending against ${via.name}${via.model ? ` · ${via.model}` : ""}`
                    : `${via.name}${via.model ? ` · ${via.model}` : ""} — ${tool.error || "no limits available"}`;
                body.add_child(wrappedLabel(note, "ai-usage-via-note"));
            }
            const bars = [];
            for (const m of tool.metrics ?? []) {
                const pct = clampPct(m.value);
                const color = colorFor(pct);
                const block = new St.BoxLayout({
                    orientation: Clutter.Orientation.VERTICAL,
                    x_expand: true,
                });
                const top = new St.BoxLayout({
                    style_class: "ai-usage-metric-top",
                    x_expand: true,
                });
                top.add_child(label(m.label, null, { x_expand: true }));
                top.add_child(
                    label(`${Math.round(pct)}%`, "ai-usage-detail-value", {
                        style: `color: ${color};`,
                    }),
                );
                block.add_child(top);
                const bar = new Bar(pct, color);
                bars.push(bar);
                block.add_child(bar);
                block.add_child(label(m.resets ?? "", "ai-usage-detail-reset"));
                body.add_child(block);
            }
            this._entryBars = bars;

            const sessions = sessionRows(tool);
            if (sessions.length) {
                const active = sessions.filter((s) => !s.paused);
                const block = new St.BoxLayout({
                    style_class: "ai-usage-sessions-block",
                    orientation: Clutter.Orientation.VERTICAL,
                    x_expand: true,
                });
                block.add_child(label("Sessions", "ai-usage-sessions-heading"));
                if (active.length) {
                    for (const session of active)
                        block.add_child(this._sessionRow(session));
                } else {
                    block.add_child(
                        label("No active sessions", "ai-usage-sessions-empty"),
                    );
                }

                const viewAll = new St.Button({
                    style_class: "ai-usage-view-all",
                    can_focus: true,
                    x_expand: true,
                    child: (() => {
                        const row = new St.BoxLayout({
                            style_class: "ai-usage-view-all-row",
                            x_expand: true,
                        });
                        row.add_child(
                            label(
                                "View all sessions",
                                "ai-usage-view-all-label",
                                {
                                    x_expand: true,
                                    y_align: Clutter.ActorAlign.CENTER,
                                },
                            ),
                        );
                        row.add_child(
                            new St.Icon({
                                style_class: "ai-usage-chevron",
                                gicon: this._icons.chevronRight,
                                icon_size: 14,
                                y_align: Clutter.ActorAlign.CENTER,
                            }),
                        );
                        return row;
                    })(),
                });
                viewAll.connect("clicked", () =>
                    this._navigate("sessions", tool.id),
                );
                block.add_child(viewAll);
                body.add_child(block);
            }
            screen.add_child(body);

            const dash = new St.Button({
                style_class: "ai-usage-dash-btn",
                label: "Open dashboard",
                can_focus: true,
                x_expand: true,
            });
            dash.connect("clicked", () =>
                this._openUri(
                    tool.dashboardUrl || "https://cursor.com/dashboard",
                ),
            );
            screen.add_child(dash);
        }

        _renderSessions(screen) {
            const tool = this.tools.find((t) => t.id === this._toolId);
            if (!tool) {
                this._screen = "list";
                this._renderList(screen);
                return;
            }
            screen.add_child(
                this._detailHeader("Sessions", tool.icon, "detail"),
            );

            const sessions = sessionRows(tool);
            const active = sessions.filter((s) => !s.paused);
            const paused = sessions.filter((s) => s.paused);
            const body = new St.BoxLayout({
                style_class: "ai-usage-sessions-screen",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });

            body.add_child(
                label(
                    `${active.length} active · ${paused.length} paused · ${sessions.length} total`,
                    "ai-usage-sessions-stats",
                ),
            );

            const filters = new St.BoxLayout({
                style_class: "ai-usage-sessions-filters",
                x_expand: true,
            });
            for (const [key, text] of [
                ["active", "Active"],
                ["paused", "Paused"],
            ]) {
                const selected = this._sessionsFilter === key;
                const count = key === "active" ? active.length : paused.length;
                const btn = new St.Button({
                    style_class: selected
                        ? "ai-usage-filter-chip active"
                        : "ai-usage-filter-chip",
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
            body.add_child(filters);

            const list = new St.BoxLayout({
                style_class: "ai-usage-sessions-list",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            const shown = this._sessionsFilter === "paused" ? paused : active;
            if (shown.length) {
                for (const session of shown)
                    list.add_child(this._sessionRow(session));
            } else {
                list.add_child(
                    label(
                        this._sessionsFilter === "paused"
                            ? "No paused sessions"
                            : "No active sessions",
                        "ai-usage-sessions-empty",
                    ),
                );
            }
            body.add_child(list);
            screen.add_child(body);
        }

        _guideItem(color, title, desc) {
            const item = new St.BoxLayout({
                style_class: "ai-usage-guide-item",
                x_expand: true,
            });
            item.add_child(
                new St.Widget({
                    style_class: "ai-usage-guide-dot",
                    style: `background-color: ${color};`,
                    y_align: Clutter.ActorAlign.START,
                    y_expand: false,
                }),
            );
            const text = new St.BoxLayout({
                style_class: "ai-usage-guide-text",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            text.add_child(label(title, "ai-usage-guide-title"));
            text.add_child(wrappedLabel(desc, "ai-usage-guide-desc"));
            item.add_child(text);
            return item;
        }

        _renderGuide(screen) {
            screen.add_child(this._detailHeader("Status colors", null));
            const body = new St.BoxLayout({
                style_class: "ai-usage-guide-body",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            body.add_child(
                this._guideItem(
                    COLOR.ok,
                    "Healthy",
                    "Plenty of headroom — under 70% used.",
                ),
            );
            body.add_child(
                this._guideItem(
                    COLOR.wait,
                    "Caution",
                    "Getting close — 70 to 89% used.",
                ),
            );
            body.add_child(
                this._guideItem(
                    COLOR.crit,
                    "Critical",
                    "At or near your limit — 90% and up.",
                ),
            );
            screen.add_child(body);
        }

        _renderAbout(screen) {
            screen.add_child(this._detailHeader("About", null));
            const body = new St.BoxLayout({
                style_class: "ai-usage-guide-body",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            const intro = new St.BoxLayout({
                style_class: "ai-usage-guide-text",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            intro.add_child(label("AI usage", "ai-usage-guide-title"));
            intro.add_child(
                wrappedLabel(
                    "Local GNOME Shell indicator for AI coding limits. Cursor is live; OpenCode and Claude Code are next.",
                    "ai-usage-guide-desc",
                ),
            );
            body.add_child(intro);

            const daemon = this._state
                ? `Daemon v${this._state.version ?? "?"} · updated ${relativeTime(this._state.updated_at)}`
                : "Daemon not running";
            const status = new St.BoxLayout({
                style_class: "ai-usage-guide-text",
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
            });
            status.add_child(
                label(
                    `Extension v${this._ext.metadata.version}`,
                    "ai-usage-guide-title",
                ),
            );
            status.add_child(
                wrappedLabel(
                    this._state?.error
                        ? `${daemon}\n${this._state.error}`
                        : daemon,
                    "ai-usage-guide-desc",
                ),
            );
            body.add_child(status);
            screen.add_child(body);

            const refresh = new St.Button({
                style_class: "ai-usage-dash-btn ai-usage-refresh-btn",
                label: "Refresh now",
                can_focus: true,
                x_expand: true,
            });
            refresh.connect("clicked", () => this._ext.refresh());
            screen.add_child(refresh);
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
                console.error(`[ai-usage] failed to open ${uri}: ${e.message}`);
            }
        }

        _openSettings() {
            const file = Gio.File.new_for_path(CONFIG_PATH);
            const target = file.query_exists(null) ? file : file.get_parent();
            this._openUri(target.get_uri());
        }
    },
);

export default class AiUsageExtension extends Extension {
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
                            `[ai-usage] D-Bus proxy failed: ${error.message}`,
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
            console.error(`[ai-usage] bad state payload: ${e.message}`);
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
                        `[ai-usage] GetState failed: ${error.message}`,
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
}
