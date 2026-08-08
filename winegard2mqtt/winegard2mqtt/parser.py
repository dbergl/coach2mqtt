"""Pure parsing of Winegard ConnecT responses. No I/O.

Split deliberately in two halves:

* ``GpsFix.build`` validates already-extracted values. These rules hold no
  matter what the router calls its fields, so they are testable today.
* ``parse_gps`` pulls candidate values out of a live ``sys_status`` payload.
  The key names used on a real fix are **not yet known** — the unit has no GNSS
  antenna fitted, so it has never produced one. See the design doc. Until a fix
  is captured, extraction deliberately yields nothing rather than guessing.
"""

import re
from dataclasses import dataclass, asdict
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


@dataclass(frozen=True)
class GpsFix:
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    utc: Optional[str] = None

    @classmethod
    def build(cls, latitude=None, longitude=None, altitude=None,
              speed=None, heading=None, utc=None) -> Optional["GpsFix"]:
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

        return cls(
            latitude=lat,
            longitude=lon,
            altitude=_number(altitude),
            speed=_number(speed),
            heading=_number(heading),
            utc=utc_text,
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


def parse_gps(status: dict) -> Optional[GpsFix]:
    """Extract a fix from a sys_status payload, or None when there is none."""
    gps = status.get("gps")
    if not isinstance(gps, dict):
        return None
    if gps.get("error"):
        return None

    # NOTE: deferred. No fix has ever been observed from this hardware, so the
    # keys carrying coordinates are unknown. GpsFix.build below is already
    # correct and tested; only this extraction needs filling in, against a
    # captured fix rather than a guess.
    return GpsFix.build(
        latitude=gps.get("latitude"),
        longitude=gps.get("longitude"),
        altitude=gps.get("altitude"),
        speed=gps.get("speed"),
        heading=gps.get("heading"),
        utc=gps.get("utc"),
    )


_SIGNAL_RE = re.compile(r"(-?\d+)\s*%")
_CARRIER_RE = re.compile(r"Connected to Cellular\s+(\S+)")
_APN_RE = re.compile(r'Plan\s+"([^"]+)"')


def _integer(value) -> Optional[int]:
    number = _number(value)
    return None if number is None else int(number)


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
