import json
import pathlib

import pytest

from winegard2mqtt.parser import GpsFix, parse_gps, parse_modem

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def sys_status_nofix():
    return json.loads((FIXTURES / "sys_status_nofix.json").read_text())


@pytest.fixture
def sys_status_fix():
    """A real 3D fix, captured 2026-08-15 once a GNSS antenna was fitted.

    Coordinates are substituted; the router's formatting is verbatim.
    """
    return json.loads((FIXTURES / "sys_status_fix.json").read_text())


# --- GpsFix.build: coordinate validation ------------------------------------
# This is the schema-independent half of parsing. Whatever key names the router
# turns out to use on a fix, these are the rules the extracted values must obey.


def test_valid_coordinates_build_a_fix():
    fix = GpsFix.build(latitude="37.7749", longitude="-122.4194")
    assert fix is not None
    assert fix.latitude == pytest.approx(37.7749)
    assert fix.longitude == pytest.approx(-122.4194)


def test_optional_fields_are_carried_when_present():
    fix = GpsFix.build(
        latitude=37.7749, longitude=-122.4194,
        altitude="120.5", speed="12.0", heading="271", utc="2026-08-08T21:13:38Z",
    )
    assert fix.altitude == pytest.approx(120.5)
    assert fix.speed == pytest.approx(12.0)
    assert fix.heading == pytest.approx(271.0)
    assert fix.utc == "2026-08-08T21:13:38Z"


def test_missing_longitude_is_not_a_fix():
    """Half a position is not a position."""
    assert GpsFix.build(latitude=37.7749, longitude=None) is None


def test_unknown_placeholder_is_not_a_coordinate():
    """The UI writes '*unknown*' into empty fields."""
    assert GpsFix.build(latitude="*unknown*", longitude="*unknown*") is None


def test_out_of_range_latitude_is_rejected():
    assert GpsFix.build(latitude=91.0, longitude=0.0) is None


def test_out_of_range_longitude_is_rejected():
    assert GpsFix.build(latitude=0.0, longitude=181.0) is None


def test_null_island_is_rejected():
    """0,0 is the classic 'receiver has no idea' output, not a real position."""
    assert GpsFix.build(latitude=0.0, longitude=0.0) is None


def test_bad_optional_field_does_not_void_the_fix():
    """A garbled altitude must not throw away a good latitude/longitude."""
    fix = GpsFix.build(latitude=37.7749, longitude=-122.4194, altitude="*unknown*")
    assert fix is not None
    assert fix.altitude is None


# --- parse_gps: extraction from a live sys_status payload -------------------


def test_no_fix_yields_no_position(sys_status_nofix):
    """A router reporting 'Not fixed now' must yield no position at all."""
    assert parse_gps(sys_status_nofix) is None


def test_missing_gps_object_yields_no_position():
    assert parse_gps({}) is None


def test_a_real_fix_yields_a_position(sys_status_fix):
    fix = parse_gps(sys_status_fix)
    assert fix is not None
    assert fix.latitude == pytest.approx(12.34567)
    assert fix.longitude == pytest.approx(-65.43210)


def test_altitude_speed_and_heading_come_from_the_fix(sys_status_fix):
    """The JSON carries bare numbers; the rendered page adds 'meters ASL', 'kph'."""
    fix = parse_gps(sys_status_fix)
    assert fix.altitude == pytest.approx(83.6)
    assert fix.speed == pytest.approx(0.0)
    assert fix.heading == pytest.approx(0.0)


def test_utc_is_composed_from_the_separate_date_and_time_keys(sys_status_fix):
    """There is no `utc` key: the router splits it into `date` and `time`.

    Home Assistant's timestamp device_class needs ISO 8601 with an offset, so
    the two halves are recombined rather than passed through.
    """
    assert parse_gps(sys_status_fix).utc == "2026-08-15T22:15:30+00:00"


def test_a_time_without_a_fractional_part_still_parses(sys_status_fix):
    sys_status_fix["gps"]["time"] = "22:15:30"
    assert parse_gps(sys_status_fix).utc == "2026-08-15T22:15:30+00:00"


def test_an_unparsable_timestamp_does_not_void_the_position(sys_status_fix):
    """A garbled clock is not a reason to throw away good coordinates."""
    sys_status_fix["gps"]["date"] = "*unknown*"
    fix = parse_gps(sys_status_fix)
    assert fix is not None
    assert fix.utc is None


