# winegard2mqtt

Publishes GPS position and cellular modem telemetry from a Winegard ConnecT
router to MQTT, with Home Assistant discovery.

Design doc: [`docs/superpowers/specs/2026-08-08-winegard-gps-mqtt-design.md`](../docs/superpowers/specs/2026-08-08-winegard-gps-mqtt-design.md)

## ⚠️ Position reporting is not finished

The unit this was built against has **no GNSS antenna fitted**. The Quectel
EC25-AF modem has a dedicated `ANT_GNSS` interface separate from the cellular
antennas, and its u.fl connector is unpopulated — so the router reports
`"Not fixed now"` permanently and has never produced a position.

As a result **the coordinate extraction in `parser.parse_gps` is a placeholder.**
It guesses the key names `latitude`/`longitude`/etc., which have never been
observed. Everything around it is finished and tested:

* `GpsFix.build` — validation (range checks, partial fixes, `*unknown*`
  placeholders, Null Island) is schema-independent and fully tested
* the no-fix path, which is what runs today
* modem telemetry, verified against the live router
* session handling, discovery, publishing

### Finishing it

1. Fit a passive GNSS antenna to `ANT_GNSS` (the EC25 supplies no bias voltage,
   so an active antenna needs an external LDO). Confirm from the silkscreen that
   the empty connector really is GNSS and not an unused diversity port.
2. Capture a real fix:
   ```
   curl -c cj -X POST http://10.11.12.1/cgi-bin/luci/themes/winegard2/index.htm \
     -d 'luci_username=admin&luci_password=PASSWORD&luci_continue=CONTINUE'
   curl -b cj http://10.11.12.1/cgi-bin/luci/sys_status
   curl -b cj http://10.11.12.1/cgi-bin/luci/themes/winegard2/gps.htm
   ```
3. Save both as `test/fixtures/sys_status_fix.json` and `gps_fix.html`.
4. Write a failing test asserting the real coordinates parse out of the fixture.
5. Fix the key mapping in `parse_gps` until it passes. If the coordinates turn
   out to live only in the rendered page rather than the JSON, add the HTML
   fallback path — `client.gps_page()` already fetches it.

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
| `winegard/connect/gps` | JSON: `latitude`, `longitude`, `altitude`, `speed`, `heading`, `utc` |
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
