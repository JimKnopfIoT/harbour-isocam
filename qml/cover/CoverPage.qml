import QtQuick 2.6
import Sailfish.Silica 1.0

CoverBackground {
    id: cover

    // Fernschreiber-style watermark: a single-colour silhouette of the app motif
    // (acoustic-camera lens + sound waves), oversized so only a crop shows, with
    // depth from varying transparency rather than colour. Hand-drawn (Qt 5.6
    // Canvas has no setLineDash), tinted in the ambience colour.
    Canvas {
        id: watermark
        anchors.fill: parent
        property color tint: Theme.primaryColor
        onTintChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            // motif authored in a 172 box, lens centred at (70,90); scale up ~1.9x
            // and bias it low-left so the waves bleed off the top-right corner.
            var S = Math.max(width, height) * 1.9 / 172
            ctx.translate(width * 0.42 - 70 * S, height * 0.58 - 90 * S)
            ctx.scale(S, S)
            ctx.strokeStyle = tint
            ctx.fillStyle = tint
            ctx.lineCap = "round"

            var cx = 70, cy = 90

            // sound waves radiating to the right, fading outward
            ctx.lineWidth = 7
            var radii = [70, 96, 122, 148]
            for (var i = 0; i < radii.length; i++) {
                ctx.globalAlpha = 0.22 - i * 0.04
                ctx.beginPath()
                ctx.arc(cx, cy, radii[i], -0.95, 0.95)
                ctx.stroke()
            }

            // lens: outer ring
            ctx.globalAlpha = 0.17
            ctx.lineWidth = 6
            ctx.beginPath(); ctx.arc(cx, cy, 48, 0, 2 * Math.PI); ctx.stroke()

            // hexagonal iris
            ctx.globalAlpha = 0.15
            ctx.lineWidth = 4
            ctx.beginPath()
            for (var h = 0; h < 6; h++) {
                var a = Math.PI / 6 + h * Math.PI / 3
                var x = cx + 34 * Math.cos(a), y = cy + 34 * Math.sin(a)
                if (h === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
            }
            ctx.closePath(); ctx.stroke()

            // inner ring + hot centre
            ctx.beginPath(); ctx.arc(cx, cy, 20, 0, 2 * Math.PI); ctx.stroke()
            ctx.globalAlpha = 0.20
            ctx.beginPath(); ctx.arc(cx, cy, 6, 0, 2 * Math.PI); ctx.fill()

            ctx.globalAlpha = 1.0
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: Theme.paddingMedium
        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "iSoCam"
            font.pixelSize: Theme.fontSizeLarge
            color: Theme.highlightColor
        }
        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "CRY8024"
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.secondaryColor
        }
    }
}
