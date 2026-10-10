/* @ds-bundle: {"format":4,"namespace":"AIUsageDesignSystem_480680","components":[{"name":"ExtButton","sourcePath":"components/controls/ExtButton.jsx"},{"name":"ExtFilterChips","sourcePath":"components/controls/ExtFilterChips.jsx"},{"name":"ExtWindowPicker","sourcePath":"components/controls/ExtWindowPicker.jsx"},{"name":"EXT_ICON_PATHS","sourcePath":"components/icons/ExtIcon.jsx"},{"name":"ExtIcon","sourcePath":"components/icons/ExtIcon.jsx"},{"name":"PROVIDER_ICONS","sourcePath":"components/icons/ProviderIcon.jsx"},{"name":"ProviderIcon","sourcePath":"components/icons/ProviderIcon.jsx"},{"name":"ExtPanelIndicator","sourcePath":"components/panel/ExtPanelIndicator.jsx"},{"name":"ExtFooter","sourcePath":"components/popover/ExtFooter.jsx"},{"name":"ExtHeader","sourcePath":"components/popover/ExtHeader.jsx"},{"name":"ExtPopover","sourcePath":"components/popover/ExtPopover.jsx"},{"name":"ExtSection","sourcePath":"components/popover/ExtSection.jsx"},{"name":"ExtGuideItem","sourcePath":"components/rows/ExtGuideItem.jsx"},{"name":"ExtListRow","sourcePath":"components/rows/ExtListRow.jsx"},{"name":"ExtMeterRow","sourcePath":"components/rows/ExtMeterRow.jsx"},{"name":"ExtSessionRow","sourcePath":"components/rows/ExtSessionRow.jsx"},{"name":"ExtStats","sourcePath":"components/rows/ExtStats.jsx"}],"sourceHashes":{"components/controls/ExtButton.jsx":"d56839f76550","components/controls/ExtFilterChips.jsx":"0054371c8e03","components/controls/ExtWindowPicker.jsx":"b98aaeccacd1","components/icons/ExtIcon.jsx":"09890230e39f","components/icons/ProviderIcon.jsx":"1666afb15866","components/panel/ExtPanelIndicator.jsx":"3d3ff2519899","components/popover/ExtFooter.jsx":"b9548bda0c4c","components/popover/ExtHeader.jsx":"770a15d4d632","components/popover/ExtPopover.jsx":"9f0a1cace693","components/popover/ExtSection.jsx":"e28fffecc8a8","components/rows/ExtGuideItem.jsx":"7e61052f1cbc","components/rows/ExtListRow.jsx":"4bbbc1808afe","components/rows/ExtMeterRow.jsx":"32af0c012942","components/rows/ExtSessionRow.jsx":"3da140b89516","components/rows/ExtStats.jsx":"a9da20d2ace9","site/Directions.jsx":"049168973600","site/Shared.jsx":"79795b5d4de4","site/burn.jsx":"a2ac3fc9366d","site/releases.jsx":"dde83de18508","site/tweaks-panel.jsx":"d259e3a86f73","ui_kits/ai-usage-popover/App.jsx":"b6ec02dac281","ui_kits/ai-usage-popover/Screens.jsx":"dcca37b8b6cc","ui_kits/ai-usage-popover/TopBar.jsx":"aa0598f02d04","ui_kits/ai-usage-popover/data.jsx":"ab52bc1ac188"},"inlinedExternals":[],"unexposedExports":[{"name":"resolveIcon","sourcePath":"components/icons/ProviderIcon.jsx"}]} */

(() => {

const __ds_ns = (window.AIUsageDesignSystem_480680 = window.AIUsageDesignSystem_480680 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/controls/ExtFilterChips.jsx
try { (() => {
function ExtFilterChips({
  options = [],
  value,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, options.map(o => {
    const on = o.value === value;
    return /*#__PURE__*/React.createElement("button", {
      key: o.value,
      onClick: () => onChange && onChange(o.value),
      className: on ? undefined : "ext-chip",
      style: {
        padding: "3px 10px",
        border: "1px solid " + (on ? "var(--color-text)" : "var(--color-divider)"),
        background: on ? "var(--color-text)" : "transparent",
        color: on ? "var(--color-bg)" : "var(--muted)",
        fontFamily: "var(--font-body)",
        fontSize: 12,
        cursor: "pointer",
        fontVariantNumeric: "tabular-nums"
      }
    }, o.label, o.count != null ? " " + o.count : "");
  }));
}
Object.assign(__ds_scope, { ExtFilterChips });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/controls/ExtFilterChips.jsx", error: String((e && e.message) || e) }); }

// components/controls/ExtWindowPicker.jsx
try { (() => {
// The window picker at the foot of the agent list (from the shipped extension), redrawn square:
// flat buttons edge to edge; the chosen window keeps a brighter, heavier label and an accent rule on its top edge.
function ExtWindowPicker({
  options = [],
  value,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      borderTop: "1px solid var(--color-divider)"
    }
  }, options.map(o => {
    const sel = o.value === value;
    return /*#__PURE__*/React.createElement("button", {
      key: o.value,
      onClick: () => !sel && onChange && onChange(o.value),
      className: "ext-window-btn",
      style: {
        flex: "1 1 0",
        height: 36,
        padding: 0,
        border: 0,
        background: "transparent",
        cursor: "pointer",
        fontFamily: "var(--font-heading)",
        fontSize: 13,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: sel ? "var(--color-text)" : "var(--muted)",
        fontWeight: sel ? 600 : 400,
        boxShadow: sel ? "inset 0 2px 0 var(--color-accent)" : "none"
      }
    }, o.label);
  }));
}
Object.assign(__ds_scope, { ExtWindowPicker });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/controls/ExtWindowPicker.jsx", error: String((e && e.message) || e) }); }

// components/icons/ExtIcon.jsx
try { (() => {
// Lucide paths used by the Ext components, stroke-width 1.5.
const EXT_ICON_PATHS = {
  back: ["m12 19-7-7 7-7", "M19 12H5"],
  chevron: ["m9 18 6-6-6-6"],
  focus: ["m4 17 6-6-6-6M12 19h8"],
  check: ["M20 6 9 17l-5-5"],
  wifi: ["M12 20h.01", "M2 8.82a15 15 0 0 1 20 0", "M5 12.859a10 10 0 0 1 14 0", "M8.5 16.429a5 5 0 0 1 7 0"],
  battery: ["M22 14v-4"],
  settings: ["M20 7h-9", "M14 17H5"]
};
function ExtIcon({
  name = "chevron",
  size = 14,
  style
}) {
  const paths = EXT_ICON_PATHS[name] || [];
  return /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.5",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      display: "block",
      flex: "none",
      ...style
    }
  }, paths.map((d, i) => /*#__PURE__*/React.createElement("path", {
    key: i,
    d: d
  })), name === "battery" && /*#__PURE__*/React.createElement("rect", {
    x: "2",
    y: "6",
    width: "16",
    height: "12",
    rx: "2"
  }), name === "settings" && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "17",
    cy: "17",
    r: "3"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "7",
    cy: "7",
    r: "3"
  })));
}
Object.assign(__ds_scope, { EXT_ICON_PATHS, ExtIcon });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/icons/ExtIcon.jsx", error: String((e && e.message) || e) }); }

// components/controls/ExtButton.jsx
try { (() => {
function ExtButton({
  label,
  children,
  variant = "secondary",
  size = "md",
  block = false,
  icon,
  onClick,
  style
}) {
  const sm = size === "sm";
  const inner = {
    display: "flex",
    alignItems: "center",
    gap: 6,
    whiteSpace: "nowrap",
    padding: sm ? "4px 9px" : "9px 16px",
    fontSize: sm ? 13 : 15,
    lineHeight: 1.2
  };
  const wrap = block ? {
    flex: 1,
    minWidth: 0,
    display: "flex"
  } : {
    display: "inline-flex",
    flex: "none"
  };
  const isPrimary = variant === "primary";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      ...wrap,
      ...style
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    className: "ext-btn ext-btn-" + variant + (isPrimary ? " blueprint" : "")
  }, isPrimary && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("i", {
    className: "corner tl"
  }), /*#__PURE__*/React.createElement("i", {
    className: "corner tr"
  }), /*#__PURE__*/React.createElement("i", {
    className: "corner bl"
  }), /*#__PURE__*/React.createElement("i", {
    className: "corner br"
  })), /*#__PURE__*/React.createElement("span", {
    style: inner
  }, icon && (EXT_ICON_NAMES.includes(icon) ? /*#__PURE__*/React.createElement(__ds_scope.ExtIcon, {
    name: icon,
    size: 14
  }) : /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.5",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("path", {
    d: icon
  }))), label ?? children)));
}
const EXT_ICON_NAMES = ["back", "chevron", "focus", "check", "wifi", "battery", "settings"];
Object.assign(__ds_scope, { ExtButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/controls/ExtButton.jsx", error: String((e && e.message) || e) }); }

// components/icons/ProviderIcon.jsx
try { (() => {
// Provider marks as single paths, exactly as the Ext component sheets carry them.
const PROVIDER_ICONS = {
  claude: {
    d: "M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.970 2.970 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.030.456.898.243.832.091.255h.158V9.010l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.030.049.061 1.549.146.662.036h1.622l3.020.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.330.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.080-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.080-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.530.286-1.900.17-.632-.012-.042-.14.018-1.434 1.967-2.180 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.440-1.882.930-1.086-.006-.158h-.055L4.132 18.560l-1.130.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z",
    fill: "currentColor",
    stroke: "none",
    color: "#D97757"
  },
  opencode: {
    d: "M8.7 5.3L10.1 6.7 5.5 12l4.6 5.3-1.4 1.4L2.9 12zM15.3 5.3L21.1 12l-5.8 6.7-1.4-1.4L18.5 12l-4.6-5.3z",
    fill: "currentColor",
    stroke: "none"
  },
  pi: {
    d: "M3.6 6.4h16.8v2.5h-3.3v7.4c0 .7.3 1 .9 1 .5 0 .9-.2 1.3-.5l.9 2c-.8.6-1.7.9-2.8.9-2 0-3.1-1.1-3.1-3.2V8.9h-3.5l-.4 5.1c-.2 2.4-.7 4.1-1.5 5.2-.8 1-2 1.5-3.5 1.5l-.5-2.4c.8-.1 1.4-.4 1.8-1 .4-.7.7-1.9.8-3.6l.4-4.8H3.6z",
    fill: "currentColor",
    stroke: "none"
  },
  cursor: {
    d: "M4.037 4.688a.495.495 0 0 1 .651-.651l16 6.5a.5.5 0 0 1-.063.947l-6.124 1.58a2 2 0 0 0-1.438 1.435l-1.579 6.126a.5.5 0 0 1-.947.063z",
    fill: "none",
    stroke: "currentColor"
  }
};
function resolveIcon(icon) {
  if (!icon) return null;
  return typeof icon === "string" ? PROVIDER_ICONS[icon] || null : icon;
}
function ProviderIcon({
  provider = "claude",
  icon,
  size = 14,
  color,
  style
}) {
  const ic = resolveIcon(icon || provider);
  if (!ic) return null;
  return /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: ic.fill ?? "currentColor",
    stroke: ic.stroke ?? "none",
    strokeWidth: "1.5",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      display: "block",
      flex: "none",
      color: color || "currentColor",
      ...style
    }
  }, /*#__PURE__*/React.createElement("path", {
    d: ic.d
  }));
}
Object.assign(__ds_scope, { PROVIDER_ICONS, resolveIcon, ProviderIcon });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/icons/ProviderIcon.jsx", error: String((e && e.message) || e) }); }

// components/panel/ExtPanelIndicator.jsx
try { (() => {
// Top-bar indicator, from "AI Usage - Ask": 1a "Tightest limit" and 1b "Quiet until it matters".
function ExtPanelIndicator({
  variant = "tightest",
  urgent = false,
  provider = "claude",
  name = "Claude",
  value = "40m",
  sessions = [],
  dot = false
}) {
  const ic = __ds_scope.resolveIcon(provider);
  const heading = {
    fontFamily: "var(--font-heading)",
    fontSize: 15,
    lineHeight: 1.2
  };
  let body;
  if (variant === "quiet") {
    body = urgent ? /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 8px",
        background: "var(--color-neutral-100)",
        color: "var(--color-neutral-900)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        ...heading,
        fontWeight: 600
      }
    }, name + " · " + value)) : /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateRows: "5px 5px",
        gridAutoFlow: "column",
        gridAutoColumns: "5px",
        gap: 2,
        padding: "3px 8px"
      }
    }, sessions.map((s, i) => /*#__PURE__*/React.createElement("span", {
      key: i,
      style: {
        width: 5,
        height: 5,
        boxSizing: "border-box",
        background: s.paused ? "transparent" : "var(--color-accent-400)",
        border: s.paused ? "1px solid var(--color-accent-400)" : "none"
      }
    })));
  } else {
    body = urgent ? /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 8px",
        background: "color-mix(in srgb, var(--color-neutral-100) 12%, transparent)"
      }
    }, ic && /*#__PURE__*/React.createElement("svg", {
      width: "13",
      height: "13",
      viewBox: "0 0 24 24",
      fill: ic.fill ?? "currentColor",
      stroke: ic.stroke ?? "none",
      strokeWidth: "1.5"
    }, /*#__PURE__*/React.createElement("path", {
      d: ic.d
    })), /*#__PURE__*/React.createElement("span", {
      style: {
        ...heading,
        fontWeight: 600
      }
    }, value)) : /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 8px"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        ...heading,
        fontWeight: 500,
        color: "var(--color-neutral-400)"
      }
    }, value));
  }
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      color: "var(--color-neutral-100)",
      fontFamily: "var(--font-body)"
    }
  }, dot && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 7,
      height: 7,
      background: "oklch(0.75 0.15 65)"
    }
  }), body);
}
Object.assign(__ds_scope, { ExtPanelIndicator });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/panel/ExtPanelIndicator.jsx", error: String((e && e.message) || e) }); }

