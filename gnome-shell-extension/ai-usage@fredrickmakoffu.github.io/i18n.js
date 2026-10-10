// Translation for the popover: en, fr and pt-BR, the same three languages as the
// website, chosen from the session's locale.
//
// This is a plain catalog rather than gettext on purpose. The extension is
// shipped by our own packages, which copy the directory as it is, so a catalog
// in JS needs no msgfmt step in the rpm/deb builds and no compiled .mo files to
// keep in step. (Publishing on extensions.gnome.org would want gettext; the
// keys here are stable, so moving to .po later is a mechanical change.)
//
// tr("key", { n: 3 }) looks the key up in the current catalog, falls back to
// English, then to the key itself. {name} is replaced from the vars; if vars.n
// is set and "key_one" / "key_other" exist, the plural form for n wins.

import GLib from "gi://GLib";

import { CATALOGS } from "./locales.js";

const FALLBACK = "en";

// The first of the user's preferred languages we have a catalog for. GLib reads
// LANGUAGE, LC_ALL, LC_MESSAGES and LANG, so this follows the session without
// asking the shell. AI_USAGE_LANG overrides it for screenshots and testing.
export function detectLocale(names = GLib.get_language_names()) {
    const forced = GLib.getenv("AI_USAGE_LANG");
    const wanted = forced ? [forced] : names;
    for (const name of wanted) {
        const base = String(name).toLowerCase().split(/[_.@-]/)[0];
        if (base === "pt") return "pt-BR";
        if (base === "fr") return "fr";
        if (base === "en") return "en";
    }
    return FALLBACK;
}

let current = detectLocale();

export function locale() {
    return current;
}

// Test hook, and the way a future in-popover language choice would plug in.
export function setLocale(code) {
    current = CATALOGS[code] ? code : FALLBACK;
}

export function has(key) {
    return key in CATALOGS[current] || key in CATALOGS[FALLBACK];
}

export function tr(key, vars) {
    const catalog = CATALOGS[current] ?? CATALOGS[FALLBACK];
    const english = CATALOGS[FALLBACK];
    let k = key;
    if (vars && vars.n !== undefined) {
        const form = new Intl.PluralRules(current).select(vars.n);
        for (const candidate of [`${key}_${form}`, `${key}_other`]) {
            if (candidate in catalog || candidate in english) {
                k = candidate;
                break;
            }
        }
    }
    let text = k in catalog ? catalog[k] : k in english ? english[k] : key;
    if (vars)
        text = text.replace(/\{(\w+)\}/g, (m, name) =>
            name in vars ? String(vars[name]) : m,
        );
    return text;
}

// -- numbers and durations ---------------------------------------------------

export function num(n, options) {
    return Number(n).toLocaleString(current, options);
}

// 8400000 -> "8.4M" ("8,4M" in French); the same steps as the daemon's
// format_tokens, so a number reads the same wherever it is written.
export function formatTokens(value) {
    const n = Number(value) || 0;
    if (!n) return "0";
    for (const [limit, suffix] of [
        [1e9, "B"],
        [1e6, "M"],
        [1e3, "K"],
    ]) {
        if (Math.abs(n) >= limit) {
            const scaled = Math.round((n / limit) * 10) / 10;
            return num(scaled, { maximumFractionDigits: 1 }) + suffix;
        }
    }
    return String(Math.round(n));
}

// Seconds as the daemon's eta_label and resets_label write them: "<1m", "45m",
// "3h 10m", "5h", then whole days from 48 hours.
export function duration(seconds) {
    const secs = Math.max(0, Math.floor(Number(seconds) || 0));
    if (secs < 60) return tr("dur.lt1m");
    const minutes = Math.floor(secs / 60);
    if (minutes < 60) return tr("dur.m", { m: minutes });
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    if (hours >= 48) return tr("dur.days", { n: Math.floor(hours / 24) });
    return rest
        ? tr("dur.hm", { h: hours, m: rest })
        : tr("dur.h", { h: hours });
}

// "Resets in 2h 15m" / "Resets soon", or "" when the daemon sent nothing to
// build one from. A daemon older than this extension sends only the English
// label, so that stands in rather than the row going blank.
export function resetsText(m) {
    if (!m) return "";
    if (Number.isFinite(m.resetsSeconds)) {
        if (m.resetsSeconds <= 0) return tr("resets.soon");
        return tr("resets.in", { dur: duration(m.resetsSeconds) });
    }
    const legacy = m.resets;
    return legacy && legacy !== "—" ? legacy : "";
}

// First letter down, for a phrase that follows another in a sentence.
export function lcFirst(text) {
    return text ? text.charAt(0).toLocaleLowerCase(current) + text.slice(1) : text;
}

export function ucFirst(text) {
    return text ? text.charAt(0).toLocaleUpperCase(current) + text.slice(1) : text;
}

// -- the daemon's English, as keys ------------------------------------------

// Meter labels come from the providers in English ("5-hour limit", "Weekly").
// They are matched exactly; anything unknown is shown as the daemon wrote it.
export function metricLabel(text) {
    if (!text) return "—";
    const key = `label.${text}`;
    if (has(key)) return tr(key);
    const days = text.match(/^(\d+) day window$/);
    if (days) return tr("label.dayWindow", { n: Number(days[1]) });
    return text;
}

// The short form that sits beside a provider's name: "5-hour limit" -> "5-hour".
export function metricTag(text) {
    if (!text) return "—";
    const key = `tag.${text}`;
    if (has(key)) return tr(key);
    return metricLabel(text).replace(/\s+limits?$/i, "");
}

// A few fixed messages the daemon sends as errors. Diagnostics with a detail
// ("HTTP 429 from Claude usage: ...") are technical and pass through unchanged.
export function errorText(message) {
    if (!message) return message;
    const key = `err.${message}`;
    return has(key) ? tr(key) : message;
}
