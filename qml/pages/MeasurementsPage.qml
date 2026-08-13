import QtQuick 2.6
import Sailfish.Silica 1.0
import QtPositioning 5.3
import Nemo.Configuration 1.0

Page {
    id: page
    allowedOrientations: Orientation.All
    property var pyRef
    property bool ready: false
    property string host: cfgHost.value

    ConfigurationValue {
        id: cfgGeotag; key: "/apps/harbour-isocam/geotagEnabled"; defaultValue: true
    }

    // The camera's address on your WiFi. Set once via the pulley menu; the
    // default is only a placeholder and will not reach anyone's camera.
    ConfigurationValue {
        id: cfgHost
        key: "/apps/harbour-isocam/cameraHost"
        defaultValue: "192.168.1.100"
    }

    // phone GPS — geotags measurements downloaded via "Von Kamera laden"
    // (only while geotagging is enabled, else we never read a position)
    PositionSource { id: gps; active: cfgGeotag.value; updateInterval: 5000 }
    property bool geoValid: cfgGeotag.value && gps.position.latitudeValid && gps.position.longitudeValid
    property real geoLat: geoValid ? gps.position.coordinate.latitude : NaN
    property real geoLon: geoValid ? gps.position.coordinate.longitude : NaN
    property real geoAlt: (geoValid && gps.position.altitudeValid) ? gps.position.coordinate.altitude : NaN

    ListModel { id: measModel }

    function reload() {
        if (!pyRef) return
        pyRef.call('backend.list_measurements', [], function(items) {
            measModel.clear()
            for (var i = 0; i < items.length; i++) measModel.append(items[i])
        })
    }
    onReadyChanged: if (ready) reload()

    SilicaListView {
        id: view
        anchors.fill: parent
        model: measModel

        header: PageHeader { title: "iSoCam — Messungen" }

        PullDownMenu {
            MenuItem {
                text: "Live-Ansicht"
                onClicked: pageStack.push(Qt.resolvedUrl("LivePage.qml"),
                                          { pyRef: page.pyRef })
            }
            MenuItem {
                text: "Kamera-Adresse: " + page.host
                onClicked: {
                    var dlg = pageStack.push(Qt.resolvedUrl("HostDialog.qml"),
                                             { currentHost: page.host })
                    dlg.accepted.connect(function() { cfgHost.value = dlg.host })
                }
            }
            MenuItem {
                text: cfgGeotag.value ? "Auto-Geotag beim Laden: an"
                                      : "Auto-Geotag beim Laden: aus"
                onClicked: cfgGeotag.value = !cfgGeotag.value
            }
            MenuItem {
                text: "Von Kamera laden"
                onClicked: {
                    busy.running = true
                    pyRef.call('backend.sync',
                               [page.host, page.geoLat, page.geoLon, page.geoAlt],
                               function(res) {
                        busy.running = false
                        reload()
                    })
                }
            }
        }

        delegate: ListItem {
            id: item
            contentHeight: Theme.itemSizeLarge

            Image {
                id: thumb
                x: Theme.horizontalPageMargin
                anchors.verticalCenter: parent.verticalCenter
                height: Theme.itemSizeLarge - Theme.paddingMedium
                width: height * 16 / 9
                fillMode: Image.PreserveAspectCrop
                clip: true
                asynchronous: true
                cache: false
                sourceSize.width: 320
                source: model.thumb ? "file://" + model.thumb : ""
                Rectangle {  // placeholder while loading / if missing
                    anchors.fill: parent
                    visible: thumb.status !== Image.Ready
                    color: Theme.rgba(Theme.secondaryColor, 0.2)
                }
            }
            Label {
                anchors {
                    left: thumb.right; leftMargin: Theme.paddingMedium
                    verticalCenter: parent.verticalCenter
                }
                text: model.name
                color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
            }
            onClicked: {
                var fs = []
                for (var i = 0; i < measModel.count; i++)
                    fs.push(measModel.get(i).folder)
                pageStack.push(Qt.resolvedUrl("DetailPage.qml"),
                               { folders: fs, index: index, pyRef: page.pyRef })
            }

            menu: ContextMenu {
                MenuItem {
                    text: "Löschen"
                    onClicked: item.remorseDelete()
                }
            }
            function remorseDelete() {
                var row = index, fol = model.folder
                remorseAction("Löschen", function() {
                    pyRef.call('backend.delete', [fol], function() {
                        measModel.remove(row)
                    })
                })
            }
        }

        ViewPlaceholder {
            enabled: measModel.count === 0 && !busy.running
            text: "Keine Messungen"
            hintText: "Nach unten ziehen → Von Kamera laden"
        }
        VerticalScrollDecorator {}
    }

    BusyIndicator {
        id: busy
        size: BusyIndicatorSize.Large
        anchors.centerIn: parent
        running: false
    }
}
