# Winegard ConnecT GPS → MQTT

**Date:** 2026-08-08
**Status:** Implemented. GNSS antenna fitted and first fix captured 2026-08-15;
the two open items below are resolved — see *Resolution* under each.

## Goal

Publish the RV's GPS position — plus the cellular modem telemetry that comes with
it — from the roof-mounted Winegard ConnecT to MQTT, and surface it in Home
Assistant through MQTT discovery.

## The device

Verified against the live unit at `10.11.12.1`:

| Property | Value |
|---|---|
| Product | `WF2-90B,WF2-95B` |
| Model string | `Winegard ConnecT 2 WF/4G/OTA/Radio` |
| Platform | OpenWrt + LuCI (`ar71xx/generic`, bootloader `WGEX-BOOT-20220901`) |
| API version | `API 2.01` |
| GPS-capable | yes (`showgps: "1"`) |

### HTTP interface

Authentication is LuCI's own form login. The `/ubus` JSON-RPC endpoint exists but
`session.login` returns status `6` (permission denied) — Winegard has locked down
the `rpcd` user database, so ubus is not a usable path.

```
POST /cgi-bin/luci/themes/winegard2/index.htm
     luci_username=admin&luci_password=<pw>&luci_continue=CONTINUE
  → 302, Set-Cookie: sysauth2=<token>; path=/cgi-bin/luci/; Max-Age=3600

GET  /cgi-bin/luci/sys_status                      → application/json (~4.5 KB)
GET  /cgi-bin/luci/themes/winegard2/gps.htm        → HTML, GPS detail fields
```

The username field is `readonly` in the UI and fixed to `admin`; only the
password is variable.

### Available data

`sys_status` carries a `gps` object and modem state:

```json
"gps": { "gpsrate": 300, "wifi_only": false,
         "error": "Not fixed now", "heartbeat": true, "tracking": true },
"internet_source": "wwan_only",
"modem_signal": "68%",
"modem_status": "Connected to Cellular TMOBILE User Data Plan \"fast.T-Mobile.com\"",
"modem_state": "connected"
```

`gps.htm` renders five fields — `utc`, `position`, `altitude`, `speed`,
`heading` — each `*unknown*` when there is no fix.

### Blocker: no GNSS antenna is fitted

**The unit cannot produce a fix in its current state.** The cellular modem is a
Quectel EC25-AF, which has three independent antenna interfaces — `ANT_MAIN`,
`ANT_DIV` and `ANT_GNSS`. GNSS does not share the cellular antenna path. On this
unit the GNSS u.fl connector is **unpopulated**, so there is no signal path to
the GNSS receiver.

This matches Winegard's published spec for the ConnecT 2.0 4G, which lists three
WiFi antennas and two 4G LTE antennas (main + diversity) and no GPS antenna. The
firmware advertises GPS Services (`showgps: "1"`, `tracking: true`) because it is
shared across SKUs, not because this board can use it.

Consequence: `"error": "Not fixed now"` is permanent until an antenna is fitted.
Sky view, driving, and the *WiFi Only* setting are all irrelevant to it. A
12-poll capture over 12 minutes, spanning a *WiFi Only* change, produced no fix
and no variation.

Fitting an antenna: the EC25 supports both passive and active GNSS antennas, but
supplies **no bias voltage** on `ANT_GNSS` — Quectel's guidance is that a passive
antenna needs no VDD circuit while an active one requires an external LDO. As
Winegard never populated this port, assume no bias circuit exists on the board,
which makes a **passive** u.fl GNSS antenna the path of least resistance. Verify
against the silkscreen that the empty connector really is `ANT_GNSS` and not an
unused diversity port before connecting anything.

**Resolution (2026-08-15).** An antenna was fitted and the unit produced a 3D
fix: 6 satellites, HDOP 0.8, `ttf` 174646. The diagnosis held — the port was the
only thing missing.

### Open item: the fixed-state schema

Downstream of the blocker above. Once an antenna is fitted, we still do not know
which keys `gps` gains on a fix, nor how `gps.htm` formats `POSITION` (single
string, coordinate convention unknown).

Resolve it by capturing a real fix before writing the parser — do not guess key
names.

Consequences for the design:

- The reader tries `sys_status.gps` first and falls back to parsing `gps.htm`.
  Both paths must be implemented, because we cannot yet confirm the JSON object
  is populated on a fix — it may only ever carry configuration plus `error`,
  with the coordinates living solely in the rendered page.
- The parser treats *any* unrecognised shape as "no fix" rather than publishing
  a partially-parsed position.

