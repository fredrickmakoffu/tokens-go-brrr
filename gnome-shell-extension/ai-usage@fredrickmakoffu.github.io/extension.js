// AI Usage — GNOME Shell indicator matching design/menu-bar-concept.html.
// Data comes from the cursor-spend-monitor daemon over D-Bus.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'io.github.fredrickmakoffu.AIUsage';
const OBJECT_PATH = '/io/github/fredrickmakoffu/AIUsage';
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

const COLOR = {ok: '#7fd68f', wait: '#e0b158', crit: '#e2726b', error: '#6c6d70'};
const CONFIG_PATH = GLib.build_filenamev([
    GLib.get_user_config_dir(), 'cursor-spend-monitor', 'config.json',
]);
const SCREEN_EASE = 160;

function colorFor(pct) {
    if (pct >= 90)
        return COLOR.crit;
    if (pct >= 70)
        return COLOR.wait;
    return COLOR.ok;
}

function metric(tool, key) {
    return (tool.metrics ?? []).find(m => m.key === key) ?? null;
}

function primaryOf(tool) {
    return metric(tool, tool.primary) ?? tool.metrics?.[0] ?? null;
}

function secondaryOf(tool) {
    return (tool.metrics ?? []).find(m => m.key !== tool.primary) ?? null;
}

function clampPct(value) {
    const n = Number(value);
    if (!Number.isFinite(n))
        return 0;
    return Math.max(0, Math.min(100, n));
}

function relativeTime(iso) {
    if (!iso)
        return 'never';
    const then = GLib.DateTime.new_from_iso8601(iso, null);
    if (!then)
        return 'unknown';
    const secs = Math.max(0, Math.round(GLib.DateTime.new_now_utc().difference(then) / 1e6));
    if (secs < 60)
        return 'just now';
    if (secs < 3600)
        return `${Math.round(secs / 60)}m ago`;
    if (secs < 86400)
        return `${Math.round(secs / 3600)}h ago`;
    return `${Math.round(secs / 86400)}d ago`;
}

function label(text, styleClass, extra = {}) {
    return new St.Label({text, style_class: styleClass, ...extra});
}

function wrappedLabel(text, styleClass, extra = {}) {
    const l = label(text, styleClass, {x_expand: true, ...extra});
    l.clutter_text.line_wrap = true;
    l.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
    l.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return l;
}

// Thin progress bar: .bar / .bar-fill in the mockup.
const Bar = GObject.registerClass(
class AiUsageBar extends St.Widget {
    _init(pct, color) {
        super._init({style_class: 'ai-usage-bar', x_expand: true});
        this._fill = new St.Widget({style_class: 'ai-usage-bar-fill'});
        this.add_child(this._fill);
        this.setValue(pct, color);
    }

    setValue(pct, color) {
        this._pct = clampPct(pct);
        this._fill.style = `background-color: ${color};`;
        this.queue_relayout();
    }

    vfunc_allocate(box) {
        this.set_allocation(box);
        const content = this.get_theme_node().get_content_box(box);
        const width = Math.round((content.x2 - content.x1) * this._pct / 100);
        const childBox = new Clutter.ActorBox({
            x1: content.x1,
            y1: content.y1,
            x2: content.x1 + width,
            y2: content.y2,
        });
        this._fill.allocate(childBox);
    }
});

