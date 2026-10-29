"""PyOtherSide backend for harbour-isocam.

QML calls these via Python.call('backend.<fn>', [...], cb). All heavy work
(HTTP, .doa parsing, PIL rendering) happens here; QML only shows results.
"""

import http.client
import json
import os
import time

from isocam_core import audio, formats, webclient
from isocam_core.render_pil import analysis_image
from isocam_core.live_pil import live_frame

try:
    import pyotherside  # present on device; absent when the module is imported alone
except ImportError:  # pragma: no cover
    pyotherside = None

DATA_ROOT = os.path.join(
    os.path.expanduser("~"), ".local", "share", "harbour-isocam", "imager"
)
# Fallback only. The real address comes from the QML side, where it is stored in
# dconf (/apps/harbour-isocam/cameraHost) and set via the "Kamera-Adresse" menu.
DEFAULT_HOST = "192.168.1.100"


def _ensure_root():
    os.makedirs(os.path.join(DATA_ROOT, "Default"), exist_ok=True)


def list_measurements():
    """Newest-first list of {folder, name, thumb} from the local store.

    thumb = the camera photo <ts>_1.jpg (QML scales it down for the list)."""
    _ensure_root()
    out = []
    for f in formats.find_measurements(DATA_ROOT):
        name = os.path.basename(f)
        thumb = os.path.join(f, name + "_1.jpg")
        if not os.path.exists(thumb):  # fall back to any jpg in the folder
            jpgs = sorted(n for n in os.listdir(f) if n.lower().endswith(".jpg"))
            thumb = os.path.join(f, jpgs[0]) if jpgs else ""
        out.append({"folder": f, "name": name, "thumb": thumb})
    out.reverse()
    return out


def render(folder):
    """Render the combined analysis to a unique PNG; return its path + summary."""
    m = formats.load_measurement(folder)
    # ring=False: no own ring circle, but keep the dB + frequency labels at the
    # spot over the original's colourful acoustic overlay.
    img = analysis_image(m, width=1080, height=660, markers=True, ring=False)
    cache = os.path.join(DATA_ROOT, ".cache")
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, "view_%d.png" % int(time.time() * 1000))
    img.save(path)
    lat = m.info.get("gpsLatitude", 0.0) or 0.0
    lon = m.info.get("gpsLongitude", 0.0) or 0.0
    return {
        "png": path,
        "name": m.name,
        "peak": round(m.dominant_khz, 1),
        "db": round(m.max_db, 1),
        "band": [round(m.freq_low_khz, 1), round(m.freq_high_khz, 1)],
        "auto": bool(m.info.get("autoFreqEnable")),
        "lat": lat,
        "lon": lon,
        "hasGeo": bool(lat or lon),
        "hasWav": audio.find_wav(folder) is not None,
    }


def _cache_path(folder, suffix):
    cache = os.path.join(DATA_ROOT, ".cache")
    os.makedirs(cache, exist_ok=True)
    return os.path.join(cache, os.path.basename(folder.rstrip("/")) + suffix)


def _fresh(path, src):
    return os.path.exists(path) and os.path.getmtime(path) >= os.path.getmtime(src)


def play_audio(folder, mode="slow"):
    """Audible version of the measurement's ultrasonic WAV; returns {path} or {error}.

    mode "slow" = time expansion 1:10, "mixer" = peak heterodyned to ~2 kHz."""
    src = audio.find_wav(folder)
    if not src:
        return {"error": "keine WAV"}
    mode = "mixer" if mode == "mixer" else "slow"
    path = _cache_path(folder, "_%s.wav" % mode)
    try:
        if not _fresh(path, src):
            w = audio.read_wav(src)
            if mode == "mixer":
                m = formats.load_measurement(folder)
                s, rate = audio.mixer(w, m.dominant_khz * 1000.0)
            else:
                s, rate = audio.slow(w)
            audio.write_wav16(path, s, rate)
    except (OSError, ValueError) as e:
        return {"error": str(e)}
    return {"path": path}