**Resolution (2026-08-15).** `sys_status.gps` carries the position, so the
`gps.htm` fallback was never needed. It is not implemented, and the client's
page fetcher has been removed rather than left as dead code — `curl` covers the
manual-debugging case it would have served. On a fix the object gains
`latitude`, `longitude`, `altitude`, `speed`, `heading`, `date`, `time`, `fix`,
`satellites`, `hdop`, `ttf` and a `view` array, and loses `error` entirely.

Three things the guess got wrong or missed:

- **There is no `utc` key.** The timestamp is split across `date`
  (`"2026/08/15"`) and `time` (`"22:15:30.0"`, fractional part not always
  present) and is recombined into ISO 8601 with an explicit `+00:00`, which is
  what HA's `timestamp` device class requires.
- **Coordinates are signed decimal degrees in strings** — `"-65.43210"`, not
  the hemisphere-suffixed form the page renders (`65.43210 W`). The JSON needs
  no unit stripping; the page would have.
- **Fix quality is available** and was not in the original design: `fix`,
  `satellites` and `hdop` are now published, with `hdop × 5 m` supplying
  `gps_accuracy` so the HA map draws a real circle instead of a false pinpoint.

Validity is now keyed on `fix ∈ {2D, 3D}` rather than on the absence of `error`.
Stale coordinates persisting in the JSON after a lost lock have not been
observed and may not happen, but the guard costs one comparison.

## Approach

A new service inside the `coach2mqtt` repo, built by compose (`build:` rather
than `image:`). This departs from the current convention that every image is
pulled from `ghcr.io/dbergl/*`, accepted deliberately: a single HTTP poller does
not justify a separate repo with its own CI and image publishing.

```
coach2mqtt/
  winegard2mqtt/
    Dockerfile
    requirements.txt
    winegard2mqtt/
      __init__.py
      app.py          # poll loop, signal handling
      client.py       # login, session refresh, sys_status fetch
      parser.py       # raw response → GpsFix | None, ModemStatus
      publisher.py    # MQTT topics + HA discovery payloads
    test/
      client_test.py
      parser_test.py
      publisher_test.py
```

`parser.py` is pure — raw text in, dataclasses out, no I/O — so the fixed-state
schema can be pinned down with fixtures the moment we capture a fix.

## Configuration

All via environment, following existing `coach2mqtt` conventions. Credentials
live in `.env`, never in the compose file or source. The router password is
expected to change from its factory default.

| Variable | Default | Purpose |
|---|---|---|
| `WINEGARD_HOST` | `10.11.12.1` | Router address |
| `WINEGARD_USERNAME` | `admin` | Fixed by the device UI |
| `WINEGARD_PASSWORD` | — | Required; from `.env` |
| `WINEGARD_POLL_INTERVAL` | `60` | Seconds between polls |
| `MQTT_HOST` / `MQTT_PORT` | `mosquitto` / `1883` | Broker |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | — | Broker credentials |
| `MQTT_TOPIC_BASE` | `winegard` | Root topic |
| `MQTT_CLIENT_ID` | `connect` | Client / topic segment |

`.env.example` gains commented entries for each.

## Topics

Root is `<MQTT_TOPIC_BASE>/<MQTT_CLIENT_ID>`, e.g. `winegard/connect`.

| Topic | Retained | Payload |
|---|---|---|
| `winegard/connect/state` | yes | `online` / `offline` — LWT; bridge reachability |
| `winegard/connect/gps/available` | yes | `online` / `offline` — *fix validity* |
| `winegard/connect/gps` | yes | JSON: `latitude`, `longitude`, `altitude`, `speed`, `heading`, `utc`, `fix_type`, `satellites`, `hdop`, `gps_accuracy` |
| `winegard/connect/modem` | yes | JSON: `signal_percent`, `carrier`, `apn`, `modem_state`, `internet_source`, `internet_status` |

Two availability topics, deliberately. `state` says whether we can reach the
router; `gps/available` says whether the reported position is real. A poller
that is healthy but has no satellite lock is a normal, distinct condition.

## Home Assistant discovery

Retained configs under `homeassistant/`, all sharing one device block:

```json
"device": { "identifiers": ["winegard_connect"],
            "manufacturer": "Winegard",
            "model": "ConnecT 2.0 4G (WF2-90B/95B)",
            "name": "Winegard ConnecT" }
```

