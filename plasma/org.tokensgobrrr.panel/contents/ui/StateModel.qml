import QtQuick
import org.kde.plasma.plasma5support as P5Support

QtObject {
    id: root

    property var state: ({})
    property var tools: []
    property var billboard: null
    property string version: ""
    property string updatedAt: ""
    property string error: ""
    property string status: "ok"
    property int landingShownId: -1
    property string screen: "list"
    property var detailTool: null
    property var locales: ({})
    property string lang: "en"
    property string runtimeUid: ""

    readonly property string busName: "io.github.fredrickmakoffu.TokensGoBrrr"
    readonly property string objectPath: "/io/github/fredrickmakoffu/TokensGoBrrr"
    readonly property string iface: "io.github.fredrickmakoffu.TokensGoBrrr"
    readonly property int cautionAt: 70
    readonly property int criticalAt: 90

    function t(key, params) {
        const cat = locales[lang] || locales["en"] || {};
        let s = cat[key] || (locales["en"] || {})[key] || key;
        if (params) {
            Object.keys(params).forEach(k => {
                s = s.replace("{" + k + "}", params[k]);
            });
        }
        return s;
    }

    function loadLocales() {
        const next = {};
        ["en", "fr", "pt-BR"].forEach(code => {
            const xhr = new XMLHttpRequest();
            xhr.open("GET", Qt.resolvedUrl("locales/" + code + ".json"), false);
            try {
                xhr.send();
                if (xhr.status === 0 || xhr.status === 200)
                    next[code] = JSON.parse(xhr.responseText);
            } catch (e) {}
        });
        locales = next;
    }

    function applyPayload(obj) {
        if (!obj || typeof obj !== "object")
            return;
        state = obj;
        tools = obj.tools || [];
        billboard = obj.billboard || null;
        version = obj.version || "";
        updatedAt = obj.updated_at || "";
        error = obj.error || "";
        status = worstStatus(tools);
    }

    function worstStatus(list) {
        let worst = "ok";
        for (let i = 0; i < list.length; i++) {
            const tool = list[i];
            if (tool.error) {
                worst = "error";
                continue;
            }
            if (tool.borrowed)
                continue;
            const m = primaryMetric(tool);
            const v = Number(m && m.value);
            if (!(v >= 0))
                continue;
            if (v >= criticalAt)
                return "crit";
            if (v >= cautionAt && worst === "ok")
                worst = "wait";
        }
        return worst;
    }

    function primaryMetric(tool) {
        const metrics = (tool && tool.metrics) || [];
        for (let i = 0; i < metrics.length; i++) {
            if (metrics[i].key === tool.primary)
                return metrics[i];
        }
        return metrics[0] || { key: "—", label: "—", value: 0 };
    }

    function shellQuote(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'";
    }

    function stateFilePath() {
        const uid = runtimeUid || "0";
        return "/run/user/" + uid + "/tokens-go-brrr/state.json";
    }

    function readStateFile() {
        if (!runtimeUid)
            return;
        exec.connectSource("cat " + shellQuote(stateFilePath()) + " 2>/dev/null");
    }

    function dbusCall(method, typeArgs) {
        let cmd = "busctl --user call "
            + shellQuote(busName) + " "
            + shellQuote(objectPath) + " "
            + shellQuote(iface) + " "
            + method;
        if (typeArgs && typeArgs.length)
            cmd += " " + typeArgs.join(" ");
        exec.connectSource(cmd + " 2>/dev/null");
    }

    function refresh() { dbusCall("Refresh", []); }
    function acknowledge(id) { dbusCall("Acknowledge", ["u", String(id)]); }

    function openPopover() {
        if (billboard && billboard.id !== undefined && billboard.id !== null
                && Number(billboard.id) !== landingShownId) {
            landingShownId = Number(billboard.id);
            screen = "landing";
        } else {
            screen = "list";
        }
    }

    function continueFromLanding() {
        if (billboard && billboard.id !== undefined && billboard.id !== null)
            acknowledge(billboard.id);
        screen = "list";
    }

    function showDetail(tool) {
        detailTool = tool;
        screen = "detail";
    }

    function showGuide() { screen = "guide"; }
    function showAbout() { screen = "about"; }
    function showList() { screen = "list"; }

    function iconFor(toolId) {
        const map = {
            cursor: "cursor.png",
            claude: "claude.svg",
            codex: "codex.svg",
            opencode: "opencode.svg",
            pi: "pi.svg",
        };
        const file = map[toolId] || (toolId + ".svg");
        return Qt.resolvedUrl("icons/" + file);
    }

    P5Support.DataSource {
        id: uidExec
        engine: "executable"
        connectedSources: ["id -u"]
        onNewData: sourceName => {
            const out = (data.stdout || "").trim();
            if (out)
                root.runtimeUid = out;
            disconnectSource(sourceName);
            root.readStateFile();
        }
    }

    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: sourceName => {
            const out = (data.stdout || "").trim();
            disconnectSource(sourceName);
            if (!out)
                return;
            let raw = out;
            if (raw.indexOf("s ") === 0) {
                raw = raw.slice(2).trim();
                try {
                    raw = JSON.parse(raw);
                } catch (e) {
                    if (raw.charAt(0) === "\"" && raw.charAt(raw.length - 1) === "\"")
                        raw = raw.slice(1, -1).replace(/\\"/g, "\"");
                }
            }
            try {
                const obj = typeof raw === "string" ? JSON.parse(raw) : raw;
                if (obj && obj.tools)
                    root.applyPayload(obj);
            } catch (e) {
                try {
                    root.applyPayload(JSON.parse(out));
                } catch (e2) {}
            }
        }
    }

    Timer {
        interval: 3000
        running: true
        repeat: true
        onTriggered: root.readStateFile()
    }

    Component.onCompleted: loadLocales()
}