// Provider row (.row in the mockup). Activation navigates instead of closing the menu.
const Row = GObject.registerClass({
    Signals: {'navigate': {}, 'swap': {}},
}, class AiUsageRow extends PopupMenu.PopupBaseMenuItem {
    _init(icons, tool, bump) {
        const ok = !tool.status || tool.status === 'ok';
        super._init({
            style_class: 'ai-usage-row',
            reactive: ok,
            activate: ok,
            hover: ok,
            can_focus: ok,
        });
        this._chip = null;
        if (!ok)
            this.add_style_class_name('ai-usage-row-disabled');

        const primary = primaryOf(tool);
        const secondary = ok ? secondaryOf(tool) : null;
        const pct = clampPct(primary?.value ?? 0);
        const color = colorFor(pct);

        const badge = new St.Bin({
            style_class: 'ai-usage-badge',
            y_align: Clutter.ActorAlign.CENTER,
            child: new St.Icon({
                style_class: 'ai-usage-badge-icon',
                gicon: icons.badge(tool.icon),
                icon_size: 14,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            }),
        });
        this.add_child(badge);

        const info = new St.BoxLayout({
            style_class: 'ai-usage-info',
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        info.add_child(label(tool.name, 'ai-usage-name'));

        const meta = new St.BoxLayout({style_class: 'ai-usage-meta'});
        if (ok) {
            meta.add_child(label(primary?.label ?? '—', 'ai-usage-limit', {
                y_align: Clutter.ActorAlign.CENTER,
            }));
            if (secondary) {
                this._chip = new St.Button({
                    style_class: 'ai-usage-chip',
                    label: `${secondary.label} ${clampPct(secondary.value)}%`,
                    can_focus: true,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                this._chip.connect('clicked', () => this.emit('swap'));
                meta.add_child(this._chip);
            }
        } else {
            meta.add_child(label(tool.error || tool.status, 'ai-usage-limit'));
        }
        info.add_child(meta);

        if (ok) {
            info.add_child(new Bar(pct, color));
        }
        this.add_child(info);

        if (ok) {
            this._value = label(`${Math.round(pct)}%`, 'ai-usage-value', {
                style: `color: ${color};`,
                y_align: Clutter.ActorAlign.CENTER,
            });
            this.add_child(this._value);
            this.add_child(new St.Icon({
                style_class: 'ai-usage-chevron',
                gicon: icons.chevronRight,
                icon_size: 14,
                y_align: Clutter.ActorAlign.CENTER,
            }));
            if (bump)
                this._bump();
            this.connect('notify::hover', () => this._syncKeyboardFocus());
        } else {
            this.opacity = 140;
        }
    }

    // Mockup shows the accent bar only for :focus-visible, i.e. keyboard focus.
    _syncKeyboardFocus() {
        const focused = global.stage.get_key_focus() === this;
        if (focused && !this.hover)
            this.add_style_class_name('ai-usage-keyboard-focus');
        else
            this.remove_style_class_name('ai-usage-keyboard-focus');
    }

    vfunc_key_focus_in() {
        super.vfunc_key_focus_in();
        this._syncKeyboardFocus();
    }

    vfunc_key_focus_out() {
        super.vfunc_key_focus_out();
        this._syncKeyboardFocus();
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
            onComplete: () => v.ease({
                scale_x: 1,
                scale_y: 1,
                duration: 120,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            }),
        });
    }

    activate(event) {
        // Clicks on the chip belong to the chip (mockup: e.stopPropagation()).
        let source = null;
        try {
            source = event ? global.stage.get_event_actor(event) : null;
        } catch {
            source = null;
        }
        if (this._chip && source && (source === this._chip || this._chip.contains(source)))
            return;
        this.emit('navigate');
    }
});

const Indicator = GObject.registerClass(
class AiUsageIndicator extends PanelMenu.Button {
    _init(ext) {
        super._init(0.5, 'AI usage', false);
        this.add_style_class_name('ai-usage-panel-button');
        this._ext = ext;
        this._icons = ext.icons;
        this._state = null;      // parsed daemon state, or null when the daemon is away
        this._screen = 'list';
        this._toolId = null;
        this._lastSwapped = null;
        this._firstRender = true;

        this._dot = new St.Widget({
            style_class: 'ai-usage-dot',
            y_align: Clutter.ActorAlign.CENTER,
            accessible_name: 'AI usage',
        });
        this.add_child(this._dot);

        this.menu.actor.add_style_class_name('ai-usage-menu');
        this.menu.connect('open-state-changed', (_menu, open) => {
            if (open) {
                this._ext.refresh();
                if (this._screen !== 'list')
                    this._navigate('list');
            }
        });

        this._render(false);
    }

    setState(state) {
        this._state = state;
        const tools = this.tools;
        if (this._screen === 'detail' &&
            !tools.find(t => t.id === this._toolId && (!t.status || t.status === 'ok'))) {
            this._screen = 'list';
            this._toolId = null;
        }
        this._updateDot();
        this._render(false);
    }

    get tools() {
        return Array.isArray(this._state?.tools) ? this._state.tools : [];
    }

    _updateDot() {
        const values = this.tools
            .filter(t => !t.status || t.status === 'ok')
            .map(t => clampPct(primaryOf(t)?.value ?? 0));
        let level = 'error';
        if (values.length) {
            const worst = Math.max(...values);
            level = worst >= 90 ? 'critical' : worst >= 70 ? 'caution' : 'ok';
        }
        for (const cls of ['caution', 'critical', 'error'])
            this._dot.remove_style_class_name(cls);
        if (level !== 'ok')
            this._dot.add_style_class_name(level);
    }

    _navigate(screen, toolId = null) {
        this._screen = screen;
        this._toolId = toolId;
        this._render(true);
    }

    _render(animate) {
        this.menu.box.destroy_all_children();
        const screen = new St.BoxLayout({
            style_class: 'ai-usage-screen',
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
        });
        if (this._screen === 'detail')
            this._renderDetail(screen);
        else if (this._screen === 'guide')
            this._renderGuide(screen);
        else if (this._screen === 'about')
            this._renderAbout(screen);
        else
            this._renderList(screen);
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
        }
    }

    _header(title) {
        const header = new St.BoxLayout({style_class: 'ai-usage-header', x_expand: true});
        header.add_child(label(title, 'ai-usage-header-title'));
        return header;
    }

    _detailHeader(title, icon) {
        const header = new St.BoxLayout({style_class: 'ai-usage-detail-header', x_expand: true});
        const back = new St.Button({
            style_class: 'ai-usage-back',
            can_focus: true,
            accessible_name: 'Back',
            y_align: Clutter.ActorAlign.CENTER,
            child: new St.Icon({
                style_class: 'ai-usage-back-icon',
                gicon: this._icons.chevronLeft,
                icon_size: 16,
            }),
        });
        back.connect('clicked', () => this._navigate('list'));
        header.add_child(back);
        if (icon) {
            header.add_child(new St.Bin({
                style_class: 'ai-usage-badge',
                y_align: Clutter.ActorAlign.CENTER,
                child: new St.Icon({
                    style_class: 'ai-usage-badge-icon',
                    gicon: this._icons.badge(icon),
                    icon_size: 14,
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                }),
            }));
        }
        header.add_child(label(title, 'ai-usage-detail-title', {y_align: Clutter.ActorAlign.CENTER}));
        return header;
    }

    _footer(withSettings) {
        const footer = new St.BoxLayout({style_class: 'ai-usage-footer', x_expand: true});
        const add = (text, cb) => {
            const b = new St.Button({
                style_class: 'ai-usage-footer-btn',
                label: text,
                can_focus: true,
                x_expand: true,
            });
            b.connect('clicked', cb);
            footer.add_child(b);
        };
        if (withSettings)
            add('Settings', () => this._openSettings());
        add('Guide', () => this._navigate('guide'));
        add('About', () => this._navigate('about'));
        return footer;
    }

    _renderList(screen) {
        screen.add_child(this._header('AI usage'));
        const tools = this.tools;
        if (!tools.length) {
            const text = this._state
                ? 'No providers yet.\nSign in to Cursor and refresh.'
                : 'Daemon not running.\nStart it with:\nsystemctl --user start cursor-spend-monitor';
            screen.add_child(wrappedLabel(text, 'ai-usage-empty'));
            screen.add_child(this._footer(false));
            return;
        }
        const section = new St.BoxLayout({
            style_class: 'ai-usage-section',
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
        });
        for (const tool of tools) {
            const row = new Row(this._icons, tool, this._lastSwapped === tool.id);
            row.connect('navigate', () => this._navigate('detail', tool.id));
            row.connect('swap', () => this._swap(tool));
            section.add_child(row);
        }
        this._lastSwapped = null;
        screen.add_child(section);
        screen.add_child(this._footer(true));
    }

    _renderDetail(screen) {
        const tool = this.tools.find(t => t.id === this._toolId);
        if (!tool) {
            this._screen = 'list';
            this._renderList(screen);
            return;
        }
        screen.add_child(this._detailHeader(tool.name, tool.icon));

        const body = new St.BoxLayout({
            style_class: 'ai-usage-detail-body',
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
        });
        for (const m of tool.metrics ?? []) {
            const pct = clampPct(m.value);
            const color = colorFor(pct);
            const block = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});
            const top = new St.BoxLayout({style_class: 'ai-usage-metric-top', x_expand: true});
            top.add_child(label(m.label, null, {x_expand: true}));
            top.add_child(label(`${Math.round(pct)}%`, 'ai-usage-detail-value', {style: `color: ${color};`}));
            block.add_child(top);
            block.add_child(new Bar(pct, color));
            block.add_child(label(m.resets ?? '', 'ai-usage-detail-reset'));
            body.add_child(block);
        }
        screen.add_child(body);

        const dash = new St.Button({
            style_class: 'ai-usage-dash-btn',
            label: 'Open dashboard',
            can_focus: true,
            x_expand: true,
        });
        dash.connect('clicked', () => this._openUri(tool.dashboardUrl || 'https://cursor.com/dashboard'));
        screen.add_child(dash);
    }

    _guideItem(color, title, desc) {
        const item = new St.BoxLayout({style_class: 'ai-usage-guide-item', x_expand: true});
        item.add_child(new St.Widget({
            style_class: 'ai-usage-guide-dot',
            style: `background-color: ${color};`,
            y_align: Clutter.ActorAlign.START,
            y_expand: false,
        }));
        const text = new St.BoxLayout({
            style_class: 'ai-usage-guide-text',
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
        });
        text.add_child(label(title, 'ai-usage-guide-title'));
        text.add_child(wrappedLabel(desc, 'ai-usage-guide-desc'));
        item.add_child(text);
        return item;
    }

    _renderGuide(screen) {
        screen.add_child(this._detailHeader('Status colors', null));
        const body = new St.BoxLayout({
            style_class: 'ai-usage-guide-body',
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
        });
        body.add_child(this._guideItem(COLOR.ok, 'Healthy', 'Plenty of headroom — under 70% used.'));
        body.add_child(this._guideItem(COLOR.wait, 'Caution', 'Getting close — 70 to 89% used.'));
        body.add_child(this._guideItem(COLOR.crit, 'Critical', 'At or near your limit — 90% and up.'));
        screen.add_child(body);
    }

    _renderAbout(screen) {
        screen.add_child(this._detailHeader('About', null));
        const body = new St.BoxLayout({
            style_class: 'ai-usage-guide-body',
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
        });
        const intro = new St.BoxLayout({
            style_class: 'ai-usage-guide-text',
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
        });
        intro.add_child(label('AI usage', 'ai-usage-guide-title'));
        intro.add_child(wrappedLabel(
            'Local GNOME Shell indicator for AI coding limits. Cursor is live; OpenCode and Claude Code are next.',
            'ai-usage-guide-desc'));
        body.add_child(intro);

        const daemon = this._state
            ? `Daemon v${this._state.version ?? '?'} · updated ${relativeTime(this._state.updated_at)}`
            : 'Daemon not running';
        const status = new St.BoxLayout({
            style_class: 'ai-usage-guide-text',
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
        });
        status.add_child(label(`Extension v${this._ext.metadata.version}`, 'ai-usage-guide-title'));
        status.add_child(wrappedLabel(this._state?.error ? `${daemon}\n${this._state.error}` : daemon,
            'ai-usage-guide-desc'));
        body.add_child(status);
        screen.add_child(body);

        const refresh = new St.Button({
            style_class: 'ai-usage-dash-btn ai-usage-refresh-btn',
            label: 'Refresh now',
            can_focus: true,
            x_expand: true,
        });
        refresh.connect('clicked', () => this._ext.refresh());
        screen.add_child(refresh);
    }

    _swap(tool) {
        const secondary = secondaryOf(tool);
        if (!secondary)
            return;
        tool.primary = secondary.key;
        this._lastSwapped = tool.id;
        this._ext.setPrimary(tool.id, secondary.key);
        this._updateDot();
        this._render(false);
    }

    _openUri(uri) {
        this.menu.close();
        try {
            Gio.AppInfo.launch_default_for_uri(uri, global.create_app_launch_context(0, -1));
        } catch (e) {
            console.error(`[ai-usage] failed to open ${uri}: ${e.message}`);
        }
    }

    _openSettings() {
        const file = Gio.File.new_for_path(CONFIG_PATH);
        const target = file.query_exists(null) ? file : file.get_parent();
        this._openUri(target.get_uri());
    }
});