| Entity | Component | Availability topic |
|---|---|---|
| Position | `device_tracker` (`source_type: gps`, `json_attributes_topic` → `.../gps`) | `gps/available` |
| Altitude | `sensor` (`device_class: distance`, `unit: m`) | `gps/available` |
| Speed | `sensor` (`device_class: speed`, `unit: km/h`) | `gps/available` |
| Heading | `sensor` (`unit: °`) | `gps/available` |
| GPS time | `sensor` (`device_class: timestamp`) | `gps/available` |
| GPS fix | `sensor` (`2D`/`3D`) | `gps/available` |
| Satellites | `sensor` | `gps/available` |
| GPS HDOP | `sensor` (`entity_category: diagnostic`) | `gps/available` |
| Modem signal | `sensor` (`unit: %`) | `state` |
| Carrier | `sensor` | `state` |
| Connection state | `sensor` | `state` |

`gps_accuracy` rides in the position payload rather than being its own entity —
HA's `device_tracker` reads that attribute name natively to size the accuracy
circle.

**Still unverified: zone membership.** The tracker's `state_topic` is
`gps/available` with `payload_home: online`, which makes HA report *home*
whenever a fix exists, wherever the rig actually is. That was untestable while
the unit could not produce a position and remains so here — it needs checking
against the running HA instance. If HA does not derive the zone from the
`latitude`/`longitude` attributes, publish a computed `home`/`not_home` to a
dedicated state topic rather than restructuring the payload.

## Behaviour

**Poll loop.** Every `WINEGARD_POLL_INTERVAL` seconds: fetch, parse, publish.
The device only recomputes its fix every `gpsrate` (currently 300 s), so a
faster poll re-reads the same values — 60 s is a deliberate compromise between
freshness after a change and pointless churn. `gpsrate` is adjustable on the
device's GPS page down to 30 s, which is worth doing when driving.

**No fix.** Publish `offline` to `gps/available` and leave the last `gps`
payload untouched. Never republish a stale position as though it were current;
an RV that admits it does not know where it is beats one frozen at last
Tuesday's parking spot. Modem entities stay available — that data is still good.

**Session expiry.** The cookie has `Max-Age=3600`. On a 403, or a response that
is the login page rather than the expected content, re-login once and retry the
request. A second failure is logged and the poll is skipped; the loop continues.

**Router unreachable.** Log, skip the poll, retry next interval. The MQTT LWT
publishes `offline` to `state` if the process dies outright.

**Shutdown.** Handle `SIGTERM` so compose restarts are clean: publish `offline`
to `state`, disconnect the broker.

## Testing

`parser.py` gets fixtures for both states — the captured no-fix responses we
already have, and the fixed-state responses once observed — asserting that a
fix parses into the right dataclass and that every unrecognised or partial shape
yields `None` rather than a half-populated position.

`client.py` is tested against a local stub HTTP server covering the login
handshake, cookie reuse, and the 403 → re-login → retry path.

`publisher.py` is tested for topic construction and discovery payload shape
without a live broker.

## Notes

**Privacy.** GPS Location Service and Heartbeat were already enabled on the
device. The GPS page states these "allow remote collection of hardware
diagnostics by Winegard." *WiFi Only* was unchecked on 2026-08-08 while
investigating the missing fix; that means this reporting now also travels over
cellular data. Since the absence of a fix turned out to be a hardware matter,
that change bought nothing and can be reverted — re-check *WiFi Only* unless and
until a GNSS antenna is fitted. This integration reads the router locally and
sends nothing to Winegard, but it does not stop the device's own reporting.

*Update 2026-08-15:* the live capture reads `wifi_only: true` and
`heartbeat: false`, so both were duly reverted. Worth restating now that the
antenna works: the device knows where the rig is and reports upstream on its own
schedule, independently of this bridge.

**Test fixtures carry no real position.** `sys_status_fix.json` is derived from
`sys_status_nofix.json` — already scrubbed of MAC, serial, SSID, IMSI, ICCID,
WAN IP and cell id — with only the `gps` object replaced. Coordinates are
substituted while the router's formatting is kept verbatim, since the formatting
is what the parser is tested against. Satellite azimuth and elevation are
synthesised as well: real ones, stamped with a real UTC time, trilaterate back
to where the capture was taken. This repo is public.

The captured `gps.htm` pages were deleted once the JSON proved a superset of
them: no test loads HTML, and keeping a rendered page around invites someone to
start parsing it again. The field mapping it established is recorded in the
service README instead.

**Router password.** Confirmed still the factory default `admin`/`admin` on
2026-08-15, with the device showing its "Default password set!" banner. It is
expected to change; the integration reads it from `.env` so a change means
editing one line, not code.
