"""Offline waveform replay; no live ingestion, catalogue input or push calls.

The existing deployed picker provides P *hypotheses*, never verified phases.
Reference coordinates may be compared after locating, not fed into the solver.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import requests
from obspy import UTCDateTime, read

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from eew.epicenter_shadow import PhaseArrival, ShadowLocator, TabulatedTravelTimes  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--deployed-source', type=Path, required=True)
    parser.add_argument('--station-config', type=Path, required=True)
    parser.add_argument('--table', type=Path, required=True)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--ambient-archive', type=Path)
    args = parser.parse_args()
    root = args.audit_dir
    config = json.loads(args.station_config.read_text(encoding='utf-8'))
    allowed = {'ARGC','CRJC','HEL','OCA','PRV','RUS','SMAR','TUM','URI'}
    stations = {s['station']:s for p in config['seedlink']['providers']
                if p['id'] == 'earthscope_colombia' for s in p['stations'] if s['station'] in allowed}
    candidates = {r['payload']['event_id']:r['payload'] for r in json.loads((root/'candidates.json').read_text())}
    cases = json.loads((root/'delivered_comparisons.json').read_text(encoding='utf-8'))
    windows = []
    bulk = []
    for row in cases:
        c = candidates[row['event_id']]
        anchor = min(float(UTCDateTime(s['trigger_time'])) for s in c['stations'])
        windows.append((c,anchor))
        for station in stations.values():
            bulk.append(f"CM {station['station']} {station.get('location','00')} HHZ {UTCDateTime(anchor-90)} {UTCDateTime(anchor+150)}")
    archive = root/'location-nine-stations.mseed'
    if args.fetch and not archive.exists():
        response = requests.post('https://service.earthscope.org/fdsnws/dataselect/1/query',
            data='\n'.join(bulk)+'\n',headers={'Content-Type':'text/plain','User-Agent':'Seismik/0.4 (+https://seismik.org)'},timeout=55)
        response.raise_for_status()
        read(io.BytesIO(response.content))  # Validate before writing cache.
        archive.write_bytes(response.content)
        print(json.dumps({'download_bytes':len(response.content),'requested_windows':len(bulk)}),flush=True)
    stream = read(str(archive))
    stream.merge(method=0,fill_value=None)
    stream = stream.split()  # Gaps stay split and cannot masquerade as an onset.
    spec = importlib.util.spec_from_file_location('deployed_onset_picker',args.deployed_source/'eew/picking.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    locator = ShadowLocator(TabulatedTravelTimes(args.table))
    results = []
    for c,anchor in windows:
        observations, absent = [], []
        began = time.monotonic()
        for station in stations.values():
            selected = stream.select(network='CM',station=station['station'],channel='HHZ').slice(UTCDateTime(anchor-90),UTCDateTime(anchor+150))
            # Require one continuous trace spanning the requested analysis window.
            if len(selected) != 1 or float(selected[0].stats.starttime) > anchor-45 or float(selected[0].stats.endtime) < anchor+115:
                absent.append(station['station'])
                continue
            trace = selected[0]
            if np.ma.isMaskedArray(trace.data):
                absent.append(station['station'])
                continue
            onset = module.pick_p_onset(trace,anchor-30,anchor+110)
            if onset is not None:
                observations.append(PhaseArrival('CM.'+station['station'],station['latitude'],station['longitude'],onset.time,'P'))
        review = locator.review(observations)
        results.append({'event_id':c['event_id'],'detected_at':c['detected_at'],
            'missing_or_split_stations':absent,'hypothesis_station_ids':[p.station_id for p in observations],
            'review':review.to_dict(),'processing_seconds':round(time.monotonic()-began,3)})
        print(json.dumps(results[-1],ensure_ascii=False),flush=True)
    noise_results = []
    if args.ambient_archive:
        ambient = read(str(args.ambient_archive))
        ambient.merge(method=0,fill_value=None)
        ambient = ambient.split()
        start = min(float(tr.stats.starttime) for tr in ambient)
        for offset in (45,185):
            anchor = start+offset
            observations = []
            for station in stations.values():
                selected = ambient.select(network='CM',station=station['station'],channel='HHZ')
                if len(selected) != 1 or float(selected[0].stats.starttime) > anchor-40 or float(selected[0].stats.endtime) < anchor+110:
                    continue
                onset = module.pick_p_onset(selected[0],anchor-30,anchor+110)
                if onset is not None:
                    observations.append(PhaseArrival('CM.'+station['station'],station['latitude'],station['longitude'],onset.time,'P'))
            noise_results.append({'window_anchor':str(UTCDateTime(anchor)),
                                  'review':locator.review(observations).to_dict()})
    output = {'source':'archived_waveform_replay_not_live_validation',
              'station_count':len(stations),'case_count':len(results),
              'phase_identification':'existing_picker_P_hypotheses_only_no_S_classifier',
              'statuses':dict(Counter(r['review']['status'] for r in results)), 'cases':results,
              'ambient_controls':noise_results}
    (root/'epicenter-shadow-replay.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'summary':output['statuses'],'ambient_controls':noise_results}),flush=True)


if __name__ == '__main__':
    main()
