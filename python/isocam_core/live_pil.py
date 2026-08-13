"""PIL compositor for the live WiFi view (no matplotlib/numpy).

The camera exposes no live spectrum/peak over any interface (settled — see the
hardware notes), so a live frame is just the optical image with the loudest
sound source marked: a ring + its dB. The current frequency band (or "Auto") and
the peak from the last *saved* capture are drawn as small captions. Pillow only,
so it runs on SailfishOS.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from .render_pil import _font, _text, ACCENT, DIM

RING = (255, 210, 63)  # warm yellow


def live_frame(jpeg: bytes, nx: float, ny: float, db: float,
               band=None, auto=False, last_peak=None) -> Image.Image:
    """Composite one live frame. nx/ny in 0..1 (loudest spot), db in dB."""
    img = Image.open(__import__("io").BytesIO(jpeg)).convert("RGB")
    w, h = img.size
    d = ImageDraw.Draw(img)

    px = int(min(max(nx, 0.0), 1.0) * w)
    py = int(min(max(ny, 0.0), 1.0) * h)
    r = max(12, h // 26)
    d.ellipse([px - r, py - r, px + r, py + r], outline=RING, width=max(2, h // 240))

    f_big = _font(max(18, h // 22))
    _text(d, (px + r + 10, py - max(18, h // 22)), "%.1f dB" % db, f_big)

    f_cap = _font(max(13, h // 36))
    if auto:
        _text(d, (14, 10), "Auto", f_cap, fill=ACCENT)
    elif band and band[1] > band[0]:
        _text(d, (14, 10), "%.1f-%.1f kHz" % (band[0], band[1]), f_cap, fill=ACCENT)
    if last_peak is not None:
        _text(d, (14, 10 + max(20, h // 30)),
              "Letzter Peak: %.1f kHz" % last_peak, f_cap, fill=DIM)
    return img
