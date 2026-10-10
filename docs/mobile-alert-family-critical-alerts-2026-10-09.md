# Android alarms, automatic family location, and iOS Critical Alerts

Implementation published 2026-10-09; status updated 2026-10-10.
Build 61 is available to Google Play internal testers and the internal TestFlight
group. Signed iOS provisioning and application entitlements were verified in
GitHub. The compatible API and dispatcher were deployed and readiness checked.
This is not an external TestFlight review, general-store promotion or scientific validation.

## Android

- Critical FCM messages remain high-priority data-only. The background handler
  posts the alarm on receipt; tapping does not replay it.
- Local notifications use FLAG_INSISTENT, alarm audio usage, a 60-second timeout
  and a `Silenciar` notification action. Android can stop insistent audio when
  the notification panel is opened. User permission, volume, channel choices,
  force-stop restrictions and OEM battery rules still apply.
- New sound channel `seismic_critical_alarm_v2`; legacy muted/lowered channels
  remain respected. No change to server push targeting or critical policy.
- Remember an alert only after successful notification submission. The full-screen
  close button says `SILENCIAR`, not an unsubmitted safety confirmation.

## Family consent and semantics

- Account-authenticated PUT `/v1/family/automatic-location` requires an actual
  boolean and membership. Default off; disabling stops future automatic shares
  and removes the currently automatic location, without deleting a manual share.
  DELETE `/v1/family/location` also revokes the preference.
- Only real critical push attempts in production trigger the helper. Local tests,
  flagged simulations, dry-runs, unlinked phones and registrations older than one
  hour do not. No family sharing from noncritical reports.
- Uses the last coordinates registered by a linked target phone, rounded to two
  decimals, for one hour. **Registration time is not a GPS observation timestamp.**
  It does not establish the person's current position or confirm receipt of the
  alert. UI labels it as last registered location, not live GPS.
- No coordinates go into the family push. A member retrieves them through the
  private circle endpoint. Notice status is `location_only`; it never claims safe
  or need_help. Older check-ins for another event are hidden; newer manual check-ins
  retain priority even when they use an official catalog ID.
- Reuses the existing family stream/dispatcher; no new service or paid dependency.
  Requires deployment of the compatible API and dispatcher before mobile rollout.

## iOS

- Optional family automatic-location control, with the same consent and limitations.
- Critical Alert permission status (refreshed on app resume), shortcut to system
  settings, magnitude threshold, and a local delayed notification test to allow
  locking the phone. The test neither creates an earthquake nor contacts family.
- Apple approved Critical Alerts for `com.seismik.app` per the owner's email.
  This is an entitlement approval, not approval of this build or scientific validation.
- TestFlight workflow checks that a regenerated App Store distribution profile
  contains `com.apple.developer.usernotifications.critical-alerts=true`, then checks
  the actual signed application's entitlement. Set `critical_alerts_approved=true`
  only for a matching profile; do not merely reuse an old profile.

## Verification and release gates

- Backend pytest suite passed after installing missing test-environment dependencies
  (google-cloud-pubsub, requests-oauthlib, fakeredis Lua support). Ruff and mypy pass.
- Android debug APK compiled; all 146 Flutter tests pass. Analysis passes. The notification mock verifies the
  repeating flag, timeout and silence action. Mock tests cannot prove physical sound.
- No Android was connected via adb. Still need delivery with screen locked, app
  backgrounded, silence/close, duplicate and permission-denied tests on a real device.
- macOS GitHub builds and native tests passed; the provisioning profile was regenerated
  after enabling Critical Alerts and the signed entitlement was checked.
  Still need a real iPhone test (silent mode/Focus, permission enabled and denied).
- Mobile changes were integrated with the other-PC authentication updates in an
  isolated release branch. Never push an old divergent primary tree wholesale.

UniCaldas/UNAL review should receive a clearly labeled experimental build and test
evidence, not a claim of guaranteed early warning or emergency-service replacement.