def spectrogram(folder):
    """Spectrogram PNG of the measurement's WAV; returns {png} or {error}."""
    src = audio.find_wav(folder)
    if not src:
        return {"error": "keine WAV"}
    path = _cache_path(folder, "_spec.png")
    try:
        if not _fresh(path, src):
            m = formats.load_measurement(folder)
            img = audio.spectrogram_image(audio.read_wav(src), m.name,
                                          (m.freq_low_khz, m.freq_high_khz),
                                          m.dominant_khz)
            img.save(path + ".part", "PNG")
            os.replace(path + ".part", path)
    except (OSError, ValueError) as e:
        return {"error": str(e)}
    return {"png": path}


def sync(host, lat=None, lon=None, alt=None):
    """Download measurements present on the camera but not yet local.

    If a valid phone position is supplied, geotag each freshly downloaded
    measurement (the Pocket has no GNSS, so info.json's gps* fields are 0)."""
    _ensure_root()
    cam = webclient.CameraHTTP(host or DEFAULT_HOST, timeout=15)
    remote = [n for n in cam.listdir("imager/Default") if n[:8].isdigit()]
    local = os.path.join(DATA_ROOT, "Default")
    have = set(os.listdir(local)) if os.path.isdir(local) else set()
    todo = [n for n in remote if n not in have]
    done = 0
    folders = []
    for ts in todo:
        try:
            dst = os.path.join(local, ts)
            for fn in cam.listdir("imager/Default/%s" % ts):
                cam.download("imager/Default/%s/%s" % (ts, fn),
                             os.path.join(dst, fn))
            geotag(dst, lat, lon, alt)
            folders.append(dst)
            done += 1
            if pyotherside:
                pyotherside.send("sync-progress", done, len(todo))
        except OSError:
            continue
    return {"new": done, "total": len(remote), "folders": folders}


def geotag(folder, lat, lon, alt=None):
    """Write the phone's GPS fix into a measurement's local info.json.

    No-op unless lat/lon are finite numbers (no fix -> leave the 0.0 the camera
    wrote). Returns True if the file was updated."""
    if lat is None or lon is None:
        return False
    try:
        lat = float(lat); lon = float(lon)
    except (TypeError, ValueError):
        return False
    if lat != lat or lon != lon or (lat == 0.0 and lon == 0.0):  # NaN or null island
        return False
    path = os.path.join(folder, "info.json")
    try:
        info = json.load(open(path))
    except (OSError, ValueError):
        return False
    info["gpsLatitude"] = lat
    info["gpsLongitude"] = lon
    if alt is not None:
        try:
            info["gpsAltitude"] = float(alt)
        except (TypeError, ValueError):
            pass
    try:
        with open(path, "w") as fh:
            json.dump(info, fh)
    except OSError:
        return False
    return True


def untag(folder):
    """Clear a measurement's GPS fields back to 0 (un-geotag). Returns True."""
    path = os.path.join(folder, "info.json")
    try:
        info = json.load(open(path))
    except (OSError, ValueError):
        return False
    info["gpsLatitude"] = 0.0
    info["gpsLongitude"] = 0.0
    info["gpsAltitude"] = 0.0
    try:
        with open(path, "w") as fh:
            json.dump(info, fh)
    except OSError:
        return False
    return True


def delete(folder):
    """Delete a whole measurement folder from the local store."""
    import shutil
    try:
        shutil.rmtree(folder)
        for suffix in ("_slow.wav", "_mixer.wav", "_spec.png"):
            p = _cache_path(folder, suffix)
            if os.path.exists(p):
                os.remove(p)
        return True
    except OSError:
        return False


# --- live view over WiFi -------------------------------------------------
# The device serves no live spectrum/peak (proven), so live = camera image +
# loudest spot + dB + current band, plus the exact peak from the last *saved*
# capture (Auto-Capture). One persistent HTTP connection, driven by a QML Timer
# calling live_poll() repeatedly — the camera WiFi (~3-4 fps) is the limit.
_live = {}


