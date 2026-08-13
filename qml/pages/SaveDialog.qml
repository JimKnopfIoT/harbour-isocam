import QtQuick 2.6
import Sailfish.Silica 1.0

Dialog {
    id: dialog
    allowedOrientations: Orientation.All
    property string suggestedName
    property string fileName: nameField.text.trim()

    canAccept: nameField.text.trim().length > 0

    Column {
        width: parent.width

        DialogHeader { title: "Bild speichern"; acceptText: "Speichern" }

        TextField {
            id: nameField
            width: parent.width
            text: dialog.suggestedName
            label: "Dateiname"
            placeholderText: "Dateiname"
            EnterKey.iconSource: "image://theme/icon-m-enter-accept"
            EnterKey.onClicked: if (dialog.canAccept) dialog.accept()
        }

        Label {
            x: Theme.horizontalPageMargin
            width: parent.width - 2 * Theme.horizontalPageMargin
            wrapMode: Text.Wrap
            text: "Ordner:  ~/Pictures/isocam/" + dialog.fileName + ".jpg"
            color: Theme.secondaryColor
            font.pixelSize: Theme.fontSizeExtraSmall
        }
    }
}
