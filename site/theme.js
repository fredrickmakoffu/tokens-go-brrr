/* Site theme: auto (follow the system), light or dark.
 *
 * Loaded in <head>, before first paint, so data-theme is already on <html>
 * when the page draws and a dark-system visitor never sees a light flash.
 * ?theme=light|dark wins for that load only (handy for screenshots); a click on
 * the toggle flips light/dark and saves the choice (before that, no choice is
 * stored and the page tracks the system). Tokens in styles.css key off [data-theme].
 */
(function () {
  var KEY = "tgb-theme";
  var MODES = ["auto", "light", "dark"];
  var mql = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
  var listeners = [];

  function initial() {
    var q = null, s = null;
    try { q = new URLSearchParams(location.search).get("theme"); } catch (e) {}
    try { s = localStorage.getItem(KEY); } catch (e) {}
    return MODES.indexOf(q) >= 0 ? q : MODES.indexOf(s) >= 0 ? s : "auto";
  }

  var mode = initial();

  function resolved() { return mode === "auto" ? (mql && mql.matches ? "dark" : "light") : mode; }

  function apply() {
    var r = resolved(), root = document.documentElement;
    root.setAttribute("data-theme", r);
    root.style.colorScheme = r;
    listeners.forEach(function (fn) { fn(r); });
  }

  function setMode(m) {
    if (MODES.indexOf(m) < 0 || m === mode) return;
    mode = m;
    try { localStorage.setItem(KEY, m); } catch (e) {}
    apply();
  }

  if (mql) {
    var onSystem = function () { if (mode === "auto") apply(); };
    if (mql.addEventListener) mql.addEventListener("change", onSystem); else if (mql.addListener) mql.addListener(onSystem);
  }

  window.THEME = {
    mode: function () { return mode; },
    resolved: resolved,
    // Two states only. Until the first click the theme is the system's; a click
    // flips whatever is showing and from then on the choice is saved.
    toggle: function () { setMode(resolved() === "dark" ? "light" : "dark"); },
    subscribe: function (fn) { listeners.push(fn); return function () { listeners = listeners.filter(function (f) { return f !== fn; }); }; },
  };
  apply();
})();
