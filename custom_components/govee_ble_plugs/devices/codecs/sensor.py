"""Govee sensor broadcast parsing.

The large Govee thermo-hygrometer family (H5072/H5075/H5101/H5102/H5074/… ) broadcasts a
packed 24-bit temp+humidity value plus a battery byte inside the ``0xEC88`` manufacturer AD.
This parser is defensive: it only returns values that pass the spec's range gates, so a model
whose layout differs reports nothing (unavailable) rather than wrong data.

Note: HA's ``manufacturer_data`` is keyed by company id with the id bytes stripped, so we look
up ``0xEC88`` and walk the remaining bytes.
"""
from __future__ import annotations

from typing import Optional

GOVEE_COMPANY_ID = 0xEC88

_TEMP_MIN, _TEMP_MAX = -40.0, 100.0
_HUM_MIN, _HUM_MAX = 0.0, 100.0


def _decode_packed_th(b: bytes) -> Optional[tuple[float, float]]:
    """Decode 3 packed bytes -> (temp_c, humidity_pct), or None if invalid.

    raw = (b0&0x7F)<<16 | b1<<8 | b2 ; MSB of b0 = negative-temp sign.
    temp_c = (raw // 1000) / 10 ; humidity = (raw % 1000) / 10.
    """
    if len(b) < 3:
        return None
    b0, b1, b2 = b[0], b[1], b[2]
    if b0 == 0x7F or (b0, b1, b2) == (0xFF, 0xFF, 0xFF):
        return None
    negative = bool(b0 & 0x80)
    raw = ((b0 & 0x7F) << 16) | (b1 << 8) | b2
    temp = (raw // 1000) / 10.0
    if negative:
        temp = -temp
    hum = (raw % 1000) / 10.0
    if not (_TEMP_MIN <= temp <= _TEMP_MAX and _HUM_MIN <= hum <= _HUM_MAX):
        return None
    return temp, hum


def parse_th_broadcast(manufacturer_data: dict[int, bytes]) -> Optional[dict]:
    """Parse a thermo-hygrometer advert into ``{temperature, humidity, battery}``.

    Returns None if no Govee TH payload is recognised. Tries the documented offsets of the
    packed value within the 0xEC88 manufacturer payload and accepts the first in-range hit.
    """
    data = manufacturer_data.get(GOVEE_COMPANY_ID)
    if not data:
        return None
    # Offset 1 = H5072/75/H5101/H5102 (flags byte then packed+battery); 3 = pactType-prefixed.
    for off in (1, 3, 0, 2):
        if len(data) >= off + 4:
            th = _decode_packed_th(data[off:off + 3])
            if th is not None:
                battery = data[off + 3]
                if 0 <= battery <= 100:
                    temp, hum = th
                    return {"temperature": temp, "humidity": hum, "battery": battery}
    return None