// components/popover/ExtFooter.jsx
try { (() => {
function ExtFooter({
  text,
  actionLabel,
  onAction,
  actions = [],
  onSettings,
  showSettings = true
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 6,
      padding: "8px 10px 8px 18px",
      borderTop: "1px solid var(--color-divider)",
      fontSize: 12,
      color: "var(--muted)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis"
    }
  }, text), actionLabel && /*#__PURE__*/React.createElement(__ds_scope.ExtButton, {
    variant: "ghost",
    size: "sm",
    label: actionLabel,
    onClick: onAction
  }), actions.map((a, i) => /*#__PURE__*/React.createElement(__ds_scope.ExtButton, {
    key: i,
    variant: "ghost",
    size: "sm",
    label: a.label,
    onClick: a.onClick
  })), showSettings && /*#__PURE__*/React.createElement("button", {
    "aria-label": window.t ? window.t("ds.settings") : "Settings",
    onClick: onSettings,
    className: "ext-settings-btn"
  }, /*#__PURE__*/React.createElement(__ds_scope.ExtIcon, {
    name: "settings",
    size: 15
  })));
}
Object.assign(__ds_scope, { ExtFooter });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/popover/ExtFooter.jsx", error: String((e && e.message) || e) }); }

// components/popover/ExtHeader.jsx
try { (() => {
function ExtHeader({
  kicker,
  meta,
  title,
  sub,
  onBack
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "18px 18px 14px",
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 6,
      fontFamily: "var(--font-heading)",
      fontSize: 12,
      letterSpacing: "0.12em",
      textTransform: "uppercase",
      color: "var(--muted)",
      minHeight: 22
    }
  }, typeof onBack === "function" && /*#__PURE__*/React.createElement("button", {
    onClick: onBack,
    "aria-label": window.t ? window.t("ds.back") : "Back",
    className: "ext-icon-btn",
    style: {
      width: 22,
      height: 22,
      marginLeft: -4,
      color: "var(--color-text)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.ExtIcon, {
    name: "back",
    size: 16
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1
    }
  }, kicker), /*#__PURE__*/React.createElement("span", null, meta)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-heading)",
      fontWeight: 600,
      fontSize: 26,
      lineHeight: 1.05,
      textWrap: "pretty"
    }
  }, title), sub && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      lineHeight: 1.45,
      color: "var(--muted)",
      textWrap: "pretty"
    }
  }, sub));
}
Object.assign(__ds_scope, { ExtHeader });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/popover/ExtHeader.jsx", error: String((e && e.message) || e) }); }

// components/popover/ExtPopover.jsx
try { (() => {
function ExtPopover({
  dark = false,
  signal = false,
  width = 380,
  children,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    "data-theme": dark ? "dark" : "light",
    "data-status": signal ? "signal" : "mono",
    style: {
      display: "inline-block"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "blueprint",
    style: {
      width,
      background: "var(--color-bg)",
      color: "var(--color-text)",
      fontFamily: "var(--font-body)",
      boxShadow: "var(--shadow-lg)",
      display: "flex",
      flexDirection: "column",
      lineHeight: 1.55,
      ...style
    }
  }, /*#__PURE__*/React.createElement("i", {
    className: "corner tl"
  }), /*#__PURE__*/React.createElement("i", {
    className: "corner tr"
  }), /*#__PURE__*/React.createElement("i", {
    className: "corner bl"
  }), /*#__PURE__*/React.createElement("i", {
    className: "corner br"
  }), children));
}
Object.assign(__ds_scope, { ExtPopover });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/popover/ExtPopover.jsx", error: String((e && e.message) || e) }); }

// components/popover/ExtSection.jsx
try { (() => {
function ExtSection({
  label,
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      borderTop: "1px solid var(--color-divider)",
      paddingBottom: 4
    }
  }, label && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "12px 18px 2px",
      fontFamily: "var(--font-heading)",
      fontSize: 12,
      letterSpacing: "0.12em",
      textTransform: "uppercase",
      color: "var(--muted)"
    }
  }, label), children);
}
Object.assign(__ds_scope, { ExtSection });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/popover/ExtSection.jsx", error: String((e && e.message) || e) }); }

// components/rows/ExtGuideItem.jsx
try { (() => {
function ExtGuideItem({
  status,
  marker,
  title,
  desc
}) {
  const mark = marker || (status ? "square" : null);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 12,
      padding: "8px 18px"
    }
  }, mark === "square" && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 9,
      height: 9,
      flex: "none",
      marginTop: 5,
      background: "var(--st-" + status + ")"
    }
  }), mark === "pace" && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 9,
      height: 10,
      flex: "none",
      marginTop: 4,
      position: "relative"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      left: 0,
      right: 0,
      top: 3,
      height: 4,
      background: "color-mix(in srgb, var(--color-text) 11%, transparent)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      left: 4,
      top: 0,
      width: 1,
      height: 10,
      background: "var(--color-text)"
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14,
      fontWeight: 600
    }
  }, title), desc && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      lineHeight: 1.4,
      color: "var(--muted)",
      textWrap: "pretty"
    }
  }, desc)));
}
Object.assign(__ds_scope, { ExtGuideItem });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/rows/ExtGuideItem.jsx", error: String((e && e.message) || e) }); }

// components/rows/ExtListRow.jsx
try { (() => {
function ExtListRow({
  kicker,
  title,
  meta,
  onClick
}) {
  return /*#__PURE__*/React.createElement("div", {
    onClick: onClick,
    className: "ext-row-hover",
    style: {
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: "10px 14px 10px 18px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: 3
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-heading)",
      fontSize: 12,
      letterSpacing: "0.1em",
      textTransform: "uppercase",
      color: "var(--muted)"
    }
  }, kicker), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14,
      fontWeight: 600,
      lineHeight: 1.35,
      textWrap: "pretty"
    }
  }, title), meta && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      color: "var(--muted)"
    }
  }, meta)), /*#__PURE__*/React.createElement(__ds_scope.ExtIcon, {
    name: "chevron",
    size: 14,
    style: {
      color: "var(--muted)"
    }
  }));
}
Object.assign(__ds_scope, { ExtListRow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/rows/ExtListRow.jsx", error: String((e && e.message) || e) }); }

// components/rows/ExtMeterRow.jsx
try { (() => {
function ExtMeterRow({
  label,
  tag,
  value = 0,
  elapsed,
  status = "ok",
  sub,
  muted = false,
  showPace = true,
  pct,
  icon,
  onClick
}) {
  const col = "var(--st-" + status + ")";
  const v = Number(value);
  const ic = __ds_scope.resolveIcon(icon);
  const clickable = typeof onClick === "function";
  const crit = status === "crit" && !muted;
  return /*#__PURE__*/React.createElement("div", {
    onClick: onClick,
    className: clickable ? "ext-row-hover" : undefined,
    style: {
      display: "flex",
      gap: 12,
      padding: "11px 14px 11px 18px",
      alignItems: "flex-start"
    }
  }, ic && /*#__PURE__*/React.createElement("div", {
    style: {
      width: 26,
      height: 26,
      flex: "none",
      border: "1px solid var(--color-divider)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      color: "var(--color-text)"
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: ic.fill ?? "currentColor",
    stroke: ic.stroke ?? "none",
    strokeWidth: "1.5",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("path", {
    d: ic.d
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "baseline",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14,
      fontWeight: 600,
      whiteSpace: "nowrap"
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-heading)",
      fontSize: 12,
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      color: "var(--muted)",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis"
    }
  }, tag), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-heading)",
      fontSize: 22,
      lineHeight: 1,
      fontWeight: status === "crit" ? 700 : 600,
      color: muted ? "var(--muted)" : status === "ok" ? "var(--color-text)" : col,
      fontVariantNumeric: "tabular-nums"
    }
  }, pct ?? v + "%")), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      height: 4,
      background: "color-mix(in srgb, var(--color-text) 11%, transparent)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      left: 0,
      top: 0,
      bottom: 0,
      width: v + "%",
      background: muted ? "color-mix(in srgb, var(--color-text) 30%, transparent)" : col
    }
  }), showPace && elapsed != null && elapsed > 8 && /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      left: "calc(" + elapsed + "% - 0.5px)",
      top: -3,
      width: 1,
      height: 10,
      background: "var(--color-text)"
    }
  })), sub && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      lineHeight: 1.3,
      color: crit ? col : "var(--muted)",
      fontWeight: crit ? 600 : 400
    }
  }, sub)), clickable && /*#__PURE__*/React.createElement(__ds_scope.ExtIcon, {
    name: "chevron",
    size: 14,
    style: {
      color: "var(--muted)",
      marginTop: 4
    }
  }));
}
Object.assign(__ds_scope, { ExtMeterRow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/rows/ExtMeterRow.jsx", error: String((e && e.message) || e) }); }

// components/rows/ExtSessionRow.jsx
try { (() => {
function ExtSessionRow({
  project,
  meta,
  paused = false,
  focused = false,
  onFocus
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: "8px 18px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 7,
      height: 7,
      flex: "none",
      boxSizing: "border-box",
      background: paused ? "transparent" : "var(--color-accent)",
      border: paused ? "1px solid var(--muted)" : "none"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: 1
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14,
      fontWeight: 600
    }
  }, project), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      color: "var(--muted)",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis"
    }
  }, meta)), /*#__PURE__*/React.createElement(__ds_scope.ExtButton, {
    variant: "secondary",
    size: "sm",
    label: window.t ? window.t(focused ? "ds.focused" : "ds.focus") : (focused ? "Focused" : "Focus"),
    icon: focused ? "check" : "focus",
    onClick: onFocus
  }));
}
Object.assign(__ds_scope, { ExtSessionRow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/rows/ExtSessionRow.jsx", error: String((e && e.message) || e) }); }

// components/rows/ExtStats.jsx
try { (() => {
function ExtStats({
  items = []
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      borderTop: "1px solid var(--color-divider)",
      borderBottom: "1px solid var(--color-divider)"
    }
  }, items.map((it, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      flex: "1 1 0",
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: 5,
      padding: "12px 14px 12px 18px",
      borderLeft: i ? "1px solid var(--color-divider)" : "none",
      paddingLeft: i ? 14 : 18
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-heading)",
      fontWeight: 600,
      fontSize: 28,
      lineHeight: 1,
      fontVariantNumeric: "tabular-nums"
    }
  }, it.value), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      lineHeight: 1.3,
      color: "var(--muted)"
    }
  }, it.label))));
}
Object.assign(__ds_scope, { ExtStats });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/rows/ExtStats.jsx", error: String((e && e.message) || e) }); }

