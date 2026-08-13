"""PIL-based renderer for the combined analysis frame (no matplotlib).

Produces one PNG: camera photo + acoustic overlay with the loudest spot's dB and
the exact peak frequency, plus an upright dB-scale spectrum-bar graph on the left
with the band window. Drawn with Pillow so it runs on Sailfish OS.
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

from .formats import Measurement

BG = (35, 38, 41)
PANEL = (24, 26, 28)
FG = (230, 230, 230)
DIM = (154, 160, 166)
ACCENT = (255, 140, 43)
BLUE = (111, 168, 214)
MAXF = 65.0  # kHz full scale (Nyquist)

_FONT_CANDIDATES = [
    "/usr/share/fonts/google-sans/ProductSans-Regular.ttf",
    "/usr/share/fonts/sailfish-default/sailfish.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def _pct(sorted_vals: list, q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, int(q * len(sorted_vals))))
    return sorted_vals[i]


def _text(draw, xy, s, font, fill=FG, anchor=None):
    x, y = xy
    draw.text((x + 1, y + 1), s, font=font, fill=(0, 0, 0), anchor=anchor)
    draw.text((x, y), s, font=font, fill=fill, anchor=anchor)


def analysis_image(m: Measurement, width: int = 900, height: int = 560,
                   alpha: float = 1.0, markers: bool = True,
                   ring: bool = True) -> Image.Image:
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    f_axis = _font(13)
    f_big = _font(22)
    f_med = _font(16)

    # ---- left frequency bar ----
    bar_left, bar_w = 58, 64
    y_top, y_bot = 30, height - 28
    d.rectangle([bar_left - 2, y_top, bar_left + bar_w + 2, y_bot], fill=PANEL)

    def y_of(khz):
        return y_bot - (khz / MAXF) * (y_bot - y_top)

    for t in (0, 10, 20, 30, 40, 50, 60, 65):
        yy = y_of(t)
        _text(d, (bar_left - 8, yy), f"{t}K", f_axis, fill=DIM, anchor="rm")

    auto = bool(m.info.get("autoFreqEnable"))
    if m.spectrum and m.spectrum_hz:
        khz = [h / 1000.0 for h in m.spectrum_hz]
        mag = [0.0 if (k > 64.0 or k < 0.5) else v for k, v in zip(khz, m.spectrum)]
        pos = [v for v in mag if v > 0]
        floor = min(pos) if pos else 1e-9
        mdb = [20.0 * math.log10(v if v > floor else floor) for v in mag]
        base = _pct(sorted(mdb), 0.35)
        peak = max(mdb)
        rng = (peak - base) or 1e-9
        nb = 256
        vals = [0.0] * nb
        for k, dvb in zip(khz, mdb):
            idx = min(nb - 1, max(0, int(k / MAXF * nb)))
            norm = (dvb - base) / rng
            norm = 0.0 if norm < 0 else (1.0 if norm > 1 else norm)
            if norm > vals[idx]:
                vals[idx] = norm
        bh = (y_bot - y_top) / nb
        for i, v in enumerate(vals):
            if v <= 0:
                continue
            c = (i + 0.5) / nb * MAXF
            yy = y_of(c)
            in_band = (not auto) and m.freq_low_khz <= c <= m.freq_high_khz
            col = ACCENT if in_band else BLUE
            d.rectangle([bar_left, yy - bh / 2, bar_left + v * bar_w, yy + bh / 2],
                        fill=col)

    if (not auto) and m.freq_high_khz > m.freq_low_khz:
        for edge in (m.freq_low_khz, m.freq_high_khz):
            yy = y_of(edge)
            d.line([bar_left - 2, yy, bar_left + bar_w + 2, yy], fill=(255, 255, 255),
                   width=2)
            _text(d, (bar_left + bar_w + 6, yy), f"{edge:.1f}", f_axis, anchor="lm")

    # ---- image + overlay + spot labels ----
    ix0, iy0 = 145, 24
    iw, ih = width - ix0 - 18, height - iy0 - 18
    try:
        comp = m.composite(alpha=alpha).convert("RGB")
        cw, ch = comp.size
        scale = min(iw / cw, ih / ch)
        sw, sh = int(cw * scale), int(ch * scale)
        comp = comp.resize((sw, sh), Image.BILINEAR)
        ox, oy = ix0 + (iw - sw) // 2, iy0 + (ih - sh) // 2
        img.paste(comp, (ox, oy))
        _text(d, (ix0, 4), m.name, _font(13), fill=DIM)
        if markers and m.peaks:
            p = m.top_peaks(1)[0]
            px, py = ox + p.nx * sw, oy + p.ny * sh
            r = max(10, sh // 26)
            if ring:
                d.ellipse([px - r, py - r, px + r, py + r], outline=ACCENT, width=3)
            # dB + dominant frequency centred to the RIGHT of the spot
            tx = px + (r + 10 if ring else max(24, sh // 14))
            _text(d, (tx, py - 14), f"{p.db:.1f} dB", f_big)
            if m.dominant_khz:
                _text(d, (tx, py + 14), f"{m.dominant_khz:.1f} kHz", f_med)
    except FileNotFoundError:
        _text(d, (ix0 + 20, iy0 + 20), "kein Foto", f_med, fill=DIM)
    return img
