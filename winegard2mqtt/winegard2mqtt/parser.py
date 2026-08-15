"""Pure parsing of Winegard ConnecT responses. No I/O.

Split deliberately in two halves:

* ``GpsFix.build`` validates already-extracted values. These rules hold no
  matter what the router calls its fields.
* ``parse_gps`` pulls those values out of a live ``sys_status`` payload.

The fixed-state schema was captured from the live unit on 2026-08-15, once a
GNSS antenna was fitted. ``sys_status.gps`` carries the position directly, as
signed decimal degrees in strings, so the rendered ``gps.htm`` page is not
needed as a source — it shows the same values with units and hemisphere letters
glued on. The one surprise is that there is no ``utc`` key: the router splits
the timestamp into ``date`` and ``time``.
"""

import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

# Values the web UI writes into fields it has nothing for.
_PLACEHOLDERS = {"*unknown*", "unknown", "", "-", "n/a"}


def _number(value) -> Optional[float]:
    """Coerce a router-supplied value to a float, or None if it isn't one."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in _PLACEHOLDERS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _integer(value) -> Optional[int]:
    number = _number(value)
    return None if number is None else int(number)


# HDOP is a unitless geometry multiplier; Home Assistant's gps_accuracy is
# metres. Scaling by a nominal user-equivalent range error is the usual rule of
# thumb — crude, but an honest circle beats an implied pinpoint.
_UERE_METRES = 5.0


@dataclass(frozen=True)
class GpsFix:
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    utc: Optional[str] = None
    fix_type: Optional[str] = None
    satellites: Optional[int] = None
    hdop: Optional[float] = None
    gps_accuracy: Optional[int] = None

    @classmethod
    def build(cls, latitude=None, longitude=None, altitude=None,
              speed=None, heading=None, utc=None, fix_type=None,
              satellites=None, hdop=None) -> Optional["GpsFix"]:
        """Validate extracted values into a fix, or None if they aren't one.

        A partial or implausible position is treated as no position at all: it
        is better for the tracker to admit it doesn't know than to publish a
        coordinate that looks authoritative and isn't.
        """
        lat, lon = _number(latitude), _number(longitude)
        if lat is None or lon is None:
            return None
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            return None
        # Null Island: what a receiver emits when it has nothing.
        if lat == 0.0 and lon == 0.0:
            return None

        utc_text = None if utc is None or str(utc).strip().lower() in _PLACEHOLDERS \
            else str(utc).strip()

        dilution = _number(hdop)
        return cls(
            latitude=lat,
            longitude=lon,
            altitude=_number(altitude),
            speed=_number(speed),
            heading=_number(heading),
            utc=utc_text,
            fix_type=fix_type,
            satellites=_integer(satellites),
            hdop=dilution,
            gps_accuracy=None if dilution is None
            else round(dilution * _UERE_METRES),
        )

    def as_payload(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class ModemStatus:
    signal_percent: Optional[int] = None
    rssi_dbm: Optional[int] = None
    band: Optional[str] = None
    mode: Optional[str] = None
    rx_bytes: Optional[int] = None
    tx_bytes: Optional[int] = None
    carrier: Optional[str] = None
    apn: Optional[str] = None
    state: Optional[str] = None
    internet_source: Optional[str] = None
    internet_status: Optional[str] = None

    def as_payload(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


# What the router reports in `fix` when it has actually locked on. Anything
# else — "NO FIX", a missing key — means any coordinates still present are
# left over from a previous lock rather than current.
_FIX_TYPES = {"2D", "3D"}

# `date` is YYYY/MM/DD, `time` is HH:MM:SS.f — with the fractional part
# sometimes absent.
_UTC_FORMATS = ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S")


def _utc_timestamp(date, time) -> Optional[str]:
    """Recombine the router's split date/time into ISO 8601, or None.

    Home Assistant's ``timestamp`` device class rejects anything without an
    offset, and the page labels this field UTC, so the offset is stated
    explicitly rather than left to the consumer to assume.
    """
    if date is None or time is None:
        return None
    stamp = f"{str(date).strip()} {str(time).strip()}"
    for fmt in _UTC_FORMATS:
        try:
            parsed = datetime.strptime(stamp, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc).isoformat()
    return None


def parse_gps(status: dict) -> Optional[GpsFix]:
    """Extract a fix from a sys_status payload, or None when there is none."""
    gps = status.get("gps")
    if not isinstance(gps, dict):
        return None
    if gps.get("error"):
        return None

    fix_type = str(gps.get("fix") or "").strip().upper()
    if fix_type not in _FIX_TYPES:
        return None

    return GpsFix.build(
        latitude=gps.get("latitude"),
        longitude=gps.get("longitude"),
        altitude=gps.get("altitude"),
        speed=gps.get("speed"),
        heading=gps.get("heading"),
        utc=_utc_timestamp(gps.get("date"), gps.get("time")),
        fix_type=fix_type,
        satellites=gps.get("satellites"),
        hdop=gps.get("hdop"),
    )


_SIGNAL_RE = re.compile(r"(-?\d+)\s*%")
_CARRIER_RE = re.compile(r"Connected to Cellular\s+(\S+)")
_APN_RE = re.compile(r'Plan\s+"([^"]+)"')


def _section(status: dict, *path) -> dict:
    """Walk a nested path, returning {} for anything missing or not a dict.

    Unused interfaces come back from the router as ``[]`` rather than ``{}``,
    so a plain ``.get`` chain is not enough.
    """
    node = status
    for key in path:
        if not isinstance(node, dict):
            return {}
        node = node.get(key)
    return node if isinstance(node, dict) else {}


def parse_modem(status: dict) -> ModemStatus:
    """Extract modem telemetry. Always returns a status; fields may be None.

    Prefers the structured sources — ``networks.wwan`` for the radio and
    ``auth.modem`` for the SIM — over the human-readable ``modem_signal`` and
    ``internet_status`` strings, which are renderings of the same data. The
    string forms remain as a fallback for firmware that lacks the structures.
    """
    wwan = _section(status, "networks", "wwan")
    modem = _section(status, "auth", "modem")

    signal = _integer(wwan.get("signal"))
    if signal is None:
        match = _SIGNAL_RE.search(str(status.get("modem_signal", "")))
        signal = int(match.group(1)) if match else None

    internet_status = status.get("internet_status") or status.get("modem_status") or ""
    carrier = modem.get("carrier") or modem.get("provider")
    apn = modem.get("apn")
    if not carrier:
        match = _CARRIER_RE.search(internet_status)
        carrier = match.group(1) if match else None
    if not apn:
        match = _APN_RE.search(internet_status)
        apn = match.group(1) if match else None

    return ModemStatus(
        signal_percent=signal,
        rssi_dbm=_integer(wwan.get("rssi")),
        band=wwan.get("band"),
        mode=wwan.get("mode"),
        rx_bytes=_integer(wwan.get("rx_bytes")),
        tx_bytes=_integer(wwan.get("tx_bytes")),
        carrier=carrier,
        apn=apn,
        state=status.get("modem_state"),
        internet_source=status.get("internet_source"),
        internet_status=internet_status or None,
    )
