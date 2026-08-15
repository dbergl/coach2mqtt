import json

import pytest

from winegard2mqtt.parser import GpsFix, ModemStatus
from winegard2mqtt.publisher import Publisher


class RecordingClient:
    """Captures publishes the way a broker would receive them."""

    def __init__(self):
        self.messages = []

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.messages.append({"topic": topic, "payload": payload, "retain": retain})

    def last(self, topic):
        for message in reversed(self.messages):
            if message["topic"] == topic:
                return message
        return None

    def topics(self):
        return [m["topic"] for m in self.messages]


@pytest.fixture
def mqtt():
    return RecordingClient()


@pytest.fixture
def publisher(mqtt):
    return Publisher(mqtt, topic_base="winegard", client_id="connect")


@pytest.fixture
def fix():
    return GpsFix.build(
        latitude=37.7749, longitude=-122.4194,
        altitude=120.5, speed=0.0, heading=271.0, utc="2026-08-08T21:13:38Z",
        fix_type="3D", satellites=6, hdop=0.8,
    )


# --- position ---------------------------------------------------------------


def test_fix_is_published_as_json(publisher, mqtt, fix):
    publisher.publish_gps(fix)

    payload = json.loads(mqtt.last("winegard/connect/gps")["payload"])
    assert payload["latitude"] == pytest.approx(37.7749)
    assert payload["longitude"] == pytest.approx(-122.4194)
    assert payload["altitude"] == pytest.approx(120.5)


def test_fix_marks_position_available(publisher, mqtt, fix):
    publisher.publish_gps(fix)
    assert mqtt.last("winegard/connect/gps/available")["payload"] == "online"


def test_position_is_retained(publisher, mqtt, fix):
    """A restarting HA must see the last position without waiting for a poll."""
    publisher.publish_gps(fix)
    assert mqtt.last("winegard/connect/gps")["retain"] is True


def test_accuracy_travels_with_the_position(publisher, mqtt, fix):
    """gps_accuracy is a name HA's device_tracker knows: it draws the circle."""
    publisher.publish_gps(fix)

    payload = json.loads(mqtt.last("winegard/connect/gps")["payload"])
    assert payload["gps_accuracy"] == 4


def test_fix_quality_travels_with_the_position(publisher, mqtt, fix):
    publisher.publish_gps(fix)

    payload = json.loads(mqtt.last("winegard/connect/gps")["payload"])
    assert payload["fix_type"] == "3D"
    assert payload["satellites"] == 6
    assert payload["hdop"] == pytest.approx(0.8)


def test_no_fix_marks_position_unavailable(publisher, mqtt):
    publisher.publish_gps(None)
    assert mqtt.last("winegard/connect/gps/available")["payload"] == "offline"


def test_no_fix_does_not_overwrite_last_position(publisher, mqtt, fix):
    """Better to go unavailable than to republish a stale coordinate as current."""
    publisher.publish_gps(fix)
    publisher.publish_gps(None)

    assert mqtt.last("winegard/connect/gps")["payload"] == mqtt.messages[0]["payload"]
    assert "winegard/connect/gps" not in mqtt.topics()[-1:]


# --- modem ------------------------------------------------------------------


def test_modem_is_published_as_json(publisher, mqtt):
    publisher.publish_modem(ModemStatus(signal_percent=68, carrier="TMOBILE",
                                        state="connected"))

    payload = json.loads(mqtt.last("winegard/connect/modem")["payload"])
    assert payload["signal_percent"] == 68
    assert payload["carrier"] == "TMOBILE"


def test_data_usage_is_published(publisher, mqtt):
    publisher.publish_modem(ModemStatus(rx_bytes=5528161218, tx_bytes=3063252923))

    payload = json.loads(mqtt.last("winegard/connect/modem")["payload"])
    assert payload["rx_bytes"] == 5528161218
    assert payload["tx_bytes"] == 3063252923


def test_data_usage_sensors_are_announced(publisher, mqtt):
    publisher.publish_discovery()

    for key in ("modem_rx_bytes", "modem_tx_bytes"):
        topic = f"homeassistant/sensor/winegard_connect/{key}/config"
        config = json.loads(mqtt.last(topic)["payload"])
        assert config["device_class"] == "data_size"
        assert config["unit_of_measurement"] == "B"


