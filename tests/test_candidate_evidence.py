"""Regression evidence, not a scientific accuracy/validation dataset."""
import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

from api.history import _preliminary_event
from eew.candidate_evidence import catalogue_phase_consistent, public_candidate_location
from eew.config import OfficialReportsSettings
from eew.models import EarthquakeCandidate, OfficialReport, StationTrigger
from eew.official import match_report

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/seedlink_audit_2026_10_24.json').read_text(encoding='utf-8'))


def candidate(payload):
    allowed = {field.name for field in fields(EarthquakeCandidate)}
    station_fields = {field.name for field in fields(StationTrigger)}
    args = {key: value for key, value in payload.items() if key in allowed}
    args['stations'] = tuple(StationTrigger(**{key: value for key, value in station.items() if key in station_fields}) for station in payload['stations'])
    return EarthquakeCandidate(**args)


def report(payload):
    return OfficialReport(source_id=payload['source'], agency=payload['source'], jurisdiction='catalogue',
                          official_event_id=payload['event_id'], origin_time=payload['origin_time'],
                          latitude=payload['latitude'], longitude=payload['longitude'],
                          depth_km=payload['depth_km'], magnitude=payload['magnitude'],
                          updated_at=None, magnitude_type=payload.get('magnitude_type'),
                          place=payload.get('place'), review_status='catalogue',
                          official_url=payload['url'])


@pytest.mark.parametrize('row', FIXTURES, ids=lambda row: row['candidate']['event_id'][:8])
def test_replayed_alert_quorums_are_not_confirmed_by_time_alone(row):
    observed = candidate(row['candidate'])
    for pair in row['reports']:
        assert catalogue_phase_consistent(observed, report(pair['report'])) is pair['expected']


def test_nearby_small_sismo_cannot_borrow_impossibly_early_distant_stations():
    row = next(row for row in FIXTURES if row['candidate']['event_id'].startswith('6f428257'))
    observed, official = candidate(row['candidate']), report(row['reports'][0]['report'])
    # Even a permissive centroid/time envelope cannot bypass the physical veto.
    assert match_report(observed, official, OfficialReportsSettings(max_distance_km=600)) is None


def test_one_sensor_duplicates_missing_depth_and_nan_cannot_confirm():
    row = FIXTURES[1]
    observed, official = candidate(row['candidate']), report(row['reports'][0]['report'])
    assert catalogue_phase_consistent(observed, official)
    assert not catalogue_phase_consistent(replace(observed, stations=observed.stations[:1]), official)
    assert not catalogue_phase_consistent(replace(observed, stations=(observed.stations[0],) * 3), official)
    assert not catalogue_phase_consistent(observed, replace(official, depth_km=None))
    assert not catalogue_phase_consistent(observed, replace(official, latitude=float('nan')))


def test_api_never_turns_station_centroids_into_epicentres():
    for row in FIXTURES:
        item = _preliminary_event(row['candidate'])
        assert item is not None
        assert item['latitude'] is None and item['longitude'] is None
        assert item['confirmation_status'] == 'unconfirmed'
        assert item['location_method'] == 'unlocated'
        assert item['station_centroid']['is_epicenter'] is False
        assert item['preliminary'] is True
        assert item['detected_at'] == row['candidate']['detected_at']


def test_invalid_centroid_is_not_exposed_and_hypothesis_is_not_validated():
    fields = public_candidate_location({'estimated_latitude': True, 'estimated_longitude': float('nan'),
                                        'association_quality': {'status': 'experimental_consistent'}})
    assert fields['station_centroid'] is None
    assert fields['latitude'] is None
    assert fields['confirmation_status'] == 'unconfirmed'