// site/Directions.jsx
try { (() => {
function useWide(min) {
  const [w, setW] = React.useState(innerWidth >= min);
  React.useEffect(() => {
    const f = () => setW(innerWidth >= min);
    addEventListener("resize", f);
    return () => removeEventListener("resize", f);
  }, [min]);
  return w;
}
function Sections({
  b,
  dark
}) {
  const sec = {
    padding: "72px 0 24px"
  };
  const rel = useReleases();
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("section", {
    id: "download",
    style: sec,
    "data-screen-label": "Download"
  }, /*#__PURE__*/React.createElement(SectionHead, {
    n: "01",
    kicker: "Download",
    title: "Pick your platform. " + rel.latest.tag + " is the latest.",
    b: b
  }), /*#__PURE__*/React.createElement(Downloads, {
    b: b,
    rel: rel
  })), /*#__PURE__*/React.createElement("section", {
    id: "screens",
    style: sec,
    "data-screen-label": "What it does"
  }, /*#__PURE__*/React.createElement(SectionHead, {
    n: "02",
    kicker: "What it does",
    title: "One indicator, one sentence, then the detail.",
    b: b
  }), /*#__PURE__*/React.createElement(Facts, null), /*#__PURE__*/React.createElement(Gallery, {
    dark: dark
  })), /*#__PURE__*/React.createElement("section", {
    id: "local",
    style: sec,
    "data-screen-label": "Local only"
  }, /*#__PURE__*/React.createElement(SectionHead, {
    n: "03",
    kicker: "Local only",
    title: "It reuses logins already on disk and keeps its history at home.",
    b: b
  }), /*#__PURE__*/React.createElement(Privacy, null)), /*#__PURE__*/React.createElement("section", {
    id: "faq",
    style: sec,
    "data-screen-label": "FAQ"
  }, /*#__PURE__*/React.createElement(SectionHead, {
    n: "04",
    kicker: "FAQ",
    title: "Questions before installing.",
    b: b
  }), /*#__PURE__*/React.createElement(Faq, null)), /*#__PURE__*/React.createElement("section", {
    id: "releases",
    style: {
      ...sec,
      paddingBottom: 72
    },
    "data-screen-label": "Releases"
  }, /*#__PURE__*/React.createElement(SectionHead, {
    n: "05",
    kicker: "Releases",
    title: "Every build, with its files.",
    b: b
  }), /*#__PURE__*/React.createElement(Releases, {
    rel: rel
  })), /*#__PURE__*/React.createElement(SiteFooter, null));
}
const HERO_SUB = "A status dot in your top bar for your AI coding limits. It reads what Cursor, Claude Code, OpenCode, Pi and Codex have used, and says in one sentence which runs out first.";
const HeroButtons = () => /*#__PURE__*/React.createElement("div", {
  style: {
    display: "flex",
    flexWrap: "wrap",
    gap: 12,
    padding: 6
  }
}, /*#__PURE__*/React.createElement(ExtButton, {
  variant: "primary",
  label: "Download for Linux",
  onClick: () => goTo("download"),
  style: {
    minWidth: 200
  }
}), /*#__PURE__*/React.createElement(ExtButton, {
  variant: "secondary",
  label: "What it does",
  onClick: () => goTo("screens")
}));
function DirA({
  b
}) {
  const wide = useWide(1040);
  const [drop, setDrop] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    "data-theme": "light",
    "data-status": "signal",
    style: {
      background: "var(--color-bg)",
      color: "var(--color-text)",
      minHeight: "100vh"
    }
  }, /*#__PURE__*/React.createElement(TopBar, {
    b: b,
    open: drop,
    onToggle: () => setDrop(d => !d)
  }), (drop || !wide) && drop && /*#__PURE__*/React.createElement("div", {
    style: {
      position: "fixed",
      top: 40,
      right: 16,
      zIndex: 60
    }
  }, /*#__PURE__*/React.createElement(PagePopover, {
    b: b
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1320,
      margin: "0 auto",
      padding: "0 clamp(20px, 4vw, 48px)",
      display: "grid",
      gridTemplateColumns: wide ? "minmax(0,1fr) 392px" : "minmax(0,1fr)",
      gap: 72
    }
  }, /*#__PURE__*/React.createElement("main", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("section", {
    "data-screen-label": "Hero",
    style: {
      padding: "clamp(56px, 9vw, 112px) 0 40px",
      display: "flex",
      flexDirection: "column",
      gap: 28
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: KICK
  }, "GNOME Shell extension · Fedora and Debian/Ubuntu"), /*#__PURE__*/React.createElement("h1", {
    style: {
      ...HEAD,
      fontSize: "clamp(72px, 10.5vw, 156px)",
      lineHeight: 0.86,
      margin: 0,
      letterSpacing: "-0.01em"
    }
  }, "Tokens go ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: stColor(b.status),
      transition: "color 300ms"
    }
  }, "brrr.")), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 20,
      lineHeight: 1.45,
      maxWidth: 560,
      textWrap: "pretty"
    }
  }, HERO_SUB), /*#__PURE__*/React.createElement(HeroButtons, null), /*#__PURE__*/React.createElement("div", {
    className: "blueprint",
    style: {
      padding: "16px 18px",
      maxWidth: 560,
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Corners, null), /*#__PURE__*/React.createElement("span", {
    style: KICK
  }, "This page is metered"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 15,
      textWrap: "pretty"
    }
  }, "It has 200,000 tokens per 5-minute window. Scrolling spends them, and so do clicks and copied commands. " + (wide ? "The popover on the right is the extension's own, pointed at this page." : "Tap the indicator in the bar above to open its popover.")))), /*#__PURE__*/React.createElement(Sections, {
    b: b
  })), wide && /*#__PURE__*/React.createElement("aside", null, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "sticky",
      top: 54,
      padding: "24px 6px",
      display: "flex",
      flexDirection: "column",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement(PagePopover, {
    b: b
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      color: "var(--muted)",
      paddingLeft: 2
    }
  }, "Window resets after 5 minutes, or press Reset window.")))));
}
function Rail({
  b
}) {
  const c = stColor(b.status);
  const lab = {
    ...HEAD,
    fontSize: 12,
    letterSpacing: "0.08em",
    color: "var(--muted)",
    position: "absolute",
    left: 0,
    width: "100%",
    textAlign: "center"
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "fixed",
      left: 0,
      top: 30,
      bottom: 0,
      width: 76,
      borderRight: "1px solid var(--color-divider)",
      zIndex: 5,
      background: "var(--color-bg)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      ...lab,
      top: 12
    }
  }, "0"), /*#__PURE__*/React.createElement("span", {
    style: {
      ...lab,
      bottom: 12
    }
  }, "200k"), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      top: 40,
      bottom: 40,
      left: 26,
      width: 6,
      background: "var(--track)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      left: 0,
      top: 0,
      width: "100%",
      height: b.pct + "%",
      background: c,
      transition: "height 200ms ease-out, background-color 300ms"
    }
  }), /*#__PURE__*/React.createElement("div", {
    title: "Even pace",
    style: {
      position: "absolute",
      left: -5,
      width: 16,
      height: 1,
      top: b.elapsedPct + "%",
      background: "var(--color-text)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      ...HEAD,
      position: "absolute",
      left: 14,
      top: "calc(" + b.pct + "% - 9px)",
      fontSize: 15,
      fontVariantNumeric: "tabular-nums",
      color: "var(--color-text)",
      transition: "top 200ms ease-out"
    }
  }, b.pct)));
}
function Readout({
  b
}) {
  const cell = {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    padding: "14px 18px",
    borderLeft: "1px solid var(--color-divider)",
    minWidth: 0
  };
  const big = {
    ...HEAD,
    fontSize: "clamp(30px, 3.6vw, 44px)",
    lineHeight: 1,
    fontVariantNumeric: "tabular-nums"
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "blueprint",
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))"
    }
  }, /*#__PURE__*/React.createElement(Corners, null), /*#__PURE__*/React.createElement("div", {
    style: {
      ...cell,
      borderLeft: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: KICK
  }, "Tokens spent"), /*#__PURE__*/React.createElement("span", {
    style: {
      ...big,
      color: stColor(b.status)
    }
  }, fmtFull(b.tokens)), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13,
      color: "var(--muted)"
    }
  }, "of 200,000")), /*#__PURE__*/React.createElement("div", {
    style: cell
  }, /*#__PURE__*/React.createElement("span", {
    style: KICK
  }, "Burning"), /*#__PURE__*/React.createElement("span", {
    style: big
  }, b.rate > 50 ? fmtTok(b.rate) + "/s" : "0/s"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13,
      color: "var(--muted)"
    }
  }, b.eta ? "Out in ~" + fmtDur(b.eta) : "Idle")), /*#__PURE__*/React.createElement("div", {
    style: cell
  }, /*#__PURE__*/React.createElement("span", {
    style: KICK
  }, "Window"), /*#__PURE__*/React.createElement("span", {
    style: big
  }, fmtDur(b.resetIn)), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13,
      color: "var(--muted)"
    }
  }, "until it resets")));
}
function DirB({
  b
}) {
  const [drop, setDrop] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    "data-theme": "dark",
    "data-status": "signal",
    style: {
      background: "var(--color-bg)",
      color: "var(--color-text)",
      minHeight: "100vh"
    }
  }, /*#__PURE__*/React.createElement(TopBar, {
    b: b,
    open: drop,
    onToggle: () => setDrop(d => !d)
  }), drop && /*#__PURE__*/React.createElement("div", {
    style: {
      position: "fixed",
      top: 40,
      right: 16,
      zIndex: 60
    }
  }, /*#__PURE__*/React.createElement(PagePopover, {
    b: b,
    dark: true
  })), /*#__PURE__*/React.createElement(Rail, {
    b: b
  }), /*#__PURE__*/React.createElement("div", {
    "aria-hidden": "true",
    style: {
      position: "fixed",
      right: "-1vw",
      bottom: "-7vw",
      zIndex: 0,
      pointerEvents: "none",
      ...HEAD,
      fontSize: "40vw",
      lineHeight: 0.8,
      fontVariantNumeric: "tabular-nums",
      color: "transparent",
      WebkitTextStroke: "1px color-mix(in srgb, " + stColor(b.status) + " 50%, transparent)",
      transition: "-webkit-text-stroke-color 300ms"
    }
  }, b.pct), /*#__PURE__*/React.createElement("div", {
    style: {
      marginLeft: 76,
      position: "relative",
      zIndex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 980,
      padding: "0 clamp(20px, 5vw, 64px)"
    }
  }, /*#__PURE__*/React.createElement("section", {
    "data-screen-label": "Hero",
    style: {
      padding: "clamp(48px, 8vw, 96px) 0 24px",
      display: "flex",
      flexDirection: "column",
      gap: 32
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: KICK
  }, "GNOME Shell extension · Fedora and Debian/Ubuntu" + " · " + b.title), /*#__PURE__*/React.createElement("h1", {
    style: {
      ...HEAD,
      fontSize: "clamp(80px, 14vw, 220px)",
      lineHeight: 0.82,
      margin: 0,
      letterSpacing: "-0.015em"
    }
  }, "Tokens", /*#__PURE__*/React.createElement("br", null), "go ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: stColor(b.status),
      transition: "color 300ms"
    }
  }, "brrr.")), /*#__PURE__*/React.createElement(Readout, {
    b: b
  }), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 20,
      lineHeight: 1.45,
      maxWidth: 600,
      textWrap: "pretty"
    }
  }, HERO_SUB), /*#__PURE__*/React.createElement(HeroButtons, null), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 14,
      color: "var(--muted)",
      maxWidth: 600
    }
  }, "The rail on the left is this page's meter: 200,000 tokens per 5-minute window, spent by scrolling, clicking and copying. The tick marks even pace.")), /*#__PURE__*/React.createElement(Sections, {
    b: b,
    dark: true
  }))));
}
Object.assign(window, {
  DirA,
  DirB
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "site/Directions.jsx", error: String((e && e.message) || e) }); }

