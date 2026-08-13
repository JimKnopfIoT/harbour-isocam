import QtQuick 2.6
import Sailfish.Silica 1.0

Dialog {
    id: dialog
    allowedOrientations: Orientation.All

    property string currentHost
    property string host: hostField.text.trim()

    canAccept: hostField.text.trim().length > 0

    Column {
        width: parent.width

        DialogHeader { title: "Kamera-Adresse"; acceptText: "Übernehmen" }

        TextField {
            id: hostField
            width: parent.width
            text: dialog.currentHost
            label: "Adresse der Kamera"
            placeholderText: "z. B. 192.168.1.100"
            inputMethodHints: Qt.ImhNoAutoUppercase | Qt.ImhNoPredictiveText
            EnterKey.iconSource: "image://theme/icon-m-enter-accept"
            EnterKey.onClicked: if (dialog.canAccept) dialog.accept()
        }

        Label {
            x: Theme.horizontalPageMargin
            width: parent.width - 2 * Theme.horizontalPageMargin
            wrapMode: Text.Wrap
            color: Theme.secondaryColor
            font.pixelSize: Theme.fontSizeExtraSmall
            text: "Die Adresse, unter der die Kamera im WLAN erreichbar ist. "
                + "Sie steht am Gerät unter den WLAN-Einstellungen. Der Port (9999) "
                + "wird automatisch angehängt."
        }
    }
}
