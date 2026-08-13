# SonoCam Pocket CRY8024 — HTTP API (port 9999)

The camera runs an HTTP server on TCP **9999**, reachable over WiFi when the camera
is awake (display on; it WiFi-sleeps when the screen is off). Example on a LAN:
`http://192.168.1.100:9999` (a placeholder — use whatever address the camera has on
your own network). The HTTP interface used by this client is documented below.

## Auth
```
POST /v1/login?user=admin&password=crysound   ->  {"result":true,"data":"<UUID token>"}
```
Pass the returned token as `userId=<token>` on every other call. Health check:
`GET /` -> `SERVER OK 123456`.

## Verified live endpoints (GET, need ?userId=)
| Endpoint | Returns |
|---|---|
| `/v1/devInfo` | appName, buildNumber, deviceId, deviceName, signature … |
| `/v1/deviceRunningParams` | `{doaType, micArraySize:6, micChannelNumber:64, sampleRate:130000}` |
| `/v1/sampleRate` | `{sampleRate:130000}` |
| `/v1/maxdB` | **LIVE** `[{value:<dB>, x, y}]` — loudest source(s) on the DOA grid |
| `/v1/getCameraImage` | **LIVE** optical camera frame (JPEG, ~560 KB) |
| `/v1/frequency` | the configured frequency band(s) |
| `/v1/album` | album list |
| `/v1/getFile`, `/v1/file`, `/v1/downloadFile` | file download by path |

## Other routes
login, userLogin, logout, heartBeat, devInfo, deviceRunningParams, sampleRate,
maxdB, frequency, doaProgramType, nahDistance, certificate, calibrationSwitch,
favorite, album, albumThumbnails, photoThumbnails, devReport, report, createWord,
getCreateReportStatus, getCameraImage, getFile, file, downloadFile,
networkInterfaces, updateResult, videoStreaming, audioCaptureLocal(+Status),
audioCaptureNetwork(+Status), remote/control, remote/status, screen/capture,
task/* …
(On the Pocket, networkInterfaces, videoStreaming and audioCaptureNetwork report
"unSupported" — there is no live audio/video stream on this model.)

## File access
File-browser web roots serve HTML listings: `/download /pictures /recordings
/dcim /update`. The `/download/..` root resolves to the device's shared storage
root, e.g. `GET /download/../imager/Default/<ts>/info.json`. Implemented in
`sonocam/webclient.py`.

## Notes
- All processing is on-device; the raw 64-channel microphone data is not exposed —
  only finished images and numeric results.
- "Live with all data" = poll `/v1/getCameraImage` + `/v1/maxdB` and overlay the
  dB peaks (x,y on the 32×24 DOA grid) onto the frame. There is no live spectrum.