// site/Shared.jsx
try { (() => {
const DS = window.AIUsageDesignSystem_480680;
const {
  ExtPopover,
  ExtHeader,
  ExtSection,
  ExtMeterRow,
  ExtFooter,
  ExtButton,
  ExtStats,
  ExtFilterChips,
  ExtPanelIndicator,
  ExtIcon
} = DS;
const HEAD = {
  fontFamily: "var(--font-heading)",
  fontWeight: 600
};
const KICK = {
  ...HEAD,
  fontSize: 12,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: "var(--muted)"
};
const MONO = {
  fontFamily: "ui-monospace, 'JetBrains Mono', 'DejaVu Sans Mono', monospace",
  fontSize: 13
};
const stColor = s => "var(--st-" + s + ")";
const Corners = () => /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("i", {
  className: "corner tl"
}), /*#__PURE__*/React.createElement("i", {
  className: "corner tr"
}), /*#__PURE__*/React.createElement("i", {
  className: "corner bl"
}), /*#__PURE__*/React.createElement("i", {
  className: "corner br"
}));
const goTo = id => {
  const el = document.getElementById(id);
  if (el) window.scrollTo({
    top: el.getBoundingClientRect().top + scrollY - 50,
    behavior: "smooth"
  });
};
function TopBar({
  b,
  onToggle,
  open
}) {
  const [clock, setClock] = React.useState(() => new Date());
  React.useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 15000);
    return () => clearInterval(t);
  }, []);
  const date = clock.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric"
  }) + " " + clock.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit"
  });
  const urgent = b.status === "crit";
  return /*#__PURE__*/React.createElement("div", {
    "data-theme": "light",
    style: {
      position: "sticky",
      top: 0,
      zIndex: 50,
      height: 30,
      background: "var(--topbar-bg)",
      display: "flex",
      alignItems: "center",
      padding: "0 12px",
      gap: 14,
      color: "var(--color-neutral-100)",
      fontSize: 13
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600
    }
  }, "Activities"), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      textAlign: "center",
      fontWeight: 600
    }
  }, date), b.brrr && /*#__PURE__*/React.createElement("span", {
    className: "tgb-brrr",
    style: {
      ...HEAD,
      fontSize: 13,
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      color: "var(--indicator-dot)"
    }
  }, "brrr"), /*#__PURE__*/React.createElement("button", {
    onClick: onToggle,
    title: "This page's usage",
    style: {
      display: "flex",
      border: 0,
      padding: 0,
      background: open ? "color-mix(in srgb, var(--color-neutral-100) 14%, transparent)" : "transparent",
      cursor: "pointer"
    },
    className: b.brrr ? "tgb-shake" : ""
  }, /*#__PURE__*/React.createElement(ExtPanelIndicator, {
    variant: urgent ? "quiet" : "tightest",
    urgent: urgent,
    name: "This page",
    value: b.limited ? "out" : b.eta ? "~" + fmtDur(b.eta) : b.pct + "%",
    dot: b.status === "warn"
  })), /*#__PURE__*/React.createElement(ExtIcon, {
    name: "wifi",
    size: 15
  }), /*#__PURE__*/React.createElement(ExtIcon, {
    name: "battery",
    size: 15
  }));
}
function PagePopover({
  b,
  dark
}) {
  return /*#__PURE__*/React.createElement(ExtPopover, {
    dark: dark,
    signal: true
  }, /*#__PURE__*/React.createElement(ExtHeader, {
    kicker: "This page",
    meta: "5-minute window",
    title: b.title,
    sub: b.sub
  }), /*#__PURE__*/React.createElement(ExtSection, null, /*#__PURE__*/React.createElement(ExtMeterRow, {
    label: "Tokens go brrr",
    tag: "tightest",
    value: b.pct,
    elapsed: b.elapsedPct,
    status: b.status,
    showPace: true,
    sub: b.rate > 50 ? "Burning " + fmtTok(b.rate) + " tokens/s" : "Idle · even pace marked by the tick"
  })), /*#__PURE__*/React.createElement(ExtSection, {
    label: "Spent on"
  }, b.parts.map(p => /*#__PURE__*/React.createElement(ExtMeterRow, {
    key: p.key,
    label: p.label,
    value: p.value,
    status: statusOf(p.value),
    sub: p.sub,
    muted: p.value === 0
  }))), /*#__PURE__*/React.createElement(ExtFooter, {
    text: b.limited ? "Rate limited" : "Updated just now",
    actionLabel: "Reset window",
    onAction: b.reset,
    showSettings: false
  }));
}
function SectionHead({
  id,
  n,
  kicker,
  title,
  b
}) {
  const ref = React.useRef(null);
  const [cost, setCost] = React.useState(0);
  React.useEffect(() => {
    const sec = ref.current && ref.current.parentElement;
    if (!sec) return;
    const m = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      setCost(sec.offsetHeight * 0.82 * LIMIT / Math.max(600, max));
    };
    m();
    const ro = new ResizeObserver(m);
    ro.observe(sec);
    ro.observe(document.body);
    return () => ro.disconnect();
  }, []);
  return /*#__PURE__*/React.createElement("div", {
    ref: ref,
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10,
      marginBottom: 28
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      gap: 16,
      borderTop: "1px solid var(--color-divider)",
      paddingTop: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: KICK
  }, n + " · " + kicker), /*#__PURE__*/React.createElement("span", {
    style: {
      ...KICK,
      fontVariantNumeric: "tabular-nums"
    }
  }, "Costs ~" + fmtTok(cost) + " to scroll")), /*#__PURE__*/React.createElement("h2", {
    style: {
      ...HEAD,
      fontSize: "clamp(34px, 4.4vw, 52px)",
      lineHeight: 1.02,
      margin: 0,
      textWrap: "balance"
    }
  }, title));
}
const GALLERY = [{
  value: "landing",
  label: "Insight",
  nav: {
    screen: "landing",
    ins: "act",
    fromEarlier: false
  },
  cap: "Two or three times a day the popover opens on one written insight. The daemon decides whether anything is worth interrupting for."
}, {
  value: "list",
  label: "Agents",
  nav: {
    screen: "list"
  },
  cap: "Every provider with its limit meter. The tick marks even pace, and the window picker sets 5-hour, weekly or monthly for every row."
}, {
  value: "detail",
  label: "Provider",
  nav: {
    screen: "detail",
    prov: "claude"
  },
  cap: "Each window with its reset, and the terminal sessions running against it. Focus raises the terminal."
}, {
  value: "sessions",
  label: "Sessions",
  nav: {
    screen: "sessions",
    prov: "cursor",
    filter: "active"
  },
  cap: "Running and paused sessions. A session suspended with Ctrl+Z spends nothing, so it is counted apart."
}, {
  value: "guide",
  label: "Guide",
  nav: {
    screen: "guide"
  },
  cap: "Healthy under 70%, caution to 89%, critical from 90%. The percentage is always written beside the bar."
}];
function Gallery({
  dark
}) {
  const [nav, setNav] = React.useState(GALLERY[0].nav);
  const [win, setWin] = React.useState("rolling");
  const go = patch => setNav(n => ({
    ...n,
    ...patch
  }));
  const tab = nav.screen === "earlier" ? "landing" : nav.screen;
  const cur = GALLERY.find(g => g.value === tab) || GALLERY[0];
  const W = window;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 40,
      alignItems: "flex-start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "1 1 240px",
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(ExtFilterChips, {
    options: GALLERY.map(g => ({
      value: g.value,
      label: g.label
    })),
    value: tab,
    onChange: v => setNav(GALLERY.find(g => g.value === v).nav)
  }), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 16,
      maxWidth: 420,
      textWrap: "pretty"
    }
  }, cur.cap), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 13,
      color: "var(--muted)"
    }
  }, "The popover is live. Rows, Back and Focus work.")), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "0 0 auto",
      padding: 6
    }
  }, /*#__PURE__*/React.createElement(ExtPopover, {
    dark: dark,
    signal: true
  }, nav.screen === "landing" && /*#__PURE__*/React.createElement(W.LandingScreen, {
    insId: nav.ins || "act",
    fromEarlier: nav.fromEarlier,
    go: go
  }), nav.screen === "earlier" && /*#__PURE__*/React.createElement(W.EarlierScreen, {
    go: go
  }), nav.screen === "list" && /*#__PURE__*/React.createElement(W.ListScreen, {
    go: go,
    showPace: true,
    win: win,
    setWin: setWin
  }), nav.screen === "detail" && /*#__PURE__*/React.createElement(W.DetailScreen, {
    provId: nav.prov,
    go: go,
    showPace: true
  }), nav.screen === "sessions" && /*#__PURE__*/React.createElement(W.SessionsScreen, {
    provId: nav.prov,
    filter: nav.filter || "active",
    go: go
  }), nav.screen === "guide" && /*#__PURE__*/React.createElement(W.GuideScreen, {
    go: go
  }), nav.screen === "about" && /*#__PURE__*/React.createElement(W.AboutScreen, {
    go: go
  }))));
}
function Privacy() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
      gap: "0 32px"
    }
  }, SITE.privacy.map(([t, d]) => /*#__PURE__*/React.createElement("div", {
    key: t,
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 6,
      padding: "16px 0",
      borderTop: "1px solid var(--color-divider)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 15,
      fontWeight: 600
    }
  }, t), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14,
      color: "var(--muted)",
      textWrap: "pretty"
    }
  }, d))));
}
function Faq() {
  const [open, setOpen] = React.useState(0);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column"
    }
  }, SITE.faq.map(([q, a], i) => /*#__PURE__*/React.createElement("div", {
    key: q,
    style: {
      borderTop: "1px solid var(--color-divider)"
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "ext-row-hover",
    onClick: () => setOpen(open === i ? -1 : i),
    style: {
      width: "100%",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      gap: 16,
      padding: "14px 0",
      border: 0,
      background: "transparent",
      color: "var(--color-text)",
      textAlign: "left",
      fontFamily: "var(--font-body)",
      fontSize: 16,
      fontWeight: 600
    }
  }, /*#__PURE__*/React.createElement("span", null, q), /*#__PURE__*/React.createElement("span", {
    style: {
      ...HEAD,
      fontSize: 12,
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      color: "var(--muted)",
      flex: "none"
    }
  }, open === i ? "Close" : "−1.2k")), open === i && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: "0 0 16px",
      fontSize: 15,
      maxWidth: 620,
      color: "var(--muted)",
      textWrap: "pretty"
    }
  }, a))));
}
function SiteFooter() {
  return /*#__PURE__*/React.createElement("footer", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      justifyContent: "space-between",
      gap: 16,
      padding: "20px 0 40px",
      borderTop: "1px solid var(--color-divider)",
      fontSize: 13,
      color: "var(--muted)"
    }
  }, /*#__PURE__*/React.createElement("span", null, "Tokens go brrr \xB7 the AI usage extension for GNOME Shell \xB7 ", /*#__PURE__*/React.createElement("a", {
    href: REL_URL,
    target: "_blank"
  }, "Releases")), /*#__PURE__*/React.createElement("span", null, "Provider names and marks belong to their owners and are used only to identify each service."));
}
function LimitModal({
  b,
  dark,
  onDismiss
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "fixed",
      inset: 0,
      zIndex: 100,
      background: "color-mix(in srgb, #1d1f20 55%, transparent)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 20
    }
  }, /*#__PURE__*/React.createElement(ExtPopover, {
    dark: dark,
    signal: true
  }, /*#__PURE__*/React.createElement(ExtHeader, {
    kicker: "429 \xB7 Rate limited",
    meta: "Resets in " + fmtDur(b.resetIn),
    title: "This page is out of tokens.",
    sub: "It spent its 5-minute window on scrolling, clicking and copying. Your real tools are probably fine. The extension can tell you which."
  }), /*#__PURE__*/React.createElement(ExtStats, {
    items: [{
      value: "200k",
      label: "tokens spent"
    }, {
      value: String(b.w.clicks),
      label: "clicks"
    }, {
      value: fmtDur(b.resetIn),
      label: "until reset"
    }]
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      padding: "16px 18px 18px"
    }
  }, /*#__PURE__*/React.createElement(ExtButton, {
    variant: "primary",
    block: true,
    label: "Download the extension",
    onClick: () => {
      onDismiss();
      setTimeout(() => goTo("download"), 50);
    }
  }), /*#__PURE__*/React.createElement(ExtButton, {
    variant: "secondary",
    label: "Reset window",
    onClick: b.reset
  }))));
}
Object.assign(window, {
  HEAD,
  KICK,
  MONO,
  stColor,
  Corners,
  goTo,
  TopBar,
  PagePopover,
  SectionHead,
  Gallery,
  Privacy,
  Faq,
  SiteFooter,
  LimitModal
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "site/Shared.jsx", error: String((e && e.message) || e) }); }

// site/burn.jsx
try { (() => {
const LIMIT = 200000;
const WINDOW_S = 300;
const BURN_KEY = "tgb-burn-v1";
const CLICK_COST = 1200;
const COPY_COST = 4000;
const fmtTok = n => n >= 1000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1) + "k" : String(Math.round(n));
const fmtFull = n => Math.round(n).toLocaleString("en-US");
const fmtDur = s => {
  s = Math.max(0, Math.round(s));
  if (s < 60) return s + "s";
  const m = Math.floor(s / 60),
    r = s % 60;
  return r ? m + "m " + r + "s" : m + "m";
};
const statusOf = pct => pct >= 90 ? "crit" : pct >= 70 ? "warn" : "ok";
function freshWindow() {
  return {
    start: Date.now(),
    scroll: 0,
    click: 0,
    copy: 0,
    clicks: 0,
    copies: 0
  };
}
function loadWindow() {
  try {
    const w = JSON.parse(localStorage.getItem(BURN_KEY));
    if (w && Date.now() - w.start < WINDOW_S * 1000) return w;
  } catch (e) {}
  return freshWindow();
}
function useBurn(mult = 1) {
  const [w, setW] = React.useState(loadWindow);
  const [now, setNow] = React.useState(Date.now());
  const wRef = React.useRef(w);
  wRef.current = w;
  const multRef = React.useRef(mult);
  multRef.current = mult;
  const samples = React.useRef([]);
  const lastY = React.useRef(window.scrollY);
  const perPx = React.useRef(1);
  const total = x => x.scroll + x.click + x.copy;
  const add = (kind, n) => setW(x => {
    if (total(x) >= LIMIT) return x;
    const room = LIMIT - total(x);
    const y = {
      ...x,
      [kind]: x[kind] + Math.min(room, n * multRef.current)
    };
    if (kind === "click") y.clicks = x.clicks + 1;
    if (kind === "copy") y.copies = x.copies + 1;
    return y;
  });
  React.useEffect(() => {
    localStorage.setItem(BURN_KEY, JSON.stringify(w));
  }, [w]);
  React.useEffect(() => {
    const measure = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      perPx.current = 0.82 * LIMIT / Math.max(600, max);
    };
    measure();
    let raf = 0,
      pending = 0;
    const onScroll = () => {
      const y = window.scrollY;
      pending += Math.abs(y - lastY.current);
      lastY.current = y;
      if (!raf) raf = requestAnimationFrame(() => {
        raf = 0;
        const px = pending;
        pending = 0;
        add("scroll", px * perPx.current);
      });
    };
    const onClick = () => add("click", CLICK_COST);
    const ro = new ResizeObserver(measure);
    ro.observe(document.body);
    addEventListener("scroll", onScroll, {
      passive: true
    });
    addEventListener("click", onClick, true);
    const tick = setInterval(() => {
      const t = Date.now();
      setNow(t);
      if (t - wRef.current.start >= WINDOW_S * 1000) {
        samples.current = [];
        setW(freshWindow());
      }
    }, 500);
    return () => {
      removeEventListener("scroll", onScroll);
      removeEventListener("click", onClick, true);
      clearInterval(tick);
      ro.disconnect();
    };
  }, []);
  const tokens = total(w);
  samples.current.push({
    t: now,
    v: tokens
  });
  samples.current = samples.current.filter(s => now - s.t <= 4000);
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
  if (limited) title = "This page is out of tokens.";else if (status === "crit") title = eta ? "This page runs out in ~" + fmtDur(eta) + "." : "This page is at " + pct + "%.";else if (status === "warn") title = pct > elapsedPct ? "This page is ahead of pace." : "This page is getting close.";else if (pct < 8) title = "This page has plenty of room.";else title = pct > elapsedPct ? "This page is ahead of pace." : "This page is under pace.";
  const sub = fmtFull(tokens) + " of 200,000 tokens · resets in " + fmtDur(resetIn);
  const pctOf = n => Math.round(n / LIMIT * 100);
  const parts = [{
    key: "scroll",
    label: "Scrolling",
    value: pctOf(w.scroll),
    sub: fmtTok(w.scroll) + " tokens · scrolling back up is not refunded"
  }, {
    key: "click",
    label: "Clicks",
    value: pctOf(w.click),
    sub: w.clicks + (w.clicks === 1 ? " click" : " clicks") + " · " + fmtTok(CLICK_COST) + " each"
  }, {
    key: "copy",
    label: "Copying",
    value: pctOf(w.copy),
    sub: w.copies + (w.copies === 1 ? " command" : " commands") + " · " + fmtTok(COPY_COST) + " each"
  }];
  return {
    tokens,
    pct,
    status,
    elapsedPct,
    resetIn,
    rate,
    eta,
    limited,
    title,
    sub,
    parts,
    w,
    perPx: perPx.current,
    brrr: rate > 6000,
    spendCopy: () => add("copy", COPY_COST),
    reset: () => {
      samples.current = [];
      setW(freshWindow());
      window.scrollTo({
        top: 0
      });
      lastY.current = 0;
    }
  };
}
const SITE = {
  privacy: [["No cookies, no scraping", "Each provider reuses a login already on disk: Cursor's IDE state, Claude Code's OAuth file, OpenCode's API key."], ["Read, never written", "Claude Code owns its token refresh. The file is opened read-only, so the daemon cannot sign you out of the CLI."], ["The extension holds nothing", "It has no credentials and makes no network calls. It reads state from the daemon over the session bus."], ["History stays in ~/.local", "Polls and the usage ledger are kept in ~/.local/share/cursor-spend-monitor for 90 days. Set history_days to 0 to stop recording."], ["Only numbers travel", "Insight wording is a template unless you turn on llm_notifications. When it is on, no transcript text, prompts or file contents are sent."]],
  faq: [["Which tools does it track?", "Cursor, Claude Code, OpenCode and Codex report their own limits. Pi is a harness, so it borrows the meters of whichever account its sessions bill to."], ["Why does a row sometimes show no bar?", "xAI publishes no usage endpoint and Cline reports a credit balance, not a window. An empty bar at 0% would read as plenty left, so the row shows its sessions and no percentage."], ["Does a paused session count?", "No. A session suspended with Ctrl+Z spends nothing until you resume it, so it stays out of the top-bar count and shows as paused in the provider's detail screen."], ["Does opening the popover hit five APIs every time?", "It asks for a refresh, and the daemon drops the request if it polled in the last 60 seconds. Anthropic returns 429 on its usage route long before any quota is spent."], ["Can I use it from a status bar or a script?", "Yes. status prints the published state in about 0.1s with no network call. check exits non-zero when quota is low, and best names the provider with the most left."], ["Which GNOME versions?", "GNOME Shell 45 or newer. Log out and back in after installing so the shell picks up the extension."], ["Windows or macOS?", "Both are coming. Fedora and Debian/Ubuntu packages are available now."]]
};
Object.assign(window, {
  LIMIT,
  WINDOW_S,
  CLICK_COST,
  COPY_COST,
  fmtTok,
  fmtFull,
  fmtDur,
  statusOf,
  useBurn,
  SITE
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "site/burn.jsx", error: String((e && e.message) || e) }); }