def live_start(host):
    """Open a live session; returns {ok, host} or {ok:false, error}."""
    live_stop()
    host = host or DEFAULT_HOST
    cam = webclient.CameraHTTP(host, timeout=8)
    try:
        token = cam.login()
    except Exception as exc:  # noqa: BLE001 — report any failure to the UI
        return {"ok": False, "error": str(exc)}
    known = set()
    try:
        known = {n for n in cam.listdir("imager/Default") if n[:8].isdigit()}
    except OSError:
        pass
    _live.update({
        "cam": cam, "host": host, "token": token,
        "conn": http.client.HTTPConnection(host, 9999, timeout=8),
        "band": (0.0, 0.0), "auto": False, "known": known,
        "last_peak": None, "i": 0,
    })
    return {"ok": True, "host": host}


def _live_get(path):
    conn = _live["conn"]
    conn.request("GET", path)
    r = conn.getresponse()
    body = r.read()
    if r.status != 200:
        raise RuntimeError("HTTP %d" % r.status)
    return body


def live_poll(auto_capture=True, lat=None, lon=None, alt=None):
    """Fetch + composite one live frame. Returns {png, db, band, auto, peak,
    captured} or {error}. captured = name of a newly auto-downloaded measurement.
    A valid phone position geotags the auto-downloaded measurement."""
    if not _live:
        return {"error": "not started"}
    _live["geo"] = (lat, lon, alt)
    token = _live["token"]
    try:
        jpeg = _live_get("/v1/getCameraImage?userId=%s" % token)
        peaks = json.loads(
            _live_get("/v1/maxdB?userId=%s" % token)).get("data", [])
        i = _live["i"]
        if i % 20 == 0:  # band changes rarely
            fb = json.loads(
                _live_get("/v1/frequency?userId=%s" % token)).get("data", [])
            en = next((d for d in fb if d.get("enable")), None)
            if en:
                _live["band"] = (en["freqDown"] / 1000.0, en["freqUp"] / 1000.0)
            _live["auto"] = not en
        _live["i"] = i + 1
    except Exception as exc:  # noqa: BLE001 — reconnect on any socket error
        try:
            _live["conn"].close()
        except OSError:
            pass
        _live["conn"] = http.client.HTTPConnection(_live["host"], 9999, timeout=8)
        return {"error": str(exc)}

    loud = max(peaks, key=lambda p: p.get("value", 0.0)) if peaks else {}
    db = float(loud.get("value", 0.0))
    nx = loud.get("x", 16) / 31.0
    ny = loud.get("y", 12) / 23.0

    captured = None
    if auto_capture and _live["i"] % 12 == 0:
        captured = _live_check_capture()

    png = os.path.join(DATA_ROOT, ".cache")
    os.makedirs(png, exist_ok=True)
    path = os.path.join(png, "live_%d.png" % int(time.time() * 1000))
    live_frame(jpeg, nx, ny, db, band=_live["band"], auto=_live["auto"],
               last_peak=_live["last_peak"]).save(path)
    prev = _live.get("last_png")  # unique names force QML reload; drop the old one
    if prev and prev != path:
        try:
            os.remove(prev)
        except OSError:
            pass
    _live["last_png"] = path
    return {
        "png": path, "db": round(db, 1),
        "band": [round(_live["band"][0], 1), round(_live["band"][1], 1)],
        "auto": bool(_live["auto"]),
        "peak": round(_live["last_peak"], 1) if _live["last_peak"] is not None else None,
        "captured": captured,
    }