def test_fix_quality_fields_are_extracted(sys_status_fix):
    fix = parse_gps(sys_status_fix)
    assert fix.fix_type == "3D"
    assert fix.satellites == 6
    assert fix.hdop == pytest.approx(0.8)


def test_gps_accuracy_is_estimated_from_hdop(sys_status_fix):
    """HDOP is unitless; Home Assistant's gps_accuracy is metres.

    Multiplying by a ~5 m user-equivalent range error is the standard rule of
    thumb, and an approximate circle beats an implied pinpoint.
    """
    assert parse_gps(sys_status_fix).gps_accuracy == 4


def test_a_2d_fix_is_still_a_position(sys_status_fix):
    sys_status_fix["gps"]["fix"] = "2D"
    assert parse_gps(sys_status_fix) is not None


def test_coordinates_without_a_fix_are_rejected(sys_status_fix):
    """Guards the case we cannot yet observe: coordinates left behind in the
    JSON after lock is lost. Without a fix type they are last known, not now."""
    sys_status_fix["gps"]["fix"] = "NO FIX"
    assert parse_gps(sys_status_fix) is None


def test_a_missing_fix_field_is_not_a_position(sys_status_fix):
    del sys_status_fix["gps"]["fix"]
    assert parse_gps(sys_status_fix) is None


def test_an_error_still_wins_over_populated_coordinates(sys_status_fix):
    sys_status_fix["gps"]["error"] = "Not fixed now"
    assert parse_gps(sys_status_fix) is None


def test_the_fix_payload_omits_fields_the_router_did_not_supply(sys_status_fix):
    del sys_status_fix["gps"]["hdop"]
    payload = parse_gps(sys_status_fix).as_payload()
    assert "hdop" not in payload
    assert "gps_accuracy" not in payload
    assert payload["latitude"] == pytest.approx(12.34567)


# --- parse_modem ------------------------------------------------------------


def test_modem_status_is_extracted(sys_status_nofix):
    modem = parse_modem(sys_status_nofix)
    assert modem.signal_percent == 68
    assert modem.state == "connected"
    assert modem.internet_source == "wwan_only"


def test_signal_comes_from_wwan_not_the_display_string(sys_status_nofix):
    """networks.wwan.signal is the real reading; modem_signal is a rendering of it."""
    sys_status_nofix["modem_signal"] = "3%"
    assert parse_modem(sys_status_nofix).signal_percent == 68


def test_rssi_is_reported_in_dbm(sys_status_nofix):
    assert parse_modem(sys_status_nofix).rssi_dbm == -79


def test_radio_details_are_extracted(sys_status_nofix):
    modem = parse_modem(sys_status_nofix)
    assert modem.band == "LTE BAND 4"
    assert modem.mode == "4G"


def test_data_usage_counters_are_extracted(sys_status_nofix):
    modem = parse_modem(sys_status_nofix)
    assert modem.rx_bytes == 5528161218
    assert modem.tx_bytes == 3063252923


def test_carrier_and_apn_come_from_the_modem_block(sys_status_nofix):
    """auth.modem states these outright — no need to regex a display string."""
    modem = parse_modem(sys_status_nofix)
    assert modem.carrier == "TMOBILE"
    assert modem.apn == "fast.T-Mobile.com"


def test_carrier_falls_back_to_the_status_string():
    """Older firmware may not expose auth.modem; the display string still works."""
    modem = parse_modem({
        "internet_status": 'Connected to Cellular TMOBILE User Data Plan "fast.T-Mobile.com"'
    })
    assert modem.carrier == "TMOBILE"
    assert modem.apn == "fast.T-Mobile.com"


def test_missing_signal_is_none_not_zero():
    """An absent reading must not masquerade as a real 0% signal."""
    modem = parse_modem({"modem_state": "connected"})
    assert modem.signal_percent is None
    assert modem.rssi_dbm is None
    assert modem.rx_bytes is None


def test_empty_wwan_list_is_tolerated():
    """Unused interfaces come back as [] rather than {} — must not raise."""
    modem = parse_modem({"networks": {"wwan": []}})
    assert modem.signal_percent is None
