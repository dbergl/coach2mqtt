"""MQTT topic layout and Home Assistant discovery.

Two availability topics, deliberately:

* ``<root>/state`` — can we reach the router at all (also the LWT)
* ``<root>/gps/available`` — is the reported position real

A healthy poller with no satellite lock is a normal condition, and distinct from
a dead bridge. Keeping them apart means the modem sensors stay live while the
tracker correctly goes unavailable.
"""

import json
from typing import NamedTuple, Optional

from .parser import GpsFix, ModemStatus

HA_PREFIX = "homeassistant"
DEVICE_ID = "winegard_connect"

DEVICE = {
    "identifiers": [DEVICE_ID],
    "manufacturer": "Winegard",
    "model": "ConnecT 2.0 4G (WF2-90B/95B)",
    "name": "Winegard ConnecT",
}

class Sensor(NamedTuple):
    """One HA sensor, reading ``json_key`` out of a published JSON payload."""

    key: str
    json_key: str
    name: str
    unit: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    icon: Optional[str] = None
    entity_category: Optional[str] = None


# Units come from how the router's own GPS page labels these fields — "83.6
# meters ASL", "0.0 kph", "0.00 deg" — while sys_status gives the bare numbers.
GPS_SENSORS = [
    Sensor("altitude", "altitude", "Altitude", "m", "distance", "measurement",
           "mdi:altimeter"),
    Sensor("speed", "speed", "Speed", "km/h", "speed", "measurement",
           "mdi:speedometer"),
    Sensor("heading", "heading", "Heading", "°", None, "measurement", "mdi:compass"),
    Sensor("utc", "utc", "GPS Time", None, "timestamp", None, "mdi:clock-outline"),
    Sensor("gps_fix", "fix_type", "GPS Fix", None, None, None, "mdi:crosshairs-gps"),
    Sensor("gps_satellites", "satellites", "Satellites", None, None, "measurement",
           "mdi:satellite-variant"),
    # HDOP explains a bad position rather than being one, so it belongs on the
    # diagnostics panel instead of the dashboard.
    Sensor("gps_hdop", "hdop", "GPS HDOP", None, None, "measurement",
           "mdi:crosshairs-question", "diagnostic"),
]

MODEM_SENSORS = [
    Sensor("modem_signal", "signal_percent", "Modem Signal", "%", None,
           "measurement", "mdi:signal"),
    Sensor("modem_rssi_dbm", "rssi_dbm", "Modem RSSI", "dBm", "signal_strength",
           "measurement"),
    Sensor("modem_band", "band", "LTE Band", icon="mdi:radio-tower"),
    Sensor("modem_mode", "mode", "Network Mode", icon="mdi:radio-tower"),
    # Counters reset only when the modem does, so total_increasing is correct:
    # it lets HA absorb a reboot without inventing a huge negative delta.
    Sensor("modem_rx_bytes", "rx_bytes", "Data Received", "B", "data_size",
           "total_increasing"),
    Sensor("modem_tx_bytes", "tx_bytes", "Data Sent", "B", "data_size",
           "total_increasing"),
    Sensor("modem_carrier", "carrier", "Carrier", icon="mdi:sim"),
    Sensor("modem_state", "state", "Modem State", icon="mdi:radio-tower"),
    Sensor("modem_internet_source", "internet_source", "Internet Source",
           icon="mdi:web"),
]


class Publisher:
    def __init__(self, client, topic_base: str = "winegard", client_id: str = "connect"):
        self.client = client
        self.root = f"{topic_base}/{client_id}"
        self.state_topic = f"{self.root}/state"
        self.gps_topic = f"{self.root}/gps"
        self.gps_available_topic = f"{self.root}/gps/available"
        self.modem_topic = f"{self.root}/modem"

    # -- state ---------------------------------------------------------------

    def publish_bridge_state(self, online: bool) -> None:
        self.client.publish(self.state_topic, "online" if online else "offline",
                            qos=0, retain=True)

    def publish_gps(self, fix: Optional[GpsFix]) -> None:
        """Publish a fix, or mark the position unavailable when there is none.

        On no fix the previous position payload is left untouched: an RV that
        admits it does not know where it is beats one frozen at a stale
        coordinate while still claiming to be current.
        """
        if fix is None:
            self.client.publish(self.gps_available_topic, "offline", qos=0, retain=True)
            return
        self.client.publish(self.gps_topic, json.dumps(fix.as_payload()),
                            qos=0, retain=True)
        self.client.publish(self.gps_available_topic, "online", qos=0, retain=True)

    def publish_modem(self, modem: ModemStatus) -> None:
        self.client.publish(self.modem_topic, json.dumps(modem.as_payload()),
                            qos=0, retain=True)

    # -- discovery -----------------------------------------------------------

    def _publish_config(self, component: str, key: str, config: dict) -> None:
        config.update({
            "device": DEVICE,
            "unique_id": f"{DEVICE_ID}_{key}",
        })
        self.client.publish(
            f"{HA_PREFIX}/{component}/{DEVICE_ID}/{key}/config",
            json.dumps(config), qos=0, retain=True,
        )

    def publish_discovery(self) -> None:
        self._publish_config("device_tracker", "position", {
            "name": "Position",
            "state_topic": self.gps_available_topic,
            "json_attributes_topic": self.gps_topic,
            "source_type": "gps",
            "payload_home": "online",
            "payload_not_home": "offline",
            "availability_topic": self.gps_available_topic,
        })

        self._publish_sensors(GPS_SENSORS, self.gps_topic, self.gps_available_topic)
        self._publish_sensors(MODEM_SENSORS, self.modem_topic, self.state_topic)

    def _publish_sensors(self, sensors, state_topic: str, availability_topic: str) -> None:
        for sensor in sensors:
            self._publish_config("sensor", sensor.key, {
                "name": sensor.name,
                "state_topic": state_topic,
                # Absent keys render as the literal "None" — HA's PAYLOAD_NONE,
                # which it reads as a clean "unknown". Rendering '' instead makes
                # a typed sensor (notably the timestamp GPS Time) log "Invalid
                # state message" on every poll a fix omits that field.
                "value_template":
                    "{{ value_json." + sensor.json_key + " | default('None') }}",
                "availability_topic": availability_topic,
                **({"unit_of_measurement": sensor.unit} if sensor.unit else {}),
                **({"device_class": sensor.device_class} if sensor.device_class else {}),
                **({"state_class": sensor.state_class} if sensor.state_class else {}),
                **({"icon": sensor.icon} if sensor.icon else {}),
                **({"entity_category": sensor.entity_category}
                   if sensor.entity_category else {}),
            })
