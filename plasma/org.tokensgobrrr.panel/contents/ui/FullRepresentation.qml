import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents

Item {
    id: full
    property var model
    property bool lightTheme: false

    readonly property color surface: lightTheme ? "#f2f2f3" : "#2b2b2d"
    readonly property color textColor: lightTheme ? "#1d1f20" : "#f5f5f8"
    readonly property color muted: lightTheme ? "#5d5d60" : "#b7b7ba"
    readonly property color hairline: lightTheme ? "#cfcfd1" : "#4b4b4e"
    readonly property color rowHover: lightTheme ? "#e9e9ea" : "#363638"
    readonly property color accent: lightTheme ? "#5980a6" : "#94bce3"
    readonly property color ok: lightTheme ? "#416180" : "#94bce3"
    readonly property color wait: lightTheme ? "#a45900" : "#f0ba59"
    readonly property color crit: lightTheme ? "#c83122" : "#fd7562"

    Layout.minimumWidth: 380
    Layout.preferredWidth: 380
    Layout.minimumHeight: 280
    Layout.preferredHeight: 420

    Rectangle {
        anchors.fill: parent
        color: surface
        border.color: hairline
        border.width: 1
        radius: 0
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 0
        spacing: 0

        // Header
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 14
            Layout.rightMargin: 10
            Layout.topMargin: 12
            Layout.bottomMargin: 8
            PlasmaComponents.Label {
                text: {
                    if (!model) return "tokens-go-brrr";
                    if (model.screen === "landing") return model.t("ui.latest");
                    if (model.screen === "guide") return model.t("ui.guide");
                    if (model.screen === "about") return model.t("ui.about");
                    if (model.screen === "detail" && model.detailTool)
                        return model.detailTool.name || model.detailTool.id;
                    return model.t("brand");
                }
                font.family: "Barlow Condensed"
                font.pixelSize: 22
                font.bold: true
                color: textColor
                Layout.fillWidth: true
            }
            PlasmaComponents.ToolButton {
                visible: model && model.screen !== "list" && model.screen !== "landing"
                text: model ? model.t("ui.back") : "Back"
                onClicked: model.showList()
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: hairline }

        Loader {
            Layout.fillWidth: true
            Layout.fillHeight: true
            sourceComponent: {
                if (!model) return listComp;
                if (model.screen === "landing") return landingComp;
                if (model.screen === "detail") return detailComp;
                if (model.screen === "guide") return guideComp;
                if (model.screen === "about") return aboutComp;
                return listComp;
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: hairline }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            spacing: 0
            PlasmaComponents.ToolButton {
                Layout.fillWidth: true
                text: model ? model.t("ui.guide") : "Guide"
                onClicked: model && model.showGuide()
            }
            PlasmaComponents.ToolButton {
                Layout.fillWidth: true
                text: model ? model.t("ui.about") : "About"
                onClicked: model && model.showAbout()
            }
            PlasmaComponents.ToolButton {
                Layout.fillWidth: true
                text: model ? model.t("ui.refresh") : "Refresh"
                onClicked: model && model.refresh()
            }
        }
    }

    Component {
        id: listComp
        ListView {
            clip: true
            model: full.model ? full.model.tools : []
            delegate: Item {
                required property var modelData
                width: ListView.view.width
                height: 58
                Rectangle {
                    anchors.fill: parent
                    color: rowArea.containsMouse ? rowHover : "transparent"
                }
                MouseArea {
                    id: rowArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: full.model.showDetail(modelData)
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 14
                    spacing: 12
                    Rectangle {
                        width: 26; height: 26
                        color: "transparent"
                        border.color: hairline
                        border.width: 1
                        Image {
                            anchors.centerIn: parent
                            width: 16; height: 16
                            source: full.model.iconFor(modelData.id)
                            fillMode: Image.PreserveAspectFit
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        RowLayout {
                            PlasmaComponents.Label {
                                text: modelData.name || modelData.id
                                color: textColor
                                font.family: "Barlow"
                                font.bold: true
                                Layout.fillWidth: true
                            }
                            PlasmaComponents.Label {
                                text: {
                                    const m = full.model.primaryMetric(modelData);
                                    return Math.round(Number(m && m.value) || 0) + "%";
                                }
                                color: textColor
                                font.family: "Barlow Condensed"
                                font.pixelSize: 18
                                font.bold: true
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            height: 3
                            color: hairline
                            radius: 0
                            Rectangle {
                                height: parent.height
                                width: {
                                    const m = full.model.primaryMetric(modelData);
                                    const v = Math.min(100, Math.max(0, Number(m && m.value) || 0));
                                    return parent.width * v / 100;
                                }
                                color: {
                                    const m = full.model.primaryMetric(modelData);
                                    const v = Number(m && m.value) || 0;
                                    if (v >= full.model.criticalAt) return crit;
                                    if (v >= full.model.cautionAt) return wait;
                                    return ok;
                                }
                            }
                        }
                    }
                }
            }
            PlasmaComponents.Label {
                anchors.centerIn: parent
                visible: !full.model || !full.model.tools || full.model.tools.length === 0
                text: full.model && full.model.error ? full.model.error : "…"
                color: muted
            }
        }
    }

    Component {
        id: detailComp
        Flickable {
            clip: true
            contentHeight: detailCol.height
            ColumnLayout {
                id: detailCol
                width: parent.width
                spacing: 0
                Repeater {
                    model: (full.model && full.model.detailTool && full.model.detailTool.metrics) || []
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 14
                        Layout.topMargin: 12
                        Layout.bottomMargin: 8
                        spacing: 6
                        RowLayout {
                            PlasmaComponents.Label {
                                text: modelData.label || modelData.key
                                color: textColor
                                font.family: "Barlow"
                                Layout.fillWidth: true
                            }
                            PlasmaComponents.Label {
                                text: Math.round(Number(modelData.value) || 0) + "%"
                                color: textColor
                                font.bold: true
                            }
                        }
                        PlasmaComponents.Label {
                            text: modelData.resets || ""
                            color: muted
                            font.pixelSize: 12
                            visible: !!(modelData.resets)
                        }
                    }
                }
                PlasmaComponents.Button {
                    Layout.leftMargin: 18
                    Layout.rightMargin: 14
                    Layout.topMargin: 12
                    Layout.bottomMargin: 16
                    text: full.model ? full.model.t("ui.openDashboard") : "Open dashboard"
                    visible: !!(full.model && full.model.detailTool && full.model.detailTool.dashboard)
                    onClicked: {
                        if (full.model && full.model.detailTool && full.model.detailTool.dashboard)
                            Qt.openUrlExternally(full.model.detailTool.dashboard);
                    }
                }
            }
        }
    }

    Component {
        id: guideComp
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 14
            Repeater {
                model: [
                    { name: "Healthy", color: ok, desc: "< 70%" },
                    { name: "Caution", color: wait, desc: "70–89%" },
                    { name: "Critical", color: crit, desc: "≥ 90%" },
                ]
                delegate: RowLayout {
                    required property var modelData
                    spacing: 12
                    Rectangle {
                        width: 9; height: 9; radius: 0
                        color: modelData.name === "Caution" ? "transparent" : modelData.color
                        border.width: modelData.name === "Caution" ? 3 : 0
                        border.color: wait
                    }
                    ColumnLayout {
                        spacing: 2
                        PlasmaComponents.Label { text: modelData.name; color: textColor; font.bold: true }
                        PlasmaComponents.Label { text: modelData.desc; color: muted; font.pixelSize: 12 }
                    }
                }
            }
            Item { Layout.fillHeight: true }
        }
    }

    Component {
        id: aboutComp
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 10
            PlasmaComponents.Label {
                text: "tokens-go-brrr"
                color: textColor
                font.family: "Barlow Condensed"
                font.pixelSize: 22
                font.bold: true
            }
            PlasmaComponents.Label {
                text: (full.model && full.model.version) ? ("v" + full.model.version) : ""
                color: muted
            }
            PlasmaComponents.Label {
                text: full.model && full.model.updatedAt
                    ? full.model.t("ui.updated", { ago: full.model.updatedAt })
                    : ""
                color: muted
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Item { Layout.fillHeight: true }
        }
    }

    Component {
        id: landingComp
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 16
            PlasmaComponents.Label {
                text: {
                    const b = full.model && full.model.billboard;
                    if (!b) return "";
                    return b.title || b.text || "";
                }
                color: textColor
                font.family: "Barlow Condensed"
                font.pixelSize: 22
                font.bold: true
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            PlasmaComponents.Label {
                text: {
                    const b = full.model && full.model.billboard;
                    if (!b) return "";
                    return b.sub || b.body || "";
                }
                color: muted
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                visible: text.length > 0
            }
            RowLayout {
                spacing: 10
                visible: !!(full.model && full.model.billboard && full.model.billboard.featured)
                Image {
                    width: 20; height: 20
                    source: {
                        const f = full.model && full.model.billboard && full.model.billboard.featured;
                        return f ? full.model.iconFor(f.id || f) : "";
                    }
                    fillMode: Image.PreserveAspectFit
                }
                PlasmaComponents.Label {
                    text: {
                        const f = full.model && full.model.billboard && full.model.billboard.featured;
                        return (f && (f.name || f.id)) || "";
                    }
                    color: textColor
                }
            }
            Item { Layout.fillHeight: true }
            PlasmaComponents.Button {
                text: full.model ? full.model.t("ui.continue") : "Continue"
                Layout.fillWidth: true
                onClicked: full.model && full.model.continueFromLanding()
            }
        }
    }
}
