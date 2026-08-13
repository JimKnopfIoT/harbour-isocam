import QtQuick 2.6
import Sailfish.Silica 1.0
import QtPositioning 5.3
import Nemo.Configuration 1.0

Page {
    id: page
    allowedOrientations: Orientation.All
    property var pyRef
    // swipeable set of measurements (gallery-style); folder follows the index
    property var folders: []
    property int index: 0
    property string folder: (index >= 0 && index < folders.length) ? folders[index] : ""
    property var info: ({ name: "…", peak: 0, db: 0, band: [0, 0], auto: false,
                          lat: 0, lon: 0, hasGeo: false })

    // landscape: data column left + image full height right
    // portrait:  data full width on top + image full width below
    property bool land: page.isLandscape
    property real colW: land ? Math.round(page.width * 0.30) : page.width

    // portrait top area: as tall as the data, but enlarged when the map is shown
    property real metaBottom: meta.y + meta.height + Theme.paddingMedium
    property real portTopH: (page.mapShown && page.info.hasGeo)
                            ? Math.max(metaBottom, Math.round(page.height * 0.45))
                            : metaBottom

    // map is a per-page toggle (starts OFF every time) so tagging never auto-
    // enables it; it works on its own as soon as the measurement has a location.
    property bool mapShown: false
    // coordinate-text display, independent of the location data and the map;
    // off by default when a measurement is opened
    property bool coordsShown: false

    // coordinate display format, persisted: 0 = nautical DDM, 1 = DMS, 2 = decimal
    ConfigurationValue {
        id: cfgCoordFmt; key: "/apps/harbour-isocam/coordFormat"; defaultValue: 0
    }

    // live phone GPS — used to geotag THIS measurement on demand
    PositionSource { id: gps; active: true; updateInterval: 3000 }
    property bool geoValid: gps.position.latitudeValid && gps.position.longitudeValid
    property real geoLat: geoValid ? gps.position.coordinate.latitude : NaN
    property real geoLon: geoValid ? gps.position.coordinate.longitude : NaN
    property real geoAlt: gps.position.altitudeValid ? gps.position.coordinate.altitude : NaN

    property var osmWays: []
    property bool osmBusy: false

    function _pad3(n) { return (n < 100 ? (n < 10 ? "00" : "0") : "") + n }
    function fmtCoord(v, isLat) {
        var hemi = isLat ? (v >= 0 ? "N" : "S") : (v >= 0 ? "E" : "W")
        var a = Math.abs(v)
        var deg = Math.floor(a)
        var degStr = isLat ? ("" + deg) : _pad3(deg)
        if (cfgCoordFmt.value === 2)
            return hemi + "  " + a.toFixed(5) + "°"
        if (cfgCoordFmt.value === 1) {
            var mf = (a - deg) * 60, mi = Math.floor(mf), se = (mf - mi) * 60
            return hemi + "  " + degStr + "° " + (mi < 10 ? "0" : "") + mi
                   + "′ " + (se < 10 ? "0" : "") + se.toFixed(1) + "″"
        }
        var mm = (a - deg) * 60
        return hemi + "  " + degStr + "° " + (mm < 10 ? "0" : "") + mm.toFixed(3) + "′"
    }

    function setGeo(la, lo, has) {
        var ni = {}
        for (var k in page.info) ni[k] = page.info[k]
        ni.lat = la; ni.lon = lo; ni.hasGeo = has
        page.info = ni
    }
    function tagHere() {
        if (!page.geoValid) return
        pyRef.call('backend.geotag', [folder, page.geoLat, page.geoLon, page.geoAlt],
                   function(ok) {
            if (ok) { page.setGeo(page.geoLat, page.geoLon, true); page.loadMap() }
        })
    }
    function untagHere() {
        pyRef.call('backend.untag', [folder], function(ok) {
            if (ok) {
                page.mapShown = false
                page.coordsShown = false
                page.setGeo(0, 0, false)
                page.osmWays = []; osmCanvas.requestPaint()
            }
        })
    }
    // 📍 button: tag if not yet located, otherwise just show/hide the coordinates
    // (the location data + map stay). Removing the location is in the pull-down.
    function toggleGeo() {
        if (!page.info.hasGeo) { page.coordsShown = true; tagHere() }
        else page.coordsShown = !page.coordsShown
    }

    function loadMap() {
        if (!page.mapShown || !page.info.hasGeo) { page.osmWays = []; osmCanvas.requestPaint(); return }
        page.osmBusy = true
        pyRef.call('backend.osm_ways', [page.info.lat, page.info.lon, 200],
                   function(res) {
            page.osmBusy = false
            page.osmWays = (res && res.ways) ? res.ways : []
            osmCanvas.requestPaint()
        })
    }

    function loadCurrent() {
        page.coordsShown = false
        page.mapShown = false
        page.osmWays = []
        img.source = ""
        busy.running = true
        pyRef.call('backend.render', [folder], function(res) {
            busy.running = false
            page.info = res
            img.source = "file://" + res.png
        })
    }
    function next() { if (page.index < page.folders.length - 1) page.index++ }
    function prev() { if (page.index > 0) page.index-- }

    Component.onCompleted: loadCurrent()
    onIndexChanged: loadCurrent()
    onColWChanged: osmCanvas.requestPaint()

    // save the whole on-screen view (all layers: bars, data, map, coords, spot)
    property string _pendingName: ""
    Timer { id: saveTimer; interval: 450; onTriggered: page.doSave() }
    function doSave() {
        saveLabel.text = ""   // don't capture a stale "Gespeichert…" note in the grab
        pyRef.call('backend.picture_path', [page._pendingName], function(res) {
            if (!res.path) { saveLabel.text = "Fehler: " + res.error; return }
            // opaque background during the grab so JPEG (no alpha) composites the
            // semi-transparent map/rings correctly instead of dropping them to white
            grabBg.visible = true
            page.grabToImage(function(result) {
                grabBg.visible = false
                saveLabel.text = result.saveToFile(res.path)
                    ? "Gespeichert: " + res.path : "Fehler beim Speichern"
            })
        })
    }

    RemorsePopup { id: remorse }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: height       // no scrolling, just hosts the PullDownMenu

        PullDownMenu {
            MenuItem {
                text: "Verortung entfernen"
                visible: page.info.hasGeo === true
                onClicked: page.untagHere()
            }
            MenuItem {
                text: "In Karte öffnen"
                visible: page.info.hasGeo === true
                onClicked: Qt.openUrlExternally(
                    "geo:" + page.info.lat + "," + page.info.lon)
            }
            MenuItem {
                text: "Bild speichern"
                onClicked: {
                    var dlg = pageStack.push(Qt.resolvedUrl("SaveDialog.qml"),
                                             { suggestedName: page.info.name })
                    dlg.accepted.connect(function() {
                        page._pendingName = dlg.fileName
                        saveTimer.restart()   // let the dialog finish closing first
                    })
                }
            }
            MenuItem {
                text: "Messung löschen"
                onClicked: remorse.execute("Messung löschen", function() {
                    pyRef.call('backend.delete', [folder], function() { pageStack.pop() })
                })
            }
        }

        // opaque backdrop, only shown while grabbing the view to a file
        Rectangle {
            id: grabBg
            anchors.fill: parent
            z: -100
            color: "#232629"   // matches the analysis frame background
            visible: false
        }

        // --- OSM silhouette behind the data column (streets + buildings) ---
        Canvas {
            id: osmCanvas
            x: 0; y: 0
            width: page.land ? page.colW : page.width
            height: page.land ? page.height : page.portTopH
            visible: page.mapShown && page.info.hasGeo
            opacity: 0.9
            onPaint: {
                var ctx = getContext("2d"); ctx.reset()
                if (!visible) return
                var cx = width / 2, cy = height / 2
                var R = Math.min(width, height) / 2 - Theme.paddingLarge
                var maxM = 200.0
                var clat = page.info.lat, clon = page.info.lon
                var coslat = Math.cos(clat * Math.PI / 180)
                // North always points to the device's short top edge:
                //   portrait  → North up   (East right)
                //   landscape → North left (East up) — top edge is on the left
                function proj(la, lo) {
                    var north = (la - clat) * 111320
                    var east = (lo - clon) * 111320 * coslat
                    if (page.land)
                        return { x: cx - north / maxM * R, y: cy - east / maxM * R }
                    return { x: cx + east / maxM * R, y: cy - north / maxM * R }
                }
                var ways = page.osmWays
                for (var i = 0; i < ways.length; ++i) {
                    var w = ways[i], pts = w.pts
                    ctx.beginPath()
                    for (var j = 0; j < pts.length; ++j) {
                        var p = proj(pts[j].lat, pts[j].lon)
                        if (j === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y)
                    }
                    if (w.building) {
                        ctx.closePath()
                        ctx.strokeStyle = Theme.rgba(Theme.secondaryColor, 0.30)
                        ctx.lineWidth = 1
                    } else {
                        ctx.strokeStyle = Theme.rgba(Theme.primaryColor, 0.32)
                        ctx.lineWidth = 1.5
                    }
                    ctx.stroke()
                }
                // range rings every 25 m (50 m emphasised + labelled), matt white
                ctx.font = Math.round(Theme.fontSizeTiny * 0.75) + "px sans-serif"
                ctx.textAlign = "center"
                for (var m = 25; m <= maxM; m += 25) {
                    var rr = m / maxM * R
                    var major = (m % 50 === 0)
                    ctx.strokeStyle = Theme.rgba(Theme.secondaryColor, major ? 0.21 : 0.105)
                    ctx.lineWidth = major ? 1.5 : 1
                    ctx.beginPath(); ctx.arc(cx, cy, rr, 0, 2 * Math.PI); ctx.stroke()
                    if (major) {
                        ctx.fillStyle = Theme.rgba(Theme.secondaryColor, 0.7)
                        ctx.fillText(m + " m", cx, cy - rr - 4)
                    }
                }
                ctx.fillStyle = Theme.highlightColor
                ctx.beginPath(); ctx.arc(cx, cy, 4, 0, 2 * Math.PI); ctx.fill()
            }
        }

        Column {
            id: meta
            x: Theme.horizontalPageMargin
            y: Theme.paddingLarge
            width: page.colW - 2 * Theme.horizontalPageMargin
            spacing: Theme.paddingSmall

            Label {
                width: parent.width
                wrapMode: Text.Wrap
                text: page.info.name
                color: Theme.highlightColor
                font.pixelSize: Theme.fontSizeLarge
            }

            Row {  // GPS = tag/untag this measurement; map toggle (independent)
                spacing: Theme.paddingMedium
                IconButton {
                    icon.source: "image://theme/icon-m-location"
                    icon.color: (page.info.hasGeo && page.coordsShown)
                                ? Theme.highlightColor : Theme.secondaryColor
                    enabled: page.geoValid || page.info.hasGeo
                    onClicked: page.toggleGeo()
                }
                IconButton {
                    icon.source: "image://theme/icon-m-levels"
                    icon.color: page.mapShown ? Theme.highlightColor : Theme.secondaryColor
                    enabled: page.info.hasGeo
                    onClicked: { page.mapShown = !page.mapShown; page.loadMap() }
                }
                Label {
                    anchors.verticalCenter: parent.verticalCenter
                    text: page.osmBusy ? "Karte lädt…"
                          : (!page.info.hasGeo
                             ? (page.geoValid ? "Tippen → verorten" : "GPS sucht…")
                             : (page.coordsShown ? "Koord. an" : "Koord. aus"))
                    color: Theme.secondaryColor
                    font.pixelSize: Theme.fontSizeExtraSmall
                }
            }

            Column {  // stacked values (both orientations)
                spacing: Theme.paddingSmall
                Label { text: "Peak"; color: Theme.secondaryColor; font.pixelSize: Theme.fontSizeExtraSmall }
                Label { text: Number(page.info.peak).toFixed(1) + " kHz"; color: Theme.primaryColor; font.pixelSize: Theme.fontSizeLarge }
                Label { text: "max"; color: Theme.secondaryColor; font.pixelSize: Theme.fontSizeExtraSmall }
                Label { text: Number(page.info.db).toFixed(1) + " dB"; color: Theme.primaryColor; font.pixelSize: Theme.fontSizeLarge }
                Label { text: "Band"; color: Theme.secondaryColor; font.pixelSize: Theme.fontSizeExtraSmall }
                Label {
                    text: page.info.auto ? "Auto"
                                         : Number(page.info.band[0]).toFixed(1) + "–"
                                           + Number(page.info.band[1]).toFixed(1) + " kHz"
                    color: Theme.primaryColor; font.pixelSize: Theme.fontSizeMedium
                }
            }

            Label {  // coordinates, white, under the values (tap cycles format)
                id: coordLabel
                visible: page.info.hasGeo === true && page.coordsShown
                text: page.fmtCoord(Number(page.info.lat), true) + "\n"
                      + page.fmtCoord(Number(page.info.lon), false)
                color: Theme.primaryColor
                font.pixelSize: Theme.fontSizeExtraSmall
                font.family: "monospace"
                MouseArea {
                    anchors.fill: parent
                    onClicked: cfgCoordFmt.value = (cfgCoordFmt.value + 1) % 3
                }
            }

            Label {
                id: saveLabel
                visible: text.length > 0
                width: parent.width
                wrapMode: Text.Wrap
                text: ""
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeExtraSmall
            }
        }

        Image {
            id: img
            x: page.land ? page.colW : 0
            y: page.land ? 0 : page.portTopH
            width: page.land ? (page.width - page.colW) : page.width
            height: page.land ? page.height : (page.height - y)
            fillMode: Image.PreserveAspectFit
            cache: false
            asynchronous: true
        }

        // gallery-style horizontal swipe over the image → prev / next measurement
        MouseArea {
            anchors.fill: img
            property real startX
            property real startY
            onPressed: { startX = mouse.x; startY = mouse.y }
            onReleased: {
                var dx = mouse.x - startX, dy = mouse.y - startY
                if (Math.abs(dx) > page.width * 0.12 && Math.abs(dx) > Math.abs(dy)) {
                    if (dx < 0) page.next(); else page.prev()
                }
            }
        }

        BusyIndicator {
            id: busy
            size: BusyIndicatorSize.Large
            anchors.centerIn: parent
        }
    }
}
