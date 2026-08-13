from unittest.mock import patch, MagicMock

import requests

from carfinder.vin import decode_vin


def _mock_response(results):
    resp = MagicMock()
    resp.json.return_value = {"Results": results}
    resp.raise_for_status.return_value = None
    return resp


@patch("carfinder.vin.requests.get")
def test_decode_vin_success(mock_get):
    mock_get.return_value = _mock_response(
        [
            {
                "Make": "HONDA",
                "Model": "Pilot",
                "ModelYear": "2012",
                "Trim": "EX-L",
                "BodyClass": "Sport Utility Vehicle (SUV)",
                "VehicleType": "MULTIPURPOSE PASSENGER VEHICLE (MPV)",
                "EngineCylinders": "6",
                "FuelTypePrimary": "Gasoline",
                "DriveType": "4WD/4-Wheel Drive/4x4",
                "PlantCountry": "UNITED STATES (USA)",
                "ErrorCode": "0",
                "ErrorText": "0 - VIN decoded clean.",
            }
        ]
    )

    decoded = decode_vin("5FNYF4H50CB012345")

    assert decoded is not None
    assert decoded["make"] == "HONDA"
    assert decoded["model"] == "Pilot"
    assert decoded["year"] == 2012
    assert decoded["trim"] == "EX-L"


@patch("carfinder.vin.requests.get")
def test_decode_vin_empty_results_returns_none(mock_get):
    mock_get.return_value = _mock_response([])
    assert decode_vin("INVALIDVIN") is None


def test_decode_vin_blank_input_returns_none():
    assert decode_vin("") is None
    assert decode_vin(None) is None


@patch("carfinder.vin.requests.get", side_effect=requests.RequestException("network error"))
def test_decode_vin_request_failure_returns_none(mock_get):
    assert decode_vin("5FNYF4H50CB012345") is None
