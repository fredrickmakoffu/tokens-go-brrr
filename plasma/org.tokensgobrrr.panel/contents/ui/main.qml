import QtQuick
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as P5Support

PlasmoidItem {
    id: root

    switchWidth: Kirigami.Units.gridUnit * 12
    switchHeight: Kirigami.Units.gridUnit * 12

    preferredRepresentation: compactRepresentation

    property bool lightTheme: false

    StateModel {
        id: stateModel
    }

    compactRepresentation: CompactRepresentation {
        model: stateModel
        lightTheme: root.lightTheme
    }

    fullRepresentation: FullRepresentation {
        model: stateModel
        lightTheme: root.lightTheme
    }

    onExpandedChanged: {
        if (expanded)
            stateModel.openPopover();
    }

    P5Support.DataSource {
        id: cfgExec
        engine: "executable"
        connectedSources: []
        onNewData: sourceName => {
            const out = (data.stdout || "").trim();
            disconnectSource(sourceName);
            let theme = "auto";
            try {
                const cfg = JSON.parse(out || "{}");
                if (cfg.ui_theme)
                    theme = String(cfg.ui_theme);
            } catch (e) {}
            applyTheme(theme);
        }
    }

    function applyTheme(theme) {
        if (theme === "dark") {
            lightTheme = false;
            return;
        }
        if (theme === "light") {
            lightTheme = true;
            return;
        }
        lightTheme = Kirigami.Theme.backgroundColor.hslLightness > 0.5;
    }

    function readUiTheme() {
        cfgExec.connectSource(
            "cat \"$HOME/.config/tokens-go-brrr/config.json\" 2>/dev/null || echo '{}'"
        );
    }

    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: root.readUiTheme()
    }

    Component.onCompleted: {
        toolTipMainText = "tokens-go-brrr";
        toolTipSubText = "AI coding usage limits";
        readUiTheme();
        applyTheme("auto");
    }

    Connections {
        target: stateModel
        function onStatusChanged() {
            root.toolTipSubText = stateModel.status;
        }
    }
}
