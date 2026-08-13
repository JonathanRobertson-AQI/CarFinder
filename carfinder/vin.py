"""VIN decoding via NHTSA's free, official vPIC API.

No API key required. Docs: https://vpic.nhtsa.dot.gov/api/
"""
from __future__ import annotations

from typing import Any, Optional

import requests

VPIC_DECODE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"

# Fields from the vPIC response we care about, mapped to friendlier names.
_FIELD_MAP = {
    "Make": "make",
    "Model": "model",
    "ModelYear": "year",
    "Trim": "trim",
    "BodyClass": "body_class",
    "VehicleType": "vehicle_type",
    "EngineCylinders": "engine_cylinders",
    "FuelTypePrimary": "fuel_type",
    "DriveType": "drive_type",
    "PlantCountry": "plant_country",
    "ErrorCode": "error_code",
    "ErrorText": "error_text",
}


def decode_vin(vin: str, timeout: float = 10.0) -> Optional[dict[str, Any]]:
    """Decode a VIN using the NHTSA vPIC API.

    Returns a dict of decoded fields, or None if the request fails or the
    VIN can't be decoded. A non-"0" ``error_code`` indicates NHTSA could not
    fully decode the VIN (e.g. it's invalid or incomplete).
    """
    vin = (vin or "").strip().upper()
    if not vin:
        return None
    try:
        response = requests.get(VPIC_DECODE_URL.format(vin=vin), timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return None

    payload = response.json()
    results = payload.get("Results") or []
    if not results:
        return None

    raw = results[0]
    decoded: dict[str, Any] = {"vin": vin}
    for source_key, dest_key in _FIELD_MAP.items():
        value = raw.get(source_key)
        decoded[dest_key] = value if value not in ("", None) else None

    if decoded.get("year"):
        try:
            decoded["year"] = int(decoded["year"])
        except (TypeError, ValueError):
            decoded["year"] = None

    return decoded
