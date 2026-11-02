# Waves supplement and historical references — 2026-10-18

Published at https://waves.seismik.org/ and https://waves.seismik.org/#historicos.

## Archive

Six additive objects, 1,666,854 bytes, copied without replacing any original or the
2026-10-10 manifest. Private prefix:
`gs://seismik-15bbb-scientific-archive/imports/local-2026-10-10/data/supplements/2026-10-18/`.
Supplement manifest:
`gs://seismik-15bbb-scientific-archive/imports/local-2026-10-10/supplements/2026-10-18/manifest.json`.
Remote size/MD5 verified against every local original; each catalogue entry also carries SHA-256.
No IAM changes, new recipients or continuous capture were introduced.

Totals: 607 scientific files / 549,985,636 bytes; 561 MiniSEED files and five
separately browsable supplemental resources (two StationXML and three station surveys).
The audit MiniSEED has 30 contiguous segments across six stations and ten separate
windows, not 30 confirmed earthquakes. No magnitude or alert is inferred from it.

## Public history

Ten source-linked documentary cards: four Colombia, six worldwide. Magnitudes belong
to the cited SGC/USGS references, not Seismik. No waveform availability is claimed;
all ten have `waveform_status=not_linked`. Original sources checked by web research;
all seven distinct reference URLs also returned HTTP 200 during deployment checks.

## Runtime and evidence

- Cloud Build: `0cba6289-9417-4e89-ab91-4606f73030c4` (`us-east1`), SUCCESS.
- Image: `us-east1-docker.pkg.dev/seismik-15bbb/seismik/waves@sha256:a13b00aecff50a1ff08244628cb97efdfb268ee0288cdfc164a036d43bca4065`.
- Cloud Run: `seismik-waves-00015-wez`, 100% of service traffic after candidate smoke checks.
- Worker final version: `388a9ecf-f7f9-4c3a-8b61-db8303abfc40`, 100%.
- Backend image corresponds to implementation commit `4ad06c0`; final edge formatting
  fix is `a500cda`. The final Worker differs only by clearer file counts/kB formatting.
- 45 Waves pytest tests passed; edge tests and JS syntax checks passed.
- Candidate and live public summaries/history checked; private routes return 401 without a session.
- Existing approved support account displayed all five resources in production.
- Live StationXML and audit MiniSEED downloads succeeded; downloaded SHA-256 matched originals:
  `ecefe86e8d81401ea2c8decd89d6b669958643e212d2e591d8701e17d7e84d4d` (StationXML),
  `ac3d36a8d8c2cf905195878ce837631df85a6bccace4caf1b9844cc6a7c900b0` (MiniSEED).
- Viewer verified at first and last time window; raw gaps are never zero-filled.
- Screenshot: workspace `work/waves-update-20261018/waves-historical-live.png`.
- No detector, main API, dispatcher, mobile build, alert policy or scientific-validation status was changed.

## Rollback

Keep archive additions; they do not affect the old service. Restore the previously active
backend with `gcloud run services update-traffic seismik-waves --project=seismik-15bbb
--region=us-east1 --to-revisions=seismik-waves-00010-zvq=100` and the previous edge with
`wrangler versions deploy 45d762fe-6e94-4425-a6e5-ff4d78e3473b@100 --config waves/edge/wrangler.toml`.
No data deletion is required.
