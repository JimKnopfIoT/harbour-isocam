import QtQuick 2.6
import Sailfish.Silica 1.0
import io.thp.pyotherside 1.5
import "pages"

ApplicationWindow {
    id: app
    allowedOrientations: Orientation.All
    property bool pyReady: false

    Python {
        id: py
        Component.onCompleted: {
            // python/ ships next to qml/ under /usr/share/harbour-isocam
            addImportPath(Qt.resolvedUrl('../python'));
            importModule('backend', function() { app.pyReady = true; });
        }
        onError: console.log('PyOtherSide error: ' + traceback)
        onReceived: console.log('py event: ' + data)
    }

    initialPage: Component {
        MeasurementsPage { pyRef: py; ready: app.pyReady }
    }
    cover: Qt.resolvedUrl("cover/CoverPage.qml")
}