// site/releases.jsx
try { (() => {
const REL_REPO = "fredrickmakoffu/cursor-spend-monitor-releases";
const REL_URL = "https://github.com/" + REL_REPO + "/releases";
const PLATFORMS = [{
  id: "fedora",
  name: "Fedora",
  kind: "RPM · GNOME",
  ext: ".rpm",
  cmd: f => "sudo dnf install ./" + f
}, {
  id: "debian",
  name: "Debian / Ubuntu",
  kind: "DEB · GNOME",
  ext: ".deb",
  cmd: f => "sudo apt install ./" + f
}, {
  id: "windows",
  name: "Windows",
  kind: "Installer"
}, {
  id: "macos",
  name: "macOS",
  kind: "Disk image"
}];
const FALLBACK_RELEASES = [{
  tag: "v0.6.1",
  date: "2026-10-09",
  url: REL_URL + "/tag/v0.6.1",
  notes: [],
  assets: [{
    name: "cursor-spend-monitor-0.6.1-1.fc44.noarch.rpm",
    size: 257000,
    url: REL_URL + "/download/v0.6.1/cursor-spend-monitor-0.6.1-1.fc44.noarch.rpm",
    sha: null
  }, {
    name: "cursor-spend-monitor_0.6.1_all.deb",
    size: 106000,
    url: REL_URL + "/download/v0.6.1/cursor-spend-monitor_0.6.1_all.deb",
    sha: null
  }]
}];
const fmtSize = b => b >= 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.round(b / 1000) + " KB";
const parseNotes = body => (body || "").split(/\r?\n/).map(l => l.trim()).filter(l => /^[-*] /.test(l)).map(l => l.slice(2).replace(/\*\*|`/g, ""));
function useReleases() {
  const [rel, setRel] = React.useState({
    list: FALLBACK_RELEASES,
    live: false
  });
  React.useEffect(() => {
    fetch("https://api.github.com/repos/" + REL_REPO + "/releases?per_page=10").then(r => r.ok ? r.json() : Promise.reject()).then(data => {
      const list = data.filter(r => !r.draft).map(r => ({
        tag: r.tag_name,
        date: (r.published_at || "").slice(0, 10),
        url: r.html_url,
        notes: parseNotes(r.body),
        prerelease: r.prerelease,
        assets: (r.assets || []).map(a => ({
          name: a.name,
          size: a.size,
          url: a.browser_download_url,
          sha: a.digest ? a.digest.replace(/^sha256:/, "") : null
        }))
      }));
      if (list.length) setRel({
        list,
        live: true
      });
    }).catch(() => {});
  }, []);
  const latest = rel.list.find(r => !r.prerelease) || rel.list[0];
  return {
    ...rel,
    latest
  };
}
function CopyLine({
  text,
  b,
  dense
}) {
  const [done, setDone] = React.useState(false);
  const copy = () => {
    try {
      navigator.clipboard.writeText(text);
    } catch (e) {}
    b.spendCopy();
    setDone(true);
    setTimeout(() => setDone(false), 1600);
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-start",
      gap: 8,
      border: "1px solid var(--color-divider)",
      padding: dense ? "8px 10px" : "10px 12px",
      background: "var(--color-surface, transparent)"
    }
  }, /*#__PURE__*/React.createElement("code", {
    style: {
      ...MONO,
      flex: 1,
      minWidth: 0,
      overflowWrap: "anywhere",
      lineHeight: 1.5
    }
  }, text), /*#__PURE__*/React.createElement("button", {
    onClick: copy,
    className: "ext-row-hover",
    style: {
      flex: "none",
      border: 0,
      background: "transparent",
      padding: "2px 4px",
      cursor: "pointer",
      ...HEAD,
      fontSize: 12,
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      color: done ? "var(--st-ok)" : "var(--muted)"
    }
  }, done ? "Copied −4k" : "Copy"));
}
function PlatformCard({
  p,
  asset,
  b
}) {
  const [sha, setSha] = React.useState(false);
  const soon = !asset;
  return /*#__PURE__*/React.createElement("div", {
    className: "blueprint",
    style: {
      padding: 20,
      display: "flex",
      flexDirection: "column",
      gap: 14,
      minWidth: 0,
      opacity: soon ? 0.75 : 1
    }
  }, /*#__PURE__*/React.createElement(Corners, null), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      ...HEAD,
      fontSize: 24,
      textTransform: "uppercase",
      letterSpacing: "0.02em"
    }
  }, p.name), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13,
      color: "var(--muted)"
    }
  }, p.kind + (asset ? " · " + fmtSize(asset.size) : ""))), soon ? /*#__PURE__*/React.createElement("div", {
    style: {
      border: "1px dashed var(--color-divider)",
      padding: "11px 12px",
      textAlign: "center",
      fontSize: 14,
      fontWeight: 600,
      color: "var(--muted)"
    }
  }, "Coming soon") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(ExtButton, {
    variant: "primary",
    block: true,
    label: "Download " + p.ext.slice(1),
    onClick: () => window.open(asset.url, "_blank")
  }), /*#__PURE__*/React.createElement(CopyLine, {
    text: p.cmd(asset.name),
    b: b,
    dense: true
  }), /*#__PURE__*/React.createElement("button", {
    onClick: () => setSha(!sha),
    style: {
      alignSelf: "flex-start",
      border: 0,
      background: "transparent",
      padding: 0,
      cursor: "pointer",
      fontSize: 13,
      color: "var(--muted)",
      fontFamily: "var(--font-body)"
    }
  }, (sha ? "▾ " : "▸ ") + "SHA-256"), sha && /*#__PURE__*/React.createElement("code", {
    style: {
      ...MONO,
      fontSize: 12,
      overflowWrap: "anywhere",
      color: "var(--muted)",
      marginTop: -6
    }
  }, asset.sha || "Listed in SHA256SUMS on the release page.")));
}
function Downloads({
  b,
  rel
}) {
  const r = rel.latest;
  const find = ext => ext && r.assets.find(a => a.name.endsWith(ext));
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 28
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14,
      color: "var(--muted)"
    }
  }, "Latest: " + r.tag + " · " + r.date), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
      gap: 16
    }
  }, PLATFORMS.map(p => /*#__PURE__*/React.createElement(PlatformCard, {
    key: p.id,
    p: p,
    asset: find(p.ext),
    b: b
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8,
      borderTop: "1px solid var(--color-divider)",
      paddingTop: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: KICK
  }, "After installing \xB7 1"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 15
    }
  }, "Log out and back in so GNOME Shell loads the extension. Needs GNOME Shell 45 or newer.")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8,
      borderTop: "1px solid var(--color-divider)",
      paddingTop: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: KICK
  }, "After installing \xB7 2"), /*#__PURE__*/React.createElement(CopyLine, {
    text: "cursor-spend-monitor setup",
    b: b
  }))), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 13,
      color: "var(--muted)"
    }
  }, "Always verify a download against its SHA-256 before installing."));
}
function Releases({
  rel
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column"
    }
  }, rel.list.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: r.tag,
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 200px), 1fr))",
      gap: "10px 28px",
      padding: "18px 0",
      borderTop: "1px solid var(--color-divider)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      ...HEAD,
      fontSize: 26,
      display: "flex",
      alignItems: "baseline",
      gap: 10
    }
  }, r.tag, i === 0 && /*#__PURE__*/React.createElement("span", {
    style: {
      ...KICK,
      color: "var(--st-ok)"
    }
  }, "Latest")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13,
      color: "var(--muted)"
    }
  }, r.date)), /*#__PURE__*/React.createElement("div", {
    style: {
      gridColumn: "span 2",
      display: "flex",
      flexDirection: "column",
      gap: 10,
      minWidth: 0
    }
  }, r.notes.length > 0 && /*#__PURE__*/React.createElement("ul", {
    style: {
      margin: 0,
      padding: 0,
      listStyle: "none",
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, r.notes.map(n => /*#__PURE__*/React.createElement("li", {
    key: n,
    style: {
      fontSize: 15,
      textWrap: "pretty"
    }
  }, n))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: "6px 18px"
    }
  }, r.assets.map(a => /*#__PURE__*/React.createElement("a", {
    key: a.name,
    href: a.url,
    style: {
      ...MONO,
      fontSize: 12
    }
  }, a.name)), /*#__PURE__*/React.createElement("a", {
    href: r.url,
    target: "_blank",
    style: {
      fontSize: 13
    }
  }, "Release page"))))), /*#__PURE__*/React.createElement("a", {
    href: REL_URL,
    target: "_blank",
    style: {
      fontSize: 14,
      paddingTop: 14,
      borderTop: "1px solid var(--color-divider)"
    }
  }, "All releases on GitHub"));
}
const FACTS = [["In the top bar", "One indicator shows the tool closest to its limit, and how long it has left at the current pace."], ["In the popover", "Every provider's 5-hour, weekly or monthly window, with the terminal sessions spending against it."], ["Behind it", "A local daemon reads the logins your tools already keep on disk, then polls each provider's own usage route."]];
function Facts() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
      gap: "0 32px",
      marginBottom: 40
    }
  }, FACTS.map(([t, d]) => /*#__PURE__*/React.createElement("div", {
    key: t,
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 6,
      padding: "14px 0",
      borderTop: "1px solid var(--color-divider)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 15,
      fontWeight: 600
    }
  }, t), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14,
      color: "var(--muted)",
      textWrap: "pretty"
    }
  }, d))));
}
Object.assign(window, {
  REL_URL,
  useReleases,
  Downloads,
  Releases,
  Facts
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "site/releases.jsx", error: String((e && e.message) || e) }); }

// site/tweaks-panel.jsx
try { (() => {
// @ds-adherence-ignore -- omelette starter scaffold (raw elements/hex/px by design)
// Copied omelette starter. Re-running copy_starter_component with this kind overwrites this file with the latest version (page content is unaffected).

/* BEGIN USAGE */
// tweaks-panel.jsx
// Reusable Tweaks shell + form-control helpers.
// Exports (to window): useTweaks, TweaksPanel, TweakSection, TweakRow, TweakSlider,
//   TweakToggle, TweakRadio, TweakSelect, TweakText, TweakNumber, TweakColor, TweakButton.
//
// Owns the host protocol (listens for __activate_edit_mode / __deactivate_edit_mode,
// posts __edit_mode_available / __edit_mode_set_keys / __edit_mode_dismissed) so
// individual prototypes don't re-roll it. Ships a consistent set of controls so you
// don't hand-draw <input type="range">, segmented radios, steppers, etc.
//
// Usage (in an HTML file that loads React + Babel):
//
//   const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
//     "primaryColor": "#D97757",
//     "palette": ["#D97757", "#29261b", "#f6f4ef"],
//     "fontSize": 16,
//     "density": "regular",
//     "dark": false
//   }/*EDITMODE-END*/;
//
//   function App() {
//     const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
//     return (
//       <div style={{ fontSize: t.fontSize, color: t.primaryColor }}>
//         Hello
//         <TweaksPanel>
//           <TweakSection label="Typography" />
//           <TweakSlider label="Font size" value={t.fontSize} min={10} max={32} unit="px"
//                        onChange={(v) => setTweak('fontSize', v)} />
//           <TweakRadio  label="Density" value={t.density}
//                        options={['compact', 'regular', 'comfy']}
//                        onChange={(v) => setTweak('density', v)} />
//           <TweakSection label="Theme" />
//           <TweakColor  label="Primary" value={t.primaryColor}
//                        options={['#D97757', '#2A6FDB', '#1F8A5B', '#7A5AE0']}
//                        onChange={(v) => setTweak('primaryColor', v)} />
//           <TweakColor  label="Palette" value={t.palette}
//                        options={[['#D97757', '#29261b', '#f6f4ef'],
//                                  ['#475569', '#0f172a', '#f1f5f9']]}
//                        onChange={(v) => setTweak('palette', v)} />
//           <TweakToggle label="Dark mode" value={t.dark}
//                        onChange={(v) => setTweak('dark', v)} />
//         </TweaksPanel>
//       </div>
//     );
//   }
//
// TweakRadio is the segmented control for 2–3 short options (auto-falls-back to
// TweakSelect past ~16/~10 chars per label); reach for TweakSelect directly when
// options are many or long. For color tweaks always curate 3-4 options rather than
// a free picker; an option can also be a whole 2–5 color palette (the stored value
// is the array). The Tweak* controls are a floor, not a ceiling — build custom
// controls inside the panel if a tweak calls for UI they don't cover.
/* END USAGE */
// ─────────────────────────────────────────────────────────────────────────────

const __TWEAKS_STYLE = `
  .twk-panel{position:fixed;right:16px;bottom:16px;z-index:2147483646;width:280px;
    max-height:calc(100vh - 32px);display:flex;flex-direction:column;
    transform:scale(var(--dc-inv-zoom,1));transform-origin:bottom right;
    background:rgba(250,249,247,.78);color:#29261b;
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:14px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
    font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:10px 8px 10px 14px;cursor:move;user-select:none}
  .twk-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
    width:22px;height:22px;border-radius:6px;cursor:default;font-size:13px;line-height:1}
  .twk-x:hover{background:rgba(0,0,0,.06);color:#29261b}
  .twk-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
    overflow-y:auto;overflow-x:hidden;min-height:0;
    scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.15) transparent}
  .twk-body::-webkit-scrollbar{width:8px}
  .twk-body::-webkit-scrollbar-track{background:transparent;margin:2px}
  .twk-body::-webkit-scrollbar-thumb{background:rgba(0,0,0,.15);border-radius:4px;
    border:2px solid transparent;background-clip:content-box}
  .twk-body::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,.25);
    border:2px solid transparent;background-clip:content-box}
  .twk-row{display:flex;flex-direction:column;gap:5px}
  .twk-row-h{flex-direction:row;align-items:center;justify-content:space-between;gap:10px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;
    color:rgba(41,38,27,.72)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:rgba(41,38,27,.5);font-variant-numeric:tabular-nums}

  .twk-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    color:rgba(41,38,27,.45);padding:10px 0 0}
  .twk-sect:first-child{padding-top:0}

  .twk-field{appearance:none;box-sizing:border-box;width:100%;min-width:0;height:26px;padding:0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;
    background:rgba(255,255,255,.6);color:inherit;font:inherit;outline:none}
  .twk-field:focus{border-color:rgba(0,0,0,.25);background:rgba(255,255,255,.85)}
  select.twk-field{padding-right:22px;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='rgba(0,0,0,.5)' d='M0 0h10L5 6z'/></svg>");
    background-repeat:no-repeat;background-position:right 8px center}

  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:6px 0;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
    width:14px;height:14px;border-radius:50%;background:#fff;
    border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}
  .twk-slider::-moz-range-thumb{width:14px;height:14px;border-radius:50%;
    background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}

  .twk-seg{position:relative;display:flex;padding:2px;border-radius:8px;
    background:rgba(0,0,0,.06);user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:6px;
    background:rgba(255,255,255,.9);box-shadow:0 1px 2px rgba(0,0,0,.12);
    transition:left .15s cubic-bezier(.3,.7,.4,1),width .15s}
  .twk-seg.dragging .twk-seg-thumb{transition:none}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;
    background:transparent;color:inherit;font:inherit;font-weight:500;min-height:22px;
    border-radius:6px;cursor:default;padding:4px 6px;line-height:1.2;
    overflow-wrap:anywhere}

  .twk-toggle{position:relative;width:32px;height:18px;border:0;border-radius:999px;
    background:rgba(0,0,0,.15);transition:background .15s;cursor:default;padding:0}
  .twk-toggle[data-on="1"]{background:#34c759}
  .twk-toggle i{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
    background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
  .twk-toggle[data-on="1"] i{transform:translateX(14px)}

  .twk-num{display:flex;align-items:center;box-sizing:border-box;min-width:0;height:26px;padding:0 0 0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;background:rgba(255,255,255,.6)}
  .twk-num-lbl{font-weight:500;color:rgba(41,38,27,.6);cursor:ew-resize;
    user-select:none;padding-right:8px}
  .twk-num input{flex:1;min-width:0;height:100%;border:0;background:transparent;
    font:inherit;font-variant-numeric:tabular-nums;text-align:right;padding:0 8px 0 0;
    outline:none;color:inherit;-moz-appearance:textfield}
  .twk-num input::-webkit-inner-spin-button,.twk-num input::-webkit-outer-spin-button{
    -webkit-appearance:none;margin:0}
  .twk-num-unit{padding-right:8px;color:rgba(41,38,27,.45)}

  .twk-btn{appearance:none;height:26px;padding:0 12px;border:0;border-radius:7px;
    background:rgba(0,0,0,.78);color:#fff;font:inherit;font-weight:500;cursor:default}
  .twk-btn:hover{background:rgba(0,0,0,.88)}
  .twk-btn.secondary{background:rgba(0,0,0,.06);color:inherit}
  .twk-btn.secondary:hover{background:rgba(0,0,0,.1)}

  .twk-swatch{appearance:none;-webkit-appearance:none;width:56px;height:22px;
    border:.5px solid rgba(0,0,0,.1);border-radius:6px;padding:0;cursor:default;
    background:transparent;flex-shrink:0}
  .twk-swatch::-webkit-color-swatch-wrapper{padding:0}
  .twk-swatch::-webkit-color-swatch{border:0;border-radius:5.5px}
  .twk-swatch::-moz-color-swatch{border:0;border-radius:5.5px}

  .twk-chips{display:flex;gap:6px}
  .twk-chip{position:relative;appearance:none;flex:1;min-width:0;height:46px;
    padding:0;border:0;border-radius:6px;overflow:hidden;cursor:default;
    box-shadow:0 0 0 .5px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.06);
    transition:transform .12s cubic-bezier(.3,.7,.4,1),box-shadow .12s}
  .twk-chip:hover{transform:translateY(-1px);
    box-shadow:0 0 0 .5px rgba(0,0,0,.18),0 4px 10px rgba(0,0,0,.12)}
  .twk-chip[data-on="1"]{box-shadow:0 0 0 1.5px rgba(0,0,0,.85),
    0 2px 6px rgba(0,0,0,.15)}
  .twk-chip>span{position:absolute;top:0;bottom:0;right:0;width:34%;
    display:flex;flex-direction:column;box-shadow:-1px 0 0 rgba(0,0,0,.1)}
  .twk-chip>span>i{flex:1;box-shadow:0 -1px 0 rgba(0,0,0,.1)}
  .twk-chip>span>i:first-child{box-shadow:none}
  .twk-chip svg{position:absolute;top:6px;left:6px;width:13px;height:13px;
    filter:drop-shadow(0 1px 1px rgba(0,0,0,.3))}
`;

// ── useTweaks ───────────────────────────────────────────────────────────────
// Single source of truth for tweak values. setTweak persists via the host
// (__edit_mode_set_keys → host rewrites the EDITMODE block on disk).
function useTweaks(defaults) {
  const [values, setValues] = React.useState(defaults);
  // Accepts either setTweak('key', value) or setTweak({ key: value, ... }) so a
  // useState-style call doesn't write a "[object Object]" key into the persisted
  // JSON block.
  const setTweak = React.useCallback((keyOrEdits, val) => {
    const edits = typeof keyOrEdits === 'object' && keyOrEdits !== null ? keyOrEdits : {
      [keyOrEdits]: val
    };
    setValues(prev => ({
      ...prev,
      ...edits
    }));
    window.parent.postMessage({
      type: '__edit_mode_set_keys',
      edits
    }, '*');
    // Same-window signal so in-page listeners (deck-stage rail thumbnails)
    // can react — the parent message only reaches the host, not peers.
    window.dispatchEvent(new CustomEvent('tweakchange', {
      detail: edits
    }));
  }, []);
  return [values, setTweak];
}

// ── TweaksPanel ─────────────────────────────────────────────────────────────
// Floating shell. Registers the protocol listener BEFORE announcing
// availability — if the announce ran first, the host's activate could land
// before our handler exists and the toolbar toggle would silently no-op.
// The close button posts __edit_mode_dismissed so the host's toolbar toggle
// flips off in lockstep; the host echoes __deactivate_edit_mode back which
// is what actually hides the panel.
function TweaksPanel({
  title = 'Tweaks',
  children
}) {
  const [open, setOpen] = React.useState(false);
  const dragRef = React.useRef(null);
  const offsetRef = React.useRef({
    x: 16,
    y: 16
  });
  const PAD = 16;
  const clampToViewport = React.useCallback(() => {
    const panel = dragRef.current;
    if (!panel) return;
    const w = panel.offsetWidth,
      h = panel.offsetHeight;
    const maxRight = Math.max(PAD, window.innerWidth - w - PAD);
    const maxBottom = Math.max(PAD, window.innerHeight - h - PAD);
    offsetRef.current = {
      x: Math.min(maxRight, Math.max(PAD, offsetRef.current.x)),
      y: Math.min(maxBottom, Math.max(PAD, offsetRef.current.y))
    };
    panel.style.right = offsetRef.current.x + 'px';
    panel.style.bottom = offsetRef.current.y + 'px';
  }, []);
  React.useEffect(() => {
    if (!open) return;
    clampToViewport();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', clampToViewport);
      return () => window.removeEventListener('resize', clampToViewport);
    }
    const ro = new ResizeObserver(clampToViewport);
    ro.observe(document.documentElement);
    return () => ro.disconnect();
  }, [open, clampToViewport]);
  React.useEffect(() => {
    const onMsg = e => {
      const t = e?.data?.type;
      if (t === '__activate_edit_mode') setOpen(true);else if (t === '__deactivate_edit_mode') setOpen(false);
    };
    window.addEventListener('message', onMsg);
    window.parent.postMessage({
      type: '__edit_mode_available'
    }, '*');
    return () => window.removeEventListener('message', onMsg);
  }, []);
  const dismiss = () => {
    setOpen(false);
    window.parent.postMessage({
      type: '__edit_mode_dismissed'
    }, '*');
  };
  const onDragStart = e => {
    const panel = dragRef.current;
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const sx = e.clientX,
      sy = e.clientY;
    const startRight = window.innerWidth - r.right;
    const startBottom = window.innerHeight - r.bottom;
    const move = ev => {
      offsetRef.current = {
        x: startRight - (ev.clientX - sx),
        y: startBottom - (ev.clientY - sy)
      };
      clampToViewport();
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };

  // data-om-starter: inert presence marker — Claude Design's starter-usage
  // probe reads it. The closed panel renders nothing, so the marker rides
  // the <html> element as an attribute instead of a rendered node — zero
  // elements added, so page CSS (even structural selectors like
  // :nth-child) can never observe it. It records that the page WIRES a
  // tweaks panel, whether or not the panel is open. Keep this effect.
  React.useEffect(() => {
    document.documentElement.setAttribute('data-om-starter', 'tweaks-panel');
    return () => document.documentElement.removeAttribute('data-om-starter');
  }, []);
  if (!open) return null;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("style", null, __TWEAKS_STYLE), /*#__PURE__*/React.createElement("div", {
    ref: dragRef,
    className: "twk-panel",
    "data-omelette-chrome": "",
    style: {
      right: offsetRef.current.x,
      bottom: offsetRef.current.y
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-hd",
    onMouseDown: onDragStart
  }, /*#__PURE__*/React.createElement("b", null, title), /*#__PURE__*/React.createElement("button", {
    className: "twk-x",
    "aria-label": "Close tweaks",
    onMouseDown: e => e.stopPropagation(),
    onClick: dismiss
  }, "\u2715")), /*#__PURE__*/React.createElement("div", {
    className: "twk-body"
  }, children)));
}

// ── Layout helpers ──────────────────────────────────────────────────────────

function TweakSection({
  label,
  children
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "twk-sect"
  }, label), children);
}
function TweakRow({
  label,
  value,
  children,
  inline = false
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: inline ? 'twk-row twk-row-h' : 'twk-row'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label), value != null && /*#__PURE__*/React.createElement("span", {
    className: "twk-val"
  }, value)), children);
}

// ── Controls ────────────────────────────────────────────────────────────────

function TweakSlider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  unit = '',
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label,
    value: `${value}${unit}`
  }, /*#__PURE__*/React.createElement("input", {
    type: "range",
    className: "twk-slider",
    min: min,
    max: max,
    step: step,
    value: value,
    onChange: e => onChange(Number(e.target.value))
  }));
}
function TweakToggle({
  label,
  value,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-row twk-row-h"
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "twk-toggle",
    "data-on": value ? '1' : '0',
    role: "switch",
    "aria-checked": !!value,
    onClick: () => onChange(!value)
  }, /*#__PURE__*/React.createElement("i", null)));
}
function TweakRadio({
  label,
  value,
  options,
  onChange
}) {
  const trackRef = React.useRef(null);
  const [dragging, setDragging] = React.useState(false);
  // The active value is read by pointer-move handlers attached for the lifetime
  // of a drag — ref it so a stale closure doesn't fire onChange for every move.
  const valueRef = React.useRef(value);
  valueRef.current = value;

  // Segments wrap mid-word once per-segment width runs out. The track is
  // ~248px (280 panel − 28 body pad − 4 seg pad), each button loses 12px
  // to its own padding, and 11.5px system-ui averages ~6.3px/char — so 2
  // options fit ~16 chars each, 3 fit ~10. Past that (or >3 options), fall
  // back to a dropdown rather than wrap.
  const labelLen = o => String(typeof o === 'object' ? o.label : o).length;
  const maxLen = options.reduce((m, o) => Math.max(m, labelLen(o)), 0);
  const fitsAsSegments = maxLen <= ({
    2: 16,
    3: 10
  }[options.length] ?? 0);
  if (!fitsAsSegments) {
    // <select> emits strings — map back to the original option value so the
    // fallback stays type-preserving (numbers, booleans) like the segment path.
    const resolve = s => {
      const m = options.find(o => String(typeof o === 'object' ? o.value : o) === s);
      return m === undefined ? s : typeof m === 'object' ? m.value : m;
    };
    return /*#__PURE__*/React.createElement(TweakSelect, {
      label: label,
      value: value,
      options: options,
      onChange: s => onChange(resolve(s))
    });
  }
  const opts = options.map(o => typeof o === 'object' ? o : {
    value: o,
    label: o
  });
  const idx = Math.max(0, opts.findIndex(o => o.value === value));
  const n = opts.length;
  const segAt = clientX => {
    const r = trackRef.current.getBoundingClientRect();
    const inner = r.width - 4;
    const i = Math.floor((clientX - r.left - 2) / inner * n);
    return opts[Math.max(0, Math.min(n - 1, i))].value;
  };
  const onPointerDown = e => {
    setDragging(true);
    const v0 = segAt(e.clientX);
    if (v0 !== valueRef.current) onChange(v0);
    const move = ev => {
      if (!trackRef.current) return;
      const v = segAt(ev.clientX);
      if (v !== valueRef.current) onChange(v);
    };
    const up = () => {
      setDragging(false);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("div", {
    ref: trackRef,
    role: "radiogroup",
    onPointerDown: onPointerDown,
    className: dragging ? 'twk-seg dragging' : 'twk-seg'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-seg-thumb",
    style: {
      left: `calc(2px + ${idx} * (100% - 4px) / ${n})`,
      width: `calc((100% - 4px) / ${n})`
    }
  }), opts.map(o => /*#__PURE__*/React.createElement("button", {
    key: o.value,
    type: "button",
    role: "radio",
    "aria-checked": o.value === value
  }, o.label))));
}
function TweakSelect({
  label,
  value,
  options,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("select", {
    className: "twk-field",
    value: value,
    onChange: e => onChange(e.target.value)
  }, options.map(o => {
    const v = typeof o === 'object' ? o.value : o;
    const l = typeof o === 'object' ? o.label : o;
    return /*#__PURE__*/React.createElement("option", {
      key: v,
      value: v
    }, l);
  })));
}
function TweakText({
  label,
  value,
  placeholder,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("input", {
    className: "twk-field",
    type: "text",
    value: value,
    placeholder: placeholder,
    onChange: e => onChange(e.target.value)
  }));
}
function TweakNumber({
  label,
  value,
  min,
  max,
  step = 1,
  unit = '',
  onChange
}) {
  const clamp = n => {
    if (min != null && n < min) return min;
    if (max != null && n > max) return max;
    return n;
  };
  const startRef = React.useRef({
    x: 0,
    val: 0
  });
  const onScrubStart = e => {
    e.preventDefault();
    startRef.current = {
      x: e.clientX,
      val: value
    };
    const decimals = (String(step).split('.')[1] || '').length;
    const move = ev => {
      const dx = ev.clientX - startRef.current.x;
      const raw = startRef.current.val + dx * step;
      const snapped = Math.round(raw / step) * step;
      onChange(clamp(Number(snapped.toFixed(decimals))));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-num"
  }, /*#__PURE__*/React.createElement("span", {
    className: "twk-num-lbl",
    onPointerDown: onScrubStart
  }, label), /*#__PURE__*/React.createElement("input", {
    type: "number",
    value: value,
    min: min,
    max: max,
    step: step,
    onChange: e => onChange(clamp(Number(e.target.value)))
  }), unit && /*#__PURE__*/React.createElement("span", {
    className: "twk-num-unit"
  }, unit));
}

// Relative-luminance contrast pick — checkmarks drawn over a swatch need to
// read on both #111 and #fafafa without per-option configuration. Hex input
// only (#rgb / #rrggbb); named or rgb()/hsl() colors fall through to "light".
function __twkIsLight(hex) {
  const h = String(hex).replace('#', '');
  const x = h.length === 3 ? h.replace(/./g, c => c + c) : h.padEnd(6, '0');
  const n = parseInt(x.slice(0, 6), 16);
  if (Number.isNaN(n)) return true;
  const r = n >> 16 & 255,
    g = n >> 8 & 255,
    b = n & 255;
  return r * 299 + g * 587 + b * 114 > 148000;
}
const __TwkCheck = ({
  light
}) => /*#__PURE__*/React.createElement("svg", {
  viewBox: "0 0 14 14",
  "aria-hidden": "true"
}, /*#__PURE__*/React.createElement("path", {
  d: "M3 7.2 5.8 10 11 4.2",
  fill: "none",
  strokeWidth: "2.2",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  stroke: light ? 'rgba(0,0,0,.78)' : '#fff'
}));

// TweakColor — curated color/palette picker. Each option is either a single
// hex string or an array of 1-5 hex strings; the card adapts — a lone color
// renders solid, a palette renders colors[0] as the hero (left ~2/3) with the
// rest stacked in a sharp column on the right. onChange emits the
// option in the shape it was passed (string stays string, array stays array).
// Without options it falls back to the native color input for back-compat.
function TweakColor({
  label,
  value,
  options,
  onChange
}) {
  if (!options || !options.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "twk-row twk-row-h"
    }, /*#__PURE__*/React.createElement("div", {
      className: "twk-lbl"
    }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("input", {
      type: "color",
      className: "twk-swatch",
      value: value,
      onChange: e => onChange(e.target.value)
    }));
  }
  // Native <input type=color> emits lowercase hex per the HTML spec, so
  // compare case-insensitively. String() guards JSON.stringify(undefined),
  // which returns the primitive undefined (no .toLowerCase).
  const key = o => String(JSON.stringify(o)).toLowerCase();
  const cur = key(value);
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-chips",
    role: "radiogroup"
  }, options.map((o, i) => {
    const colors = Array.isArray(o) ? o : [o];
    const [hero, ...rest] = colors;
    const sup = rest.slice(0, 4);
    const on = key(o) === cur;
    return /*#__PURE__*/React.createElement("button", {
      key: i,
      type: "button",
      className: "twk-chip",
      role: "radio",
      "aria-checked": on,
      "data-on": on ? '1' : '0',
      "aria-label": colors.join(', '),
      title: colors.join(' · '),
      style: {
        background: hero
      },
      onClick: () => onChange(o)
    }, sup.length > 0 && /*#__PURE__*/React.createElement("span", null, sup.map((c, j) => /*#__PURE__*/React.createElement("i", {
      key: j,
      style: {
        background: c
      }
    }))), on && /*#__PURE__*/React.createElement(__TwkCheck, {
      light: __twkIsLight(hero)
    }));
  })));
}
function TweakButton({
  label,
  onClick,
  secondary = false
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: secondary ? 'twk-btn secondary' : 'twk-btn',
    onClick: onClick
  }, label);
}
Object.assign(window, {
  useTweaks,
  TweaksPanel,
  TweakSection,
  TweakRow,
  TweakSlider,
  TweakToggle,
  TweakRadio,
  TweakSelect,
  TweakText,
  TweakNumber,
  TweakColor,
  TweakButton
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "site/tweaks-panel.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ai-usage-popover/App.jsx
try { (() => {
const {
  ExtPopover
} = window.AIUsageDesignSystem_480680;
function App() {
  const saved = JSON.parse(localStorage.getItem("aiusage-kit2") || "null");
  const [nav, setNav] = React.useState(saved?.nav || {
    screen: "landing",
    ins: "act",
    fromEarlier: false
  });
  const [opts, setOpts] = React.useState(saved?.opts || {
    dark: false,
    signal: false,
    bar: "tightest",
    urgent: true,
    win: "rolling"
  });
  const [open, setOpen] = React.useState(true);
  React.useEffect(() => localStorage.setItem("aiusage-kit2", JSON.stringify({
    nav,
    opts
  })), [nav, opts]);
  const go = patch => setNav(n => ({
    ...n,
    ...patch
  }));
  const set = (k, v) => setOpts(o => ({
    ...o,
    [k]: v
  }));
  const chip = on => ({
    fontFamily: "var(--font-heading)",
    fontWeight: 600,
    fontSize: 13,
    padding: "3px 9px",
    border: "1px solid var(--color-neutral-600)",
    background: on ? "var(--color-text)" : "transparent",
    color: on ? "var(--color-bg)" : "var(--color-text)",
    cursor: "pointer"
  });
  const Seg = ({
    k,
    items
  }) => /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6
    }
  }, items.map(([v, l]) => /*#__PURE__*/React.createElement("button", {
    key: l,
    style: chip(opts[k] === v),
    onClick: () => set(k, v)
  }, l)));
  const screens = {
    landing: "Insight",
    earlier: "Earlier",
    list: "Agents",
    guide: "Guide",
    about: "About"
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: "100vh",
      background: "var(--color-neutral-300)"
    }
  }, /*#__PURE__*/React.createElement(TopBar, {
    variant: opts.bar,
    urgent: opts.urgent,
    open: open,
    onToggle: () => setOpen(o => !o)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "flex-end",
      padding: "14px 120px 40px 24px",
      gap: 40
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8,
      fontSize: 12,
      color: "var(--color-neutral-800)",
      alignSelf: "flex-start"
    }
  }, /*#__PURE__*/React.createElement(Seg, {
    k: "dark",
    items: [[false, "Light"], [true, "Dark"]]
  }), /*#__PURE__*/React.createElement(Seg, {
    k: "signal",
    items: [[false, "Mono"], [true, "Signal"]]
  }), /*#__PURE__*/React.createElement(Seg, {
    k: "bar",
    items: [["tightest", "Bar 1a"], ["quiet", "Bar 1b"]]
  }), /*#__PURE__*/React.createElement(Seg, {
    k: "urgent",
    items: [[true, "Urgent"], [false, "Calm"]]
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6,
      maxWidth: 220,
      marginTop: 8
    }
  }, Object.entries(screens).map(([s, l]) => /*#__PURE__*/React.createElement("button", {
    key: s,
    style: chip(nav.screen === s),
    onClick: () => {
      setOpen(true);
      go({
        screen: s,
        fromEarlier: false
      });
    }
  }, l))), /*#__PURE__*/React.createElement("span", null, "Click the top-bar indicator to close / reopen.")), open && /*#__PURE__*/React.createElement(ExtPopover, {
    dark: opts.dark,
    signal: opts.signal
  }, nav.screen === "landing" && /*#__PURE__*/React.createElement(LandingScreen, {
    insId: nav.ins || "act",
    fromEarlier: nav.fromEarlier,
    go: go
  }), nav.screen === "earlier" && /*#__PURE__*/React.createElement(EarlierScreen, {
    go: go
  }), nav.screen === "list" && /*#__PURE__*/React.createElement(ListScreen, {
    go: go,
    showPace: true,
    win: opts.win,
    setWin: w => set("win", w)
  }), nav.screen === "detail" && /*#__PURE__*/React.createElement(DetailScreen, {
    provId: nav.prov,
    go: go,
    showPace: true
  }), nav.screen === "sessions" && /*#__PURE__*/React.createElement(SessionsScreen, {
    provId: nav.prov,
    filter: nav.filter || "active",
    go: go
  }), nav.screen === "guide" && /*#__PURE__*/React.createElement(GuideScreen, {
    go: go
  }), nav.screen === "about" && /*#__PURE__*/React.createElement(AboutScreen, {
    go: go
  }))));
}
if (window.__AIU_KIT__) {
  window.App = App;
  const el = document.getElementById("root");
  if (el) ReactDOM.createRoot(el).render(/*#__PURE__*/React.createElement(App, null));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ai-usage-popover/App.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ai-usage-popover/Screens.jsx
try { (() => {
const {
  ExtHeader,
  ExtStats,
  ExtButton,
  ExtSection,
  ExtMeterRow,
  ExtListRow,
  ExtFooter,
  ExtSessionRow,
  ExtWindowPicker,
  ExtFilterChips,
  ExtGuideItem,
  ProviderIcon
} = window.AIUsageDesignSystem_480680;
const byId = id => PROVIDERS.find(p => p.id === id);
const sessionsOf = id => SESSIONS.filter(s => s.p === id);
const sessionMeta = s => [s.model ? s.model + " via " + s.via : null, s.tty, s.paused ? "paused" : null].filter(Boolean).join(" · ");
function useFocusNote() {
  const [note, setNote] = React.useState(null);
  const focus = s => {
    setNote({
      key: s.p + s.tty,
      text: "Focused " + s.project + " · " + s.tty
    });
    clearTimeout(window.__ft);
    window.__ft = setTimeout(() => setNote(null), 2200);
  };
  return [note, focus];
}
function LandingScreen({
  insId,
  fromEarlier,
  go
}) {
  const ins = INSIGHTS.find(i => i.id === insId);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(ExtHeader, {
    kicker: "Insight · " + ins.kind,
    meta: ins.time,
    title: ins.title,
    sub: ins.sub,
    onBack: fromEarlier ? () => go({
      screen: "earlier"
    }) : undefined
  }), /*#__PURE__*/React.createElement(ExtStats, {
    items: ins.stats
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "12px 18px",
      fontSize: 12,
      color: "var(--muted)"
    }
  }, /*#__PURE__*/React.createElement(ProviderIcon, {
    provider: "claude",
    size: 13
  }), /*#__PURE__*/React.createElement("span", null, "Written by Claude Code from your token data")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      padding: "4px 18px 18px"
    }
  }, /*#__PURE__*/React.createElement(ExtButton, {
    variant: "primary",
    block: true,
    label: "Continue to agents",
    onClick: () => go({
      screen: "list"
    })
  }), /*#__PURE__*/React.createElement(ExtButton, {
    variant: "secondary",
    label: "Earlier",
    onClick: () => go({
      screen: "earlier"
    })
  })));
}
function EarlierScreen({
  go
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(ExtHeader, {
    kicker: "Insights",
    meta: "3 today",
    title: "Earlier insights",
    sub: "Written two or three times a day from your token data.",
    onBack: () => go({
      screen: "list"
    })
  }), /*#__PURE__*/React.createElement(ExtSection, null, INSIGHTS.map(i => /*#__PURE__*/React.createElement(ExtListRow, {
    key: i.id,
    kicker: i.kind + " · " + i.time,
    title: i.title,
    meta: "Written by Claude Code",
    onClick: () => go({
      screen: "landing",
      ins: i.id,
      fromEarlier: true
    })
  }))), /*#__PURE__*/React.createElement(ExtFooter, {
    text: "Next insight around 21:00"
  }));
}
function ListScreen({
  go,
  showPace,
  win,
  setWin
}) {
  const running = SESSIONS.filter(s => !s.paused);
  const projects = new Set(running.map(s => s.project)).size;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(ExtHeader, {
    kicker: "AI usage",
    meta: "15:00",
    title: "Claude Code runs out in ~40m.",
    sub: "OpenCode has room. " + running.length + " agents running across " + projects + " projects."
  }), /*#__PURE__*/React.createElement(ExtSection, null, PROVIDERS.map(p => {
    const w = p.windows.find(x => x.kind === win) || p.windows.find(x => x.key === p.binding);
    return /*#__PURE__*/React.createElement(ExtMeterRow, {
      key: p.id,
      icon: p.id,
      label: p.name,
      tag: p.via ? "via " + p.via : w.label,
      value: w.value,
      elapsed: w.elapsed,
      status: p.via ? "ok" : w.status,
      muted: !!p.via,
      showPace: showPace,
      sub: p.via ? "Shares OpenCode limits · " + w.label.toLowerCase() + " " + w.value + "%" : w.sub,
      onClick: () => go({
        screen: "detail",
        prov: p.id
      })
    });
  })), /*#__PURE__*/React.createElement(ExtWindowPicker, {
    options: WINDOWS,
    value: win,
    onChange: setWin
  }), /*#__PURE__*/React.createElement(ExtFooter, {
    text: "Updated 2m ago",
    actionLabel: "Latest insight",
    onAction: () => go({
      screen: "landing",
      ins: "act",
      fromEarlier: false
    }),
    actions: [{
      label: "Guide",
      onClick: () => go({
        screen: "guide"
      })
    }, {
      label: "About",
      onClick: () => go({
        screen: "about"
      })
    }]
  }));
}
function DetailScreen({
  provId,
  go,
  showPace
}) {
  const p = byId(provId);
  const sess = sessionsOf(p.id);
  const active = sess.filter(s => !s.paused);
  const [note, focus] = useFocusNote();
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(ExtHeader, {
    kicker: p.name,
    meta: p.plan,
    title: p.title,
    sub: p.sub,
    onBack: () => go({
      screen: "list"
    })
  }), /*#__PURE__*/React.createElement(ExtSection, {
    label: p.via ? "Limits · shared with OpenCode Go" : "Limits"
  }, p.windows.map(w => /*#__PURE__*/React.createElement(ExtMeterRow, {
    key: w.key,
    label: w.label,
    tag: w.key === p.binding ? "tightest" : "",
    value: w.value,
    elapsed: w.elapsed,
    status: w.status,
    sub: w.sub,
    muted: !!p.via,
    showPace: showPace
  }))), sess.length > 0 && /*#__PURE__*/React.createElement(ExtSection, {
    label: "Sessions · " + active.length + " running"
  }, active.map(s => /*#__PURE__*/React.createElement(ExtSessionRow, {
    key: s.tty,
    project: s.project,
    focused: !!note && note.key === s.p + s.tty,
    meta: sessionMeta(s),
    onFocus: () => focus(s)
  })), /*#__PURE__*/React.createElement(ExtListRow, {
    kicker: "Sessions",
    title: "View all sessions",
    meta: active.length + " active · " + (sess.length - active.length) + " paused",
    onClick: () => go({
      screen: "sessions",
      prov: p.id,
      filter: "active"
    })
  })), /*#__PURE__*/React.createElement(ExtFooter, {
    text: note ? note.text : "Updated 2m ago",
    actionLabel: "Open dashboard"
  }));
}
function SessionsScreen({
  provId,
  filter,
  go
}) {
  const p = byId(provId);
  const sess = sessionsOf(p.id);
  const active = sess.filter(s => !s.paused);
  const paused = sess.filter(s => s.paused);
  const shown = filter === "paused" ? paused : active;
  const [note, focus] = useFocusNote();
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(ExtHeader, {
    kicker: p.name,
    meta: "Sessions",
    title: p.name + " has " + active.length + (active.length === 1 ? " agent" : " agents") + " running.",
    sub: active.length + " active · " + paused.length + " paused · " + sess.length + " total",
    onBack: () => go({
      screen: "detail",
      prov: p.id
    })
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "0 18px 12px"
    }
  }, /*#__PURE__*/React.createElement(ExtFilterChips, {
    options: [{
      value: "active",
      label: "Active",
      count: active.length
    }, {
      value: "paused",
      label: "Paused",
      count: paused.length
    }],
    value: filter,
    onChange: f => go({
      filter: f
    })
  })), /*#__PURE__*/React.createElement(ExtSection, null, shown.length ? shown.map(s => /*#__PURE__*/React.createElement(ExtSessionRow, {
    key: s.tty,
    project: s.project,
    paused: !!s.paused,
    focused: !!note && note.key === s.p + s.tty,
    meta: sessionMeta(s),
    onFocus: () => focus(s)
  })) : /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "14px 18px",
      fontSize: 13,
      color: "var(--muted)"
    }
  }, filter === "paused" ? "No paused sessions" : "No active sessions")), /*#__PURE__*/React.createElement(ExtFooter, {
    text: note ? note.text : "Updated 2m ago"
  }));
}
function GuideScreen({
  go
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(ExtHeader, {
    kicker: "Guide",
    title: "Status colours",
    sub: "Every meter writes its percentage beside it. The colour says how close it is.",
    onBack: () => go({
      screen: "list"
    })
  }), /*#__PURE__*/React.createElement(ExtSection, {
    label: "Status"
  }, /*#__PURE__*/React.createElement(ExtGuideItem, {
    status: "ok",
    title: "Healthy",
    desc: "Plenty of headroom \u2014 under 70% used."
  }), /*#__PURE__*/React.createElement(ExtGuideItem, {
    status: "warn",
    title: "Caution",
    desc: "Getting close \u2014 70 to 89% used."
  }), /*#__PURE__*/React.createElement(ExtGuideItem, {
    status: "crit",
    title: "Critical",
    desc: "At or near your limit \u2014 90% and up."
  })), /*#__PURE__*/React.createElement(ExtSection, {
    label: "Meter"
  }, /*#__PURE__*/React.createElement(ExtGuideItem, {
    marker: "pace",
    title: "Pace tick",
    desc: "The tick on each bar marks even pace."
  })), /*#__PURE__*/React.createElement(ExtFooter, {
    text: "Updated 2m ago"
  }));
}
function AboutScreen({
  go
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(ExtHeader, {
    kicker: "About",
    title: "AI usage",
    sub: "Local GNOME Shell indicator for AI coding limits.",
    onBack: () => go({
      screen: "list"
    })
  }), /*#__PURE__*/React.createElement(ExtSection, null, /*#__PURE__*/React.createElement(ExtGuideItem, {
    title: "Extension v2",
    desc: "Daemon v" + ABOUT.version + " · updated " + ABOUT.updated
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      padding: "6px 18px 18px"
    }
  }, /*#__PURE__*/React.createElement(ExtButton, {
    variant: "secondary",
    block: true,
    label: "Refresh now"
  })));
}
if (window.__AIU_KIT__) Object.assign(window, {
  LandingScreen,
  EarlierScreen,
  ListScreen,
  DetailScreen,
  SessionsScreen,
  GuideScreen,
  AboutScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ai-usage-popover/Screens.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ai-usage-popover/TopBar.jsx
try { (() => {
const {
  ExtPanelIndicator,
  ExtIcon
} = window.AIUsageDesignSystem_480680;
function TopBar({
  variant,
  urgent,
  onToggle,
  open
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height: 30,
      background: "var(--topbar-bg)",
      display: "flex",
      alignItems: "center",
      padding: "0 12px",
      gap: 14,
      color: "var(--color-neutral-100)",
      fontSize: 13
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600
    }
  }, "Activities"), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      textAlign: "center",
      fontWeight: 600
    }
  }, "Oct 8 15:00"), /*#__PURE__*/React.createElement("div", {
    onClick: onToggle,
    style: {
      cursor: "pointer",
      outline: open ? "1px solid color-mix(in srgb, var(--color-neutral-100) 40%, transparent)" : "none"
    }
  }, /*#__PURE__*/React.createElement(ExtPanelIndicator, {
    variant: variant,
    urgent: urgent,
    provider: "claude",
    name: "Claude",
    value: urgent ? "40m" : "33%",
    sessions: SESSIONS.map(s => ({
      paused: !!s.paused
    }))
  })), /*#__PURE__*/React.createElement(ExtIcon, {
    name: "wifi",
    size: 15
  }), /*#__PURE__*/React.createElement(ExtIcon, {
    name: "battery",
    size: 15
  }));
}
if (window.__AIU_KIT__) window.TopBar = TopBar;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ai-usage-popover/TopBar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ai-usage-popover/data.jsx
try { (() => {
const PROVIDERS = [{
  id: "cursor",
  name: "Cursor",
  binding: "monthly",
  plan: "Pro",
  windows: [{
    key: "monthly",
    kind: "monthly",
    label: "Monthly",
    value: 74,
    elapsed: 60,
    sub: "Ahead of pace · out in ~6d, resets in 12d",
    status: "warn"
  }, {
    key: "other",
    kind: "other",
    label: "Other models",
    value: 31,
    elapsed: 60,
    sub: "Resets in 12d",
    status: "ok"
  }],
  title: "Cursor is ahead of pace.",
  sub: "74% of the monthly limit is used with 12 days left. At this rate it runs out in about 6 days."
}, {
  id: "claude",
  name: "Claude Code",
  binding: "5h",
  plan: "Max",
  windows: [{
    key: "5h",
    kind: "rolling",
    label: "5-hour",
    value: 93,
    elapsed: 55,
    sub: "Out in ~40m · resets in 2h 15m",
    status: "crit"
  }, {
    key: "weekly",
    kind: "weekly",
    label: "Weekly",
    value: 81,
    elapsed: 43,
    sub: "Resets in 4d",
    status: "warn"
  }],
  title: "Claude Code runs out in ~40m.",
  sub: "The 5-hour window is at 93% and resets in 2h 15m. Weekly is at 81%."
}, {
  id: "opencode",
  name: "OpenCode",
  binding: "weekly",
  plan: "Go",
  windows: null,
  title: "OpenCode has plenty of room.",
  sub: "Its tightest window is weekly at 33%, under pace. Resets in 2 days."
}, {
  id: "pi",
  name: "Pi",
  binding: "weekly",
  via: "OpenCode Go",
  plan: "",
  windows: null,
  title: "Pi spends OpenCode Go.",
  sub: "optimus meters against OpenCode\u2019s limits. sundeskv2 runs on xAI, which has no tracked limit."
}];
const OC_WINDOWS = [{
  key: "5h",
  kind: "rolling",
  label: "5-hour",
  value: 15,
  elapsed: 3,
  sub: "Resets in 4h 50m",
  status: "ok"
}, {
  key: "weekly",
  kind: "weekly",
  label: "Weekly",
  value: 33,
  elapsed: 71,
  sub: "Under pace · resets in 2d",
  status: "ok"
}, {
  key: "monthly",
  kind: "monthly",
  label: "Monthly",
  value: 23,
  elapsed: 33,
  sub: "Resets in 20d",
  status: "ok"
}];
PROVIDERS.forEach(p => {
  if (!p.windows) p.windows = OC_WINDOWS;
});
const SESSIONS = [{
  p: "claude",
  project: "maarifa-project",
  tty: "pts/7"
}, {
  p: "cursor",
  project: "maarifa-project",
  tty: "pts/2"
}, {
  p: "cursor",
  project: "optimus",
  tty: "pts/3"
}, {
  p: "cursor",
  project: "cursor-folder",
  tty: "pts/4",
  paused: true
}, {
  p: "pi",
  project: "optimus",
  tty: "pts/5",
  model: "deepseek-v4-flash",
  via: "OpenCode Go"
}, {
  p: "pi",
  project: "sundeskv2",
  tty: "pts/6",
  model: "grok-4.6",
  via: "xAI"
}];
const INSIGHTS = [{
  id: "act",
  kind: "Actionable",
  time: "Today 14:00",
  title: "Move to OpenCode before Claude Code\u2019s 5-hour window closes.",
  sub: "Claude Code is at 93% and will hit its limit in about 40 minutes, well before the 2h 15m reset. OpenCode has 67% of its weekly limit free.",
  stats: [{
    value: "93%",
    label: "Claude 5-hour"
  }, {
    value: "~40m",
    label: "until it runs out"
  }, {
    value: "67%",
    label: "OpenCode free"
  }]
}, {
  id: "cost",
  kind: "Model & cost",
  time: "Today 09:00",
  title: "deepseek-v4-flash did Pi\u2019s heaviest work for $0.40.",
  sub: "It handled 2.1M tokens on optimus this week. The same tokens on grok-4.6 would have cost about $3.10.",
  stats: [{
    value: "2.1M",
    label: "tokens"
  }, {
    value: "$0.40",
    label: "spent"
  }, {
    value: "7.8\u00d7",
    label: "cheaper than grok-4.6"
  }]
}, {
  id: "recap",
  kind: "Recap",
  time: "Yesterday 21:00",
  title: "This month: 154 sessions across 11 projects.",
  sub: "Claude Code did 71% of the work. 8.4M tokens in total, most of them on optimus.",
  stats: [{
    value: "154",
    label: "sessions"
  }, {
    value: "8.4M",
    label: "tokens"
  }, {
    value: "71%",
    label: "by Claude Code"
  }]
}];
const WINDOWS = [{
  value: "rolling",
  label: "5-hour"
}, {
  value: "weekly",
  label: "Weekly"
}, {
  value: "monthly",
  label: "Monthly"
}];
const ABOUT = {
  version: "0.4.0",
  updated: "just now"
};
if (window.__AIU_KIT__) Object.assign(window, {
  PROVIDERS,
  SESSIONS,
  INSIGHTS,
  WINDOWS,
  ABOUT
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ai-usage-popover/data.jsx", error: String((e && e.message) || e) }); }

__ds_ns.ExtButton = __ds_scope.ExtButton;

__ds_ns.ExtFilterChips = __ds_scope.ExtFilterChips;

__ds_ns.ExtWindowPicker = __ds_scope.ExtWindowPicker;

__ds_ns.EXT_ICON_PATHS = __ds_scope.EXT_ICON_PATHS;

__ds_ns.ExtIcon = __ds_scope.ExtIcon;

__ds_ns.PROVIDER_ICONS = __ds_scope.PROVIDER_ICONS;

__ds_ns.ProviderIcon = __ds_scope.ProviderIcon;

__ds_ns.ExtPanelIndicator = __ds_scope.ExtPanelIndicator;

__ds_ns.ExtFooter = __ds_scope.ExtFooter;

__ds_ns.ExtHeader = __ds_scope.ExtHeader;

__ds_ns.ExtPopover = __ds_scope.ExtPopover;

__ds_ns.ExtSection = __ds_scope.ExtSection;

__ds_ns.ExtGuideItem = __ds_scope.ExtGuideItem;

__ds_ns.ExtListRow = __ds_scope.ExtListRow;

__ds_ns.ExtMeterRow = __ds_scope.ExtMeterRow;

__ds_ns.ExtSessionRow = __ds_scope.ExtSessionRow;

__ds_ns.ExtStats = __ds_scope.ExtStats;

})();
