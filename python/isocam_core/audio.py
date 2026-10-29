"""Make the measurement's ultrasonic <ts>.wav audible and visible (no numpy).

The camera stores ~1 s of mono audio at 130 kHz next to every photo. Since
firmware 0.0.41 it is 32-bit float with real signal in the measurement band;
older firmware wrote 16-bit PCM that is little more than quantisation noise.

Two ways to listen, both written as 16-bit PCM WAVs a phone can play:
  slow   time expansion 1:10 — same samples played at 13 kHz: ~10 s long, every
         frequency divided by ten (30 kHz -> 3 kHz), the whole spectrum is kept.
  mixer  heterodyne like an ultrasonic leak detector — the peak is mixed down to
         ~2 kHz and played in real time (~1 s).
Plus a spectrogram (time x frequency) rendered with Pillow.
"""

from __future__ import annotations

import cmath
import math
import os
import struct

from PIL import Image, ImageDraw

from .render_pil import ACCENT, BG, DIM, FG, PANEL, _font, _pct, _text

SLOW_FACTOR = 10
MIX_TONE_HZ = 2000.0   # where the peak lands after mixing
MIX_DECIMATE = 3       # 130 kHz -> 43.3 kHz output


class Wav:
    def __init__(self, samples: list, rate: int, fmt: int, bits: int) -> None:
        self.samples = samples
        self.rate = rate
        self.fmt = fmt     # 1 = PCM, 3 = IEEE float
        self.bits = bits

    @property
    def seconds(self) -> float:
        return len(self.samples) / float(self.rate) if self.rate else 0.0

    @property
    def legacy(self) -> bool:
        """16-bit PCM from firmware < 0.0.41: hardly any usable signal."""
        return self.fmt == 1


def find_wav(folder: str) -> str | None:
    name = os.path.basename(folder.rstrip("/"))
    p = os.path.join(folder, name + ".wav")
    if os.path.exists(p):
        return p
    for n in sorted(os.listdir(folder)):
        if n.lower().endswith(".wav"):
            return os.path.join(folder, n)
    return None


