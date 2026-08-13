import QtQuick 2.6
import Sailfish.Silica 1.0
import QtPositioning 5.3
import Nemo.Configuration 1.0

Page {
    id: page
    allowedOrientations: Orientation.All
    property var pyRef
    property string host: cfgHost.value
    property bool autoCapture: true

    property bool running: false
    property string status: "getrennt"

    ConfigurationValue {
        id: cfgGeotag; key: "/apps/harbour-isocam/geotagEnabled"; defaultValue: true
    }

    // shared with MeasurementsPage — set there via "Kamera-Adresse"
    ConfigurationValue {
        id: cfgHost
        key: "/apps/harbour-isocam/cameraHost"
        defaultValue: "192.168.1.100"
    }

    // phone GPS — geotags auto-captured measurements (the Pocket has no GNSS)
    PositionSource {
        id: gps
        active: page.autoCapture && cfgGeotag.value
        updateInterval: 5000
    }
    property bool geoValid: cfgGeotag.value && gps.position.latitudeValid && gps.position.longitudeValid
    property real geoLat: geoValid ? gps.position.coordinate.latitude : NaN
    property real geoLon: geoValid ? gps.position.coordinate.longitude : NaN
    property real geoAlt: gps.position.altitudeValid ? gps.position.coordinate.altitude : NaN

    function poll() {
        if (!running) return
        pyRef.call('backend.live_poll',
                   [autoCapture, page.geoLat, page.geoLon, page.geoAlt],
                   function(res) {
            if (!running) return
            if (res.error) {
                page.status = "neu verbinden… (" + res.error + ")"
            } else {
                img.source = "file://" + res.png
                page.status = res.auto ? "Auto"
                                       : res.band[0].toFixed(1) + "–" + res.band[1].toFixed(1) + " kHz"
                if (res.peak !== null && res.peak !== undefined)
                    page.status += "   Peak " + res.peak.toFixed(1) + " kHz"
                if (res.captured)
                    capLabel.text = "Aufnahme geladen: " + res.captured
            }
            pollTimer.restart()
        })
    }

    Timer { id: pollTimer; interval: 40; repeat: false; onTriggered: page.poll() }

    function start() {
        page.status = "verbinde…"
        pyRef.call('backend.live_start', [host], function(res) {
            if (res.ok) {
                page.running = true
                page.status = "verbunden mit " + res.host
                page.poll()
            } else {
                page.status = "Login fehlgeschlagen: " + res.error
            }
        })
    }
    function stop() {
        page.running = false
        pollTimer.stop()
        if (pyRef) pyRef.call('backend.live_stop', [], function() {})
        page.status = "getrennt"
    }

    Component.onCompleted: start()
    Component.onDestruction: stop()

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: height       // no scrolling, just hosts the PullDownMenu

        PullDownMenu {
            MenuItem {
                text: page.running ? "Stop" : "Start"
                onClicked: page.running ? page.stop() : page.start()
            }
            MenuItem {
                text: page.autoCapture ? "Auto-Capture: an" : "Auto-Capture: aus"
                onClicked: page.autoCapture = !page.autoCapture
            }
        }

        Image {
            id: img
            anchors.fill: parent
            fillMode: Image.PreserveAspectFit
            cache: false
            asynchronous: true
        }

        Label {
            anchors { top: parent.top; horizontalCenter: parent.horizontalCenter
                      topMargin: Theme.paddingLarge }
            text: page.status
            color: Theme.highlightColor
            font.pixelSize: Theme.fontSizeSmall
        }

        Label {
            id: capLabel
            anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter
                      bottomMargin: Theme.paddingLarge }
            text: ""
            color: Theme.secondaryHighlightColor
            font.pixelSize: Theme.fontSizeExtraSmall
        }

        Label {
            anchors { bottom: parent.bottom; right: parent.right
                      margins: Theme.paddingMedium }
            visible: page.autoCapture && cfgGeotag.value
            text: page.geoValid
                  ? "GPS " + page.geoLat.toFixed(5) + ", " + page.geoLon.toFixed(5)
                  : "GPS sucht…"
            color: page.geoValid ? Theme.highlightColor : Theme.secondaryColor
            font.pixelSize: Theme.fontSizeExtraSmall
        }

        BusyIndicator {
            size: BusyIndicatorSize.Large
            anchors.centerIn: parent
            running: !page.running && img.status !== Image.Ready
        }
    }
}
