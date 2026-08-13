"""Parsers for SonoCam Pocket CRY8024 measurement files — numpy-free.

Uses struct + plain lists so it runs on Sailfish OS (Python 3.11) with only
Pillow, no numpy. Data is tiny (3201-float spectrum, 768-cell grid) so pure
Python is plenty fast.

A measurement folder ``imager/<album>/<YYYYMMDD_HHMMSS>/`` holds:
  <ts>_1.jpg  optical photo, <ts>_0.jpg acoustic overlay (RGBA),
  <ts>.doa    text+binary blocks, info.json, .wav, dateTime, scenarioMode
.doa blocks: scalars ASCII; big arrays length-prefixed float32-LE; the PowerSpec
bin axis is REVERSED (bin 0 = 65 kHz) — handled by the calibration.
"""

from __future__ import annotations

import json
import math
import os
import re
import struct
from dataclasses import dataclass, field

from PIL import Image

_BIN_BLOCKS = {"PowerSpec", "ResEngMap"}


def _isbad(v: float) -> bool:
    return v != v or v == float("inf") or v == float("-inf")


@dataclass
class Peak:
    x: int
    y: int
    db: float
    nx: float = 0.5  # normalized 0..1 position in the image (x -> width)
    ny: float = 0.5  # normalized 0..1 position in the image (y -> height)


@dataclass
class Measurement:
    folder: str
    name: str
    info: dict
    photo_path: str | None
    overlay_path: str | None
    peaks: list = field(default_factory=list)
    freq_low_khz: float = 0.0
    freq_high_khz: float = 0.0
    res_row: int = 32
    res_col: int = 24
    heatmap: list | None = None          # list of rows (ResEngMap)
    spectrum: list | None = None         # PowerSpec magnitudes (list of float)
    spectrum_hz: list | None = None      # matching frequency axis (Hz)
    dominant_khz: float = 0.0
    max_db: float = 0.0

    def top_peaks(self, n: int = 3) -> list:
        return sorted(self.peaks, key=lambda p: p.db, reverse=True)[:n]

    def composite(self, alpha: float = 1.0) -> Image.Image:
        """Camera photo with the acoustic overlay composited on top."""
        if not self.photo_path:
            raise FileNotFoundError("no photo in measurement")
        photo = Image.open(self.photo_path).convert("RGBA")
        if not self.overlay_path:
            return photo
        ov = Image.open(self.overlay_path).convert("RGBA").resize(
            photo.size, Image.BILINEAR
        )
        if alpha < 1.0:
            a = ov.getchannel("A").point(lambda v: int(v * alpha))
            ov.putalpha(a)
        return Image.alpha_composite(photo, ov)


def _find_file(folder: str, suffix: str) -> str | None:
    for fn in os.listdir(folder):
        if fn.endswith(suffix):
            return os.path.join(folder, fn)
    return None


def _doa_blocks(path: str) -> dict:
    data = open(path, "rb").read()
    s = data.find(b"--start--")
    e = data.rfind(b"--end--")
    if s < 0 or e < 0:
        return {}
    region = data[s + len(b"--start--"): e]
    blocks: dict = {}
    i = 0
    while i < len(region):
        mk = region.find(b"**", i)
        if mk < 0:
            break
        colon = region.find(b":", mk)
        if colon < 0:
            break
        name = region[mk + 2:colon].decode("latin1")
        nl = region.find(b"\r\n", colon)
        if name in _BIN_BLOCKS and nl > 0:
            head = region[colon + 1:nl]
            try:
                if b"x" in head:
                    r, c = (int(v) for v in head.split(b"x"))
                    n = r * c
                else:
                    n = int(head)
            except ValueError:
                n = 0
            binend = nl + 2 + n * 4
            blocks[name] = region[colon + 1:binend]
            i = binend
        else:
            nxt = region.find(b"**", colon)
            end = nxt if nxt > 0 else len(region)
            blocks[name] = region[colon + 1:end]
            i = end
    return blocks


def _parse_float_array(block: bytes) -> tuple:
    head, _, raw = block.partition(b"\r\n")
    n = 0
    if b"x" in head:
        rows, cols = (int(v) for v in head.split(b"x"))
        n = rows * cols
    elif head.strip().isdigit():
        n = int(head)
    raw = raw[: n * 4]
    count = len(raw) // 4
    vals = list(struct.unpack("<%df" % count, raw)) if count else []
    return head.decode(), vals


