from dataclasses import replace

import numpy as np
import pytest

from eew.epicenter_shadow import (
    LocationSettings,
    PhaseArrival,
    ProgressiveLocationReview,
    ShadowLocator,
    distance_deg,
)


class ConstantVelocity:
    """Independent synthetic medium; tests are not scientific validation."""
    def predict(self, depth, distance, phases):
        return np.hypot(np.asarray(distance)*111.195, depth)/np.where(phases == 'P', 6., 3.5)


COORDS = [(5.,-74.), (6.,-75.), (7.,-74.5), (7.5,-72.5), (5.,-72.), (4.,-73.5)]


def arrivals(*, phases=('P','S'), noise=0.):
    result = []
    rng = np.random.default_rng(592)
    for i,(lat,lon) in enumerate(COORDS):
        km = float(distance_deg(6.,-73.5,lat,lon))*111.195
        for phase in phases:
            seconds = np.hypot(km,30.)/(6 if phase == 'P' else 3.5)
            result.append(PhaseArrival(str(i),lat,lon,1_700_000_000+seconds+rng.normal(0,noise),phase))
    return result


def test_joint_phases_recover_source_without_catalogue_input():
    review = ShadowLocator(ConstantVelocity()).review(arrivals(noise=.08))
    assert review.status == 'experimental_consistent'
    assert float(distance_deg(review.latitude,review.longitude,6.,-73.5))*111.195 < 3
    assert abs(review.depth_km-30) < 5
    assert review.station_removal_shift_km < 5
    assert review.validation_status == 'experimental_unvalidated'
    assert review.public_alert_eligible is False


def test_four_station_fit_cannot_claim_a_solution():
    review = ShadowLocator(ConstantVelocity()).review(arrivals()[:8])
    assert review.status == 'insufficient_data'
    assert review.latitude is None


def test_noisy_pick_is_not_silently_dropped_to_make_solution_pass():
    picks = arrivals()
    picks[0] = replace(picks[0],time=picks[0].time+12)
    review = ShadowLocator(ConstantVelocity()).review(picks)
    assert review.status == 'ambiguous'
    assert 'incoherent_arrivals' in review.reasons
    assert review.phase_count == 12


def test_plane_wave_is_not_a_confirmed_colombian_source():
    picks = [PhaseArrival(str(i),lat,lon,1_700_000_000+2*lat+3*lon,'P')
             for i,(lat,lon) in enumerate(COORDS)]
    review = ShadowLocator(ConstantVelocity()).review(picks)
    assert review.status == 'ambiguous'
    assert 'distant_wavefront_not_excluded' in review.reasons
    assert review.plane_wave_rms_seconds < .001
    assert not review.public_alert_eligible


def test_p_only_fit_does_not_claim_resolved_depth():
    review = ShadowLocator(ConstantVelocity()).review(arrivals(phases=('P',)))
    assert review.status == 'ambiguous'
    assert 'p_only_depth_ambiguous' in review.reasons


@pytest.mark.parametrize('field,value', [('latitude',float('nan')),('sigma_seconds',0),
                                       ('phase','PKIKP'),('longitude',190)])
def test_invalid_observations_fail_closed(field,value):
    picks = arrivals()
    picks[0] = replace(picks[0],**{field:value})
    assert ShadowLocator(ConstantVelocity()).review(picks).status == 'rejected'


def test_s_before_p_and_duplicate_phase_are_rejected():
    picks = arrivals()
    picks[1] = replace(picks[1],time=picks[0].time-1)
    assert ShadowLocator(ConstantVelocity()).review(picks).status == 'rejected'
    assert ShadowLocator(ConstantVelocity()).review(arrivals()+arrivals()[:1]).status == 'rejected'


def test_input_is_bounded_before_grid_allocation():
    review = ShadowLocator(ConstantVelocity()).review(arrivals()*3)
    assert review.reasons == ('observation_limit',)


def test_progressive_update_retains_later_stations_and_recomputes_after_rate_limit():
    worker = ProgressiveLocationReview(ShadowLocator(ConstantVelocity()))
    picks = arrivals()
    now = max(p.time for p in picks)
    first = worker.update('one',picks[:8],now=now)
    assert first.status == 'insufficient_data'
    assert worker.update('one',picks[8:],now=now+1).status == 'pending'
    # Repeated input cannot bypass the CPU rate limit, nor lose queued picks.
    assert worker.update('one',[],now=now+2).status == 'pending'
    final = worker.update('one',[],now=now+6)
    assert final.status == 'experimental_consistent'
    assert final.station_count == 6
    assert worker.update('one',[],now=now+7) is final


def test_progressive_events_are_isolated_bounded_and_expire():
    worker = ProgressiveLocationReview(ShadowLocator(ConstantVelocity()),maximum_events=2)
    picks = arrivals()
    now = max(p.time for p in picks)
    worker.update('one',picks[:6],now=now)
    review = worker.update('two',picks[6:],now=now)
    assert review.station_count == 3
    worker.update('three',picks[:4],now=now)
    assert worker.pending_count == 2
    worker.update('four',[],now=now+241)
    assert worker.pending_count == 1
    assert worker.update('four',picks,now=now+300).status == 'rejected'


def test_missing_travel_times_and_oversized_grid_fail_closed():
    class MissingTable:
        def predict(self, depth, distance, phases):
            return np.full(np.broadcast_arrays(depth,distance)[0].shape,np.nan)

    assert ShadowLocator(MissingTable()).review(arrivals()).reasons == ('no_finite_solution',)
    with pytest.raises(ValueError):
        LocationSettings(bounds=(-80,80,-170,170))
    with pytest.raises(ValueError):
        LocationSettings(maximum_rms_seconds=float('nan'))