export default class AiUsageExtension extends Extension {
    enable() {
        this.icons = {
            badge: name => this._icon(`${name || 'cursor'}-symbolic`),
            chevronRight: this._icon('chevron-right-symbolic'),
            chevronLeft: this._icon('chevron-left-symbolic'),
        };
        this._indicator = new Indicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator, 0, 'right');

        this._cancellable = new Gio.Cancellable();
        this._proxy = null;
        this._stateSignalId = 0;
        this._ownerSignalId = 0;
        new UsageProxy(Gio.DBus.session, BUS_NAME, OBJECT_PATH, (proxy, error) => {
            if (error) {
                if (!this._cancellable?.is_cancelled())
                    console.error(`[ai-usage] D-Bus proxy failed: ${error.message}`);
                return;
            }
            if (!this._indicator)
                return;
            this._proxy = proxy;
            this._stateSignalId = proxy.connectSignal('StateChanged', (_p, _sender, [json]) => {
                this._applyJson(json);
            });
            this._ownerSignalId = proxy.connect('notify::g-name-owner', () => this._fetchState());
            this._fetchState();
        }, this._cancellable, Gio.DBusProxyFlags.DO_NOT_AUTO_START);
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

    _applyJson(json) {
        try {
            this._indicator?.setState(JSON.parse(json));
        } catch (e) {
            console.error(`[ai-usage] bad state payload: ${e.message}`);
        }
    }

    _fetchState() {
        if (!this._proxy || !this._indicator)
            return;
        if (!this._proxy.g_name_owner) {
            this._indicator.setState(null);
            return;
        }
        this._proxy.GetStateRemote((result, error) => {
            if (error) {
                if (!this._cancellable?.is_cancelled())
                    console.error(`[ai-usage] GetState failed: ${error.message}`);
                return;
            }
            this._applyJson(result[0]);
        });
    }

    refresh() {
        if (this._proxy?.g_name_owner)
            this._proxy.RefreshRemote(() => {});
    }

    setPrimary(providerId, metricKey) {
        if (this._proxy?.g_name_owner)
            this._proxy.SetPrimaryRemote(providerId, metricKey, () => {});
    }
}