def _mask_invalid(vals: list, limit: float = 1e6) -> list:
    return [float("nan") if (_isbad(v) or abs(v) > limit) else v for v in vals]


def _doa_fileinfo(path: str) -> dict:
    data = open(path, "rb").read(512)
    e = data.find(b"==FILE_INFO_END==")
    txt = data[:e].decode("latin1") if e > 0 else ""
    return dict(re.findall(r"([A-Z_]+):([^\r\n]+)", txt))


def load_measurement(folder: str) -> Measurement:
    name = os.path.basename(folder.rstrip("/"))
    info_path = os.path.join(folder, "info.json")
    info = json.load(open(info_path)) if os.path.exists(info_path) else {}

    m = Measurement(
        folder=folder,
        name=name,
        info=info,
        photo_path=_find_file(folder, "_1.jpg"),
        overlay_path=_find_file(folder, "_0.jpg"),
        freq_low_khz=float(info.get("frequencyDown", 0.0)),
        freq_high_khz=float(info.get("frequencyUp", 0.0)),
        max_db=float(info.get("maxdBSpl", 0.0)),
    )

    doa = _find_file(folder, ".doa")
    if doa:
        fi = _doa_fileinfo(doa)
        m.res_row = int(fi.get("RESROW", 32) or 32)
        m.res_col = int(fi.get("RESCOL", 24) or 24)

    for group in info.get("doaPeaksList", []) or []:
        for p in group:
            x, y = int(p["x"]), int(p["y"])
            m.peaks.append(Peak(
                x, y, float(p["db"]),
                nx=x / max(1, m.res_row - 1),
                ny=y / max(1, m.res_col - 1),
            ))

    if doa:
        blocks = _doa_blocks(doa)
        if "ResEngMap" in blocks:
            head, arr = _parse_float_array(blocks["ResEngMap"])
            try:
                rows, cols = (int(v) for v in head.split("x"))
                if len(arr) >= rows * cols:
                    flat = _mask_invalid(arr[: rows * cols])
                    m.heatmap = [flat[r * cols:(r + 1) * cols] for r in range(rows)]
            except ValueError:
                pass
        if "PowerSpec" in blocks:
            _, spec = _parse_float_array(blocks["PowerSpec"])
            spec = [0.0 if _isbad(v) else v for v in spec]
            m.spectrum = spec
            if len(spec) > 1:
                khz = spectrum_axis_khz(len(spec))
                m.spectrum_hz = [k * 1000.0 for k in khz]
                m.dominant_khz = _dominant_in_band(m)
    return m


# --- frequency-axis calibration (freq_calib.json next to this module) ------
_CALIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "freq_calib.json")


def freq_calibration() -> tuple:
    if os.path.exists(_CALIB_PATH):
        try:
            c = json.load(open(_CALIB_PATH))
            return (float(c["slope_khz_per_bin"]), float(c["offset_khz"]),
                    int(c.get("n", 0)))
        except (ValueError, KeyError, OSError):
            pass
    return 65.0 / 3200.0, 0.0, 3201


def spectrum_axis_khz(n: int) -> list:
    slope, offset, ref_n = freq_calibration()
    if ref_n and ref_n != n:
        slope = slope * (ref_n - 1) / (n - 1)
    return [i * slope + offset for i in range(n)]


def _dominant_in_band(m: Measurement) -> float:
    khz = [h / 1000.0 for h in m.spectrum_hz]
    spec = m.spectrum
    kmax = max(khz) if khz else 0.0
    auto = bool(m.info.get("autoFreqEnable"))
    banded = (not auto) and m.freq_high_khz > m.freq_low_khz
    best_i, best_v = -1, -math.inf
    for i, (k, v) in enumerate(zip(khz, spec)):
        ok = (m.freq_low_khz <= k <= m.freq_high_khz) if banded else (k < kmax * 0.99)
        if ok and v > best_v:
            best_v, best_i = v, i
    return khz[best_i] if best_i >= 0 else 0.0


def find_measurements(root: str) -> list:
    found = []
    for dirpath, _dirs, files in os.walk(root):
        if any(f == "info.json" for f in files) and any(
            f.endswith(".doa") for f in files
        ):
            found.append(dirpath)
    return sorted(found)