def read_wav(path: str) -> Wav:
    """Mono 16-bit PCM or 32-bit float WAV -> samples as floats (-1..1 for PCM)."""
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    fmt = rate = bits = ch = 0
    data = b""
    pos = 12
    while pos + 8 <= len(b):
        cid = b[pos:pos + 4]
        size = struct.unpack("<I", b[pos + 4:pos + 8])[0]
        body = b[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt, ch, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            data = body
            break
        pos += 8 + size + (size & 1)
    if ch != 1:
        raise ValueError("expected mono, got %d channels" % ch)
    if fmt == 3 and bits == 32:
        n = len(data) // 4
        s = list(struct.unpack("<%df" % n, data[:n * 4]))
    elif fmt == 1 and bits == 16:
        n = len(data) // 2
        s = [v / 32768.0 for v in struct.unpack("<%dh" % n, data[:n * 2])]
    else:
        raise ValueError("unsupported WAV format %d/%d bit" % (fmt, bits))
    return Wav(s, rate, fmt, bits)


def write_wav16(path: str, samples: list, rate: int) -> None:
    """Peak-normalise to -1 dBFS, 5 ms fades against clicks, write 16-bit PCM."""
    n = len(samples)
    peak = max((abs(v) for v in samples), default=0.0) or 1.0
    g = 0.89 * 32767.0 / peak
    fade = max(1, min(n // 2, int(rate * 0.005)))
    out = []
    for i, v in enumerate(samples):
        w = 1.0
        if i < fade:
            w = i / fade
        elif i >= n - fade:
            w = (n - 1 - i) / fade
        out.append(int(round(v * g * w)))
    data = struct.pack("<%dh" % n, *out)
    hdr = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(data), b"WAVE",
                      b"fmt ", 16, 1, 1, rate, rate * 2, 2, 16,
                      b"data", len(data))
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(hdr)
        f.write(data)
    os.replace(tmp, path)


def _highpass(x: list, rate: int, fc: float) -> list:
    """One-pole high-pass; also removes the DC offset the camera leaves in."""
    a = 1.0 / (1.0 + 2.0 * math.pi * fc / rate)
    y = []
    py = px = 0.0
    if x:
        px = x[0]
    for v in x:
        py = a * (py + v - px)
        px = v
        y.append(py)
    return y


def _lowpass2(x: list, rate: int, fc: float) -> list:
    """Two cascaded Butterworth biquads (4th order)."""
    w = 2.0 * math.pi * fc / rate
    cw, al = math.cos(w), math.sin(w) / math.sqrt(2.0)
    a0 = 1.0 + al
    b0 = b2 = (1.0 - cw) / 2.0 / a0
    b1 = (1.0 - cw) / a0
    a1 = -2.0 * cw / a0
    a2 = (1.0 - al) / a0
    for _ in range(2):
        y = []
        x1 = x2 = y1 = y2 = 0.0
        for v in x:
            o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            x2, x1, y2, y1 = x1, v, y1, o
            y.append(o)
        x = y
    return x


def slow(wav: Wav) -> tuple:
    """Time expansion: (samples, playback rate)."""
    return _highpass(wav.samples, wav.rate, 1000.0), wav.rate // SLOW_FACTOR


def mixer(wav: Wav, peak_hz: float) -> tuple:
    """Heterodyne the peak down to MIX_TONE_HZ: (samples, playback rate)."""
    lo = max(1000.0, peak_hz - MIX_TONE_HZ)
    x = _highpass(wav.samples, wav.rate, lo)   # keep what's below the LO from folding up
    k = 2.0 * math.pi * lo / wav.rate
    x = [v * math.cos(k * i) for i, v in enumerate(x)]
    x = _lowpass2(x, wav.rate, 6000.0)
    return x[::MIX_DECIMATE], wav.rate // MIX_DECIMATE


# --- spectrogram ---------------------------------------------------------

_FFT_N = 512
_HOP = 512


def _fft_plan(n: int) -> tuple:
    bits = n.bit_length() - 1
    rev = [int(format(i, "0%db" % bits)[::-1], 2) for i in range(n)]
    tw = [cmath.exp(-2j * math.pi * k / n) for k in range(n // 2)]
    return rev, tw


def _fft(a: list, rev: list, tw: list) -> list:
    n = len(a)
    a = [a[r] for r in rev]
    size = 2
    while size <= n:
        half = size // 2
        step = n // size
        for start in range(0, n, size):
            for k in range(half):
                t = tw[k * step] * a[start + k + half]
                u = a[start + k]
                a[start + k] = u + t
                a[start + k + half] = u - t
        size *= 2
    return a


def stft_db(wav: Wav) -> list:
    """Columns (time) of power in dB per bin 0..N/2-1 (low -> high frequency)."""
    n = _FFT_N
    rev, tw = _fft_plan(n)
    win = [0.5 - 0.5 * math.cos(2 * math.pi * i / n) for i in range(n)]
    s = wav.samples
    mean = sum(s) / len(s) if s else 0.0
    cols = []
    for start in range(0, len(s) - n + 1, _HOP):
        frame = [(s[start + i] - mean) * win[i] for i in range(n)]
        spec = _fft(frame, rev, tw)
        cols.append([10.0 * math.log10(abs(c) ** 2 + 1e-20) for c in spec[:n // 2]])
    return cols


# inferno-like ramp, dark -> bright
_RAMP = [(0, 0, 4), (40, 11, 84), (101, 21, 110), (159, 42, 99),
         (212, 72, 66), (245, 125, 21), (250, 193, 39), (252, 255, 164)]


def _color(t: float) -> tuple:
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    p = t * (len(_RAMP) - 1)
    i = min(int(p), len(_RAMP) - 2)
    f = p - i
    a, b = _RAMP[i], _RAMP[i + 1]
    return (int(a[0] + (b[0] - a[0]) * f), int(a[1] + (b[1] - a[1]) * f),
            int(a[2] + (b[2] - a[2]) * f))


def spectrogram_image(wav: Wav, name: str, band: tuple, peak_khz: float,
                      width: int = 1080, height: int = 660) -> Image.Image:
    cols = stft_db(wav)
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    f_axis, f_title = _font(20), _font(24)
    L, R, T, B = 78, 24, 52, 52
    pw, ph = width - L - R, height - T - B
    d.rectangle([L, T, L + pw, T + ph], fill=PANEL)
    nyq = wav.rate / 2000.0  # kHz

    title = "%s  ·  Spektrogramm  ·  %.2f s" % (name, wav.seconds)
    if wav.legacy:
        title += "  ·  16-bit, alte Firmware"
    _text(d, (L, 14), title, f_title)

    if cols:
        flat = sorted(v for c in cols for v in c)
        lo, hi = _pct(flat, 0.20), flat[-1]
        span = (hi - lo) or 1.0
        nb = len(cols[0])
        raw = Image.new("RGB", (len(cols), nb))
        px = []
        for row in range(nb - 1, -1, -1):  # top row = highest frequency
            for c in cols:
                px.append(_color((c[row] - lo) / span))
        raw.putdata(px)
        img.paste(raw.resize((pw, ph), Image.BILINEAR), (L, T))

    def fy(khz: float) -> float:
        return T + ph - (khz / nyq) * ph

    for khz in range(0, int(nyq) + 1, 10):
        y = fy(khz)
        d.line([L - 6, y, L, y], fill=DIM)
        _text(d, (L - 10, y), "%dK" % khz, f_axis, fill=DIM, anchor="rm")
    secs = wav.seconds
    for i in range(0, 5):
        t = i * 0.25
        if t > secs:
            break
        x = L + (t / secs) * pw if secs else L
        d.line([x, T + ph, x, T + ph + 6], fill=DIM)
        _text(d, (x, T + ph + 10), "%.2f s" % t, f_axis, fill=DIM, anchor="ma")

    # measurement band + peak, same colours as the analysis view
    for khz in band:
        if 0 < khz < nyq:
            y = fy(khz)
            for x in range(L, L + pw, 14):
                d.line([x, y, min(x + 7, L + pw), y], fill=FG, width=2)
            _text(d, (L + pw - 4, y - 4), "%.0f" % khz, f_axis, anchor="rb")
    if 0 < peak_khz < nyq:
        y = fy(peak_khz)
        d.polygon([(L + pw + 2, y), (L + pw + 18, y - 9), (L + pw + 18, y + 9)],
                  fill=ACCENT)
    return img
