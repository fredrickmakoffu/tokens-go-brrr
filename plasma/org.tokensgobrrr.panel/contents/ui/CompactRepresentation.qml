import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasmoid

Item {
    id: compact
    property var model
    property bool lightTheme: false

    readonly property color ok: lightTheme ? "#416180" : "#94bce3"
    readonly property color wait: lightTheme ? "#a45900" : "#f0ba59"
    readonly property color crit: lightTheme ? "#c83122" : "#fd7562"
    readonly property color err: "#7a7a7d"

    implicitWidth: row.implicitWidth + 12
    implicitHeight: Kirigami.Units.iconSizes.medium

    MouseArea {
        anchors.fill: parent
        onClicked: {
            if (model)
                model.openPopover();
            Plasmoid.expanded = !Plasmoid.expanded;
        }
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 8

        Item {
            Layout.preferredWidth: 9
            Layout.preferredHeight: 9
            Rectangle {
                anchors.centerIn: parent
                width: model && model.status === "wait" ? 3 : 9
                height: width
                radius: 0
                color: {
                    if (!model) return ok;
                    if (model.status === "crit") return crit;
                    if (model.status === "error") return err;
                    if (model.status === "wait") return "transparent";
                    return ok;
                }
                border.width: model && model.status === "wait" ? 3 : 0
                border.color: wait
            }
            Rectangle {
                anchors.fill: parent
                visible: !!(model && model.billboard && model.billboard.id !== undefined
                    && Number(model.billboard.id) !== model.landingShownId)
                color: "transparent"
                border.width: 2
                border.color: "#ffffff"
                opacity: 0.85
                radius: 0
            }
        }

        Repeater {
            model: {
                if (!compact.model || !compact.model.tools)
                    return [];
                return compact.model.tools.filter(t => (t.sessions && t.sessions.active > 0));
            }
            delegate: RowLayout {
                spacing: 4
                required property var modelData
                Image {
                    source: compact.model.iconFor(modelData.id)
                    sourceSize.width: 14
                    sourceSize.height: 14
                    fillMode: Image.PreserveAspectFit
                }
                PlasmaComponents.Label {
                    visible: {
                        const m = compact.model.primaryMetric(modelData);
                        return Number(m && m.value) >= compact.model.cautionAt;
                    }
                    text: {
                        const m = compact.model.primaryMetric(modelData);
                        return Math.round(Number(m && m.value) || 0) + "%";
                    }
                    font.pixelSize: 11
                    font.bold: true
                    font.family: "Barlow"
                }
                PlasmaComponents.Label {
                    text: "×" + (modelData.sessions.active || 0)
                    font.pixelSize: 11
                    color: lightTheme ? "#5d5d60" : "#b7b7ba"
                    font.family: "Barlow"
                }
            }
        }
    }
}