def _live_check_capture():
    """Download any measurement saved on the device since the session started."""
    cam = _live["cam"]
    try:
        cur = {n for n in cam.listdir("imager/Default") if n[:8].isdigit()}
    except OSError:
        return None
    new = sorted(cur - _live["known"])
    if not new:
        return None
    ts = new[-1]
    local = os.path.join(DATA_ROOT, "Default", ts)
    try:
        for fn in cam.listdir("imager/Default/%s" % ts):
            cam.download("imager/Default/%s/%s" % (ts, fn),
                         os.path.join(local, fn))
        _live["known"].add(ts)
        lat, lon, alt = _live.get("geo", (None, None, None))
        geotag(local, lat, lon, alt)
        m = formats.load_measurement(local)
        _live["last_peak"] = m.dominant_khz
        return ts
    except OSError:
        return None


def live_stop():
    """Close the live session."""
    if _live:
        try:
            _live["conn"].close()
        except (OSError, KeyError):
            pass
        _live.clear()
    return True


# --- export the overlaid image to ~/Pictures/isocam --------------------
PICTURES_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "isocam")


def picture_path(filename=None):
    """Return the absolute target path in ~/Pictures/isocam for a chosen file
    name (the QML side grabs the on-screen view and saves it there). Ensures the
    folder exists; sanitises the name; always .jpg."""
    os.makedirs(PICTURES_DIR, exist_ok=True)
    name = os.path.basename((filename or "bild").strip())
    for ext in (".jpg", ".jpeg", ".png"):
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
            break
    if not name:
        name = "bild"
    return {"path": os.path.join(PICTURES_DIR, name + ".jpg")}


def save_overlay(folder, filename=None):
    """Save the overlaid colour image (acoustic overlay on the camera photo) as a
    full-resolution JPG into ~/Pictures/isocam. An optional filename (without or
    with extension) overrides the default. Returns {path} or {error}."""
    try:
        m = formats.load_measurement(folder)
        comp = m.composite(alpha=1.0).convert("RGB")
    except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
        return {"error": str(exc)}
    os.makedirs(PICTURES_DIR, exist_ok=True)
    name = os.path.basename((filename or m.name).strip())
    for ext in (".jpg", ".jpeg", ".png"):
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
            break
    if not name:
        name = m.name
    path = os.path.join(PICTURES_DIR, name + ".jpg")
    try:
        comp.save(path, "JPEG", quality=92)
    except OSError as exc:
        return {"error": str(exc)}
    return {"path": path}


# --- OSM silhouette (streets + buildings) for the map background ---------
# Ported from harbour-iwifi's C++ OsmFetch: POST an Overpass query to public
# mirrors, return ways as {building, pts:[{lat,lon}]} for the QML canvas to draw.
_OVERPASS_MIRRORS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def osm_ways(lat, lon, radius=200):
    """Fetch streets + buildings within `radius` m of (lat, lon) via Overpass.
    Returns {ways, lat, lon} or {error}. Tries mirrors in order."""
    import urllib.request
    import urllib.error
    try:
        lat = float(lat); lon = float(lon); radius = int(radius)
    except (TypeError, ValueError):
        return {"error": "bad coords"}
    query = ('[out:json][timeout:20];('
             'way["highway"](around:%d,%.6f,%.6f);'
             'way["building"](around:%d,%.6f,%.6f);'
             ');out geom;' % (radius, lat, lon, radius, lat, lon))
    last = "no mirror reachable"
    for url in _OVERPASS_MIRRORS:
        try:
            req = urllib.request.Request(
                url, data=query.encode("utf-8"),
                headers={"User-Agent": "harbour-isocam",
                         "Content-Type": "text/plain"})
            with urllib.request.urlopen(req, timeout=12) as r:
                root = json.loads(r.read())
            break
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = str(exc)
            continue
    else:
        return {"error": last}

    ways = []
    for el in root.get("elements", []):
        if el.get("type") != "way":
            continue
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        pts = [{"lat": g["lat"], "lon": g["lon"]} for g in geom]
        ways.append({"building": "building" in (el.get("tags") or {}),
                     "pts": pts})
    return {"ways": ways, "lat": lat, "lon": lon}
