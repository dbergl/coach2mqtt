# winegard2mqtt

Publishes GPS position and cellular modem telemetry from a Winegard ConnecT
router to MQTT, with Home Assistant discovery.

Design doc: [`docs/superpowers/specs/2026-08-08-winegard-gps-mqtt-design.md`](../docs/superpowers/specs/2026-08-08-winegard-gps-mqtt-design.md)

## Where the position comes from

A GNSS antenna was fitted on 2026-08-15 and the unit produced its first fix, so
the fixed-state schema is now known rather than guessed.

`sys_status.gps` carries the position directly, as strings holding signed
decimal degrees. **It is a strict superset of the GPS Services page**, so
nothing is scraped and the client fetches only this one endpoint.

Checked field by field against a live fix: every value `gps.htm` renders is in
the JSON — `UTC` as `date` + `time`, `POSITION` as `latitude` + `longitude`,
the reporting-rate select as `gpsrate`, the *WiFi Only* checkbox as `wifi_only`,
and the two service buttons as `tracking` / `heartbeat` (their labels give the
action, not the state, so they read inverted). The page adds units and
hemisphere letters that would only have to be stripped back off, and omits
`fix`, `satellites`, `hdop`, `ttf` and `view` entirely.

This holds for firmware `LEDE-BOTH-20240315`. Were a later build to populate the
page but not the JSON, the `fix` guard below means it would surface as *no
position* rather than a wrong one.

| Key | Example | Notes |
|---|---|---|
| `latitude` / `longitude` | `"12.34567"` / `"-65.43210"` | Signed decimal; south and west are negative |
| `altitude` | `"83.6"` | Metres above sea level |
| `speed` | `"0.0"` | km/h |
| `heading` | `"0.00"` | Degrees |
| `date` + `time` | `"2026/08/15"` + `"22:15:30.0"` | **No `utc` key** — recombined into ISO 8601 |
| `fix` | `"3D"` | `2D` / `3D`; absent when unlocked |
| `satellites` | `"06"` | Used in the solution, not in view |
| `hdop` | `"0.8"` | Published as `gps_accuracy` in metres, ×5 |
| `view` | array | Per-satellite azimuth/elevation/SNR — not parsed |

On a fix the `error` key disappears entirely. A position counts as real only
when `fix` is `2D` or `3D`: coordinates left behind in the JSON after lock is
lost would otherwise read as current. That case has not been observed, but the
cost of guarding it is one comparison.

`hdop` is unitless, so `gps_accuracy` scales it by a nominal 5 m
user-equivalent range error. Crude, but it makes HA draw an honest circle rather
than implying a pinpoint.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `WINEGARD_HOST` | `10.11.12.1` | Router address |
| `WINEGARD_USERNAME` | `admin` | Fixed by the device UI |
| `WINEGARD_PASSWORD` | — | **Required** |
| `WINEGARD_POLL_INTERVAL` | `60` | Seconds between polls |
| `MQTT_HOST` / `MQTT_PORT` | `mosquitto` / `1883` | Broker |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | — | Broker credentials |
| `MQTT_TOPIC_BASE` | `winegard` | Root topic |
| `MQTT_CLIENT_ID` | `connect` | Client / topic segment |

Set `WINEGARD_PASSWORD` in `.env`. The router ships with `admin`/`admin` and
nags until it is changed; changing it means editing `.env` only.

Note the router recomputes its fix every `gpsrate` seconds (default 300, set on
its GPS Services page, minimum 30). Polling faster than that just re-reads the
same values.

## Topics

| Topic | Payload |
|---|---|
| `winegard/connect/state` | `online` / `offline` — bridge reachability (LWT) |
| `winegard/connect/gps/available` | `online` / `offline` — **fix validity** |
| `winegard/connect/gps` | JSON: `latitude`, `longitude`, `altitude`, `speed`, `heading`, `utc`, `fix_type`, `satellites`, `hdop`, `gps_accuracy` |
| `winegard/connect/modem` | JSON: `signal_percent`, `carrier`, `apn`, `state`, `internet_source` |

### Data usage counters reset on every reconnect

`rx_bytes` / `tx_bytes` come from `networks.wwan` and are **per-session, not
cumulative**. Observed directly: 5,554,430,940 bytes before a spontaneous LTE
drop, 1,629,717 a few minutes after it re-established.

They are published with `state_class: total_increasing` so Home Assistant
recognises a drop as a counter reset rather than a negative delta. For
billing-cycle totals, wrap them in a `utility_meter` helper — that accumulates
correctly across resets.

Cellular drops are routine here. They do not affect this service, which reaches
the router over the LAN; they only interrupt remote access to the RV, since the
Winegard is also the uplink for everything else in it.

### Availability

Two availability topics is deliberate. A healthy bridge with no satellite lock
is a normal condition and distinct from a dead bridge, so the modem sensors stay
live while the tracker correctly goes unavailable. On loss of fix the last
position payload is left untouched rather than republished — an RV that admits
it doesn't know where it is beats one frozen at a stale coordinate.

## Development

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt pytest
./venv/bin/python -m pytest test/ -v
```

Tests use real code throughout: `client_test.py` runs against a local HTTP
server that mimics the LuCI login handshake and cookie expiry, and the parser
fixtures are genuine captured router responses.