def test_data_usage_is_a_rising_total(publisher, mqtt):
    """Counters only climb; HA needs to know so statistics aren't nonsense."""
    topic = "homeassistant/sensor/winegard_connect/modem_rx_bytes/config"
    publisher.publish_discovery()

    config = json.loads(mqtt.last(topic)["payload"])
    assert config["state_class"] == "total_increasing"


def test_rssi_sensor_is_announced_in_dbm(publisher, mqtt):
    publisher.publish_discovery()

    topic = "homeassistant/sensor/winegard_connect/modem_rssi_dbm/config"
    config = json.loads(mqtt.last(topic)["payload"])
    assert config["device_class"] == "signal_strength"
    assert config["unit_of_measurement"] == "dBm"


# --- availability -----------------------------------------------------------


def test_bridge_online_is_published(publisher, mqtt):
    publisher.publish_bridge_state(online=True)
    assert mqtt.last("winegard/connect/state")["payload"] == "online"


# --- home assistant discovery ----------------------------------------------


def test_discovery_announces_a_device_tracker(publisher, mqtt):
    publisher.publish_discovery()

    topic = "homeassistant/device_tracker/winegard_connect/position/config"
    config = json.loads(mqtt.last(topic)["payload"])
    assert config["source_type"] == "gps"
    assert config["json_attributes_topic"] == "winegard/connect/gps"


def test_position_entities_use_the_fix_availability_topic(publisher, mqtt):
    """GPS entities must go unavailable on loss of fix, not on loss of router."""
    publisher.publish_discovery()

    topic = "homeassistant/device_tracker/winegard_connect/position/config"
    config = json.loads(mqtt.last(topic)["payload"])
    assert config["availability_topic"] == "winegard/connect/gps/available"


def test_modem_entities_use_the_bridge_availability_topic(publisher, mqtt):
    """Modem data stays valid while there is no satellite fix."""
    publisher.publish_discovery()

    topic = "homeassistant/sensor/winegard_connect/modem_signal/config"
    config = json.loads(mqtt.last(topic)["payload"])
    assert config["availability_topic"] == "winegard/connect/state"


def test_fix_quality_sensors_are_announced(publisher, mqtt):
    publisher.publish_discovery()

    for key in ("gps_fix", "gps_satellites", "gps_hdop"):
        topic = f"homeassistant/sensor/winegard_connect/{key}/config"
        config = json.loads(mqtt.last(topic)["payload"])
        assert config["availability_topic"] == "winegard/connect/gps/available"


def test_hdop_is_a_diagnostic_not_a_headline_reading(publisher, mqtt):
    """Dilution of precision belongs on the diagnostics panel, not the dashboard."""
    topic = "homeassistant/sensor/winegard_connect/gps_hdop/config"
    publisher.publish_discovery()

    assert json.loads(mqtt.last(topic)["payload"])["entity_category"] == "diagnostic"


def test_speed_is_announced_in_the_units_the_router_reports(publisher, mqtt):
    """The rendered page labels this field 'kph'; the JSON gives the bare number."""
    topic = "homeassistant/sensor/winegard_connect/speed/config"
    publisher.publish_discovery()

    config = json.loads(mqtt.last(topic)["payload"])
    assert config["unit_of_measurement"] == "km/h"
    assert config["device_class"] == "speed"


def test_altitude_is_announced_in_metres(publisher, mqtt):
    """'83.6 meters ASL' on the page; 83.6 in the JSON."""
    topic = "homeassistant/sensor/winegard_connect/altitude/config"
    publisher.publish_discovery()

    assert json.loads(mqtt.last(topic)["payload"])["unit_of_measurement"] == "m"


def test_all_entities_share_one_device(publisher, mqtt):
    publisher.publish_discovery()

    configs = [json.loads(m["payload"]) for m in mqtt.messages
               if m["topic"].startswith("homeassistant/")]
    assert len(configs) >= 6
    for config in configs:
        assert config["device"]["identifiers"] == ["winegard_connect"]
        assert config["unique_id"].startswith("winegard_connect_")


def test_discovery_is_retained(publisher, mqtt):
    publisher.publish_discovery()

    for message in mqtt.messages:
        if message["topic"].startswith("homeassistant/"):
            assert message["retain"] is True
