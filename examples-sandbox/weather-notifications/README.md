# Background weather and notifications (sandbox)

A macOS LaunchAgent owns the keyboard while logged in. No Chrome window or
running Codex chat is required. It starts at login and restarts after failures.
The computer must be awake and the keyboard connected over USB.

- Animated current weather: San Francisco by default, refreshed hourly.
- Calendar: local EventKit events, including Google and iCloud accounts synced
  through macOS Calendar. Polls every ten seconds; reminds within the minute
  before a meeting. Skips all-day, canceled, and declined events.
- On-demand: authenticated loopback HTTP inbox and the `notify.py` command.
- Minimal black notification cards use large text and colored accents. The
  default duration is 60 seconds; new notices reset the return deadline.
  Afterwards, the latest cached weather returns, even if the network is down.

One USB worker serializes all writes. Weather fetching runs separately and
cannot replace an active notification. Only block 0 is erased/written. Returning
from a notification rewrites the small cached weather animation to that block;
this mode does not use the old resident-reel return pointer. Duplicate notice
IDs are suppressed, with a persisted return deadline for process restarts.

## Setup

Use a Python environment with the repository dependencies. First initialize the
[weather display](../weather-display/README.md), then stop its old worker.
Add Google/iCloud accounts in Calendar → Add Account and enable Calendars.
Authorize the included read-only helper interactively:

```sh
python examples-sandbox/weather-notifications/calendar_app.py --build
python examples-sandbox/weather-notifications/calendar_app.py --authorize
python examples-sandbox/weather-notifications/manage_service.py install \
  --seed-weather /absolute/path/to/current-weather.qgif
```

Calendar authorization may require macOS Full Access because EventKit has no
read-only permission category; the helper only reads events. The signed helper installs in `~/Library/Application Support/OpenKeyboardLCD`,
with its own Calendar privacy identity, independent of ChatGPT.
Google OAuth remains managed by macOS; no Google secret is stored in this repo.
This is a synced-calendar integration, not a direct Google Calendar API client.

Location and units: edit `../weather-display/weather.json`. Reloaded each hour.
Logs: `state/weather-notifications/service.log` and `error.log` (local only).
A Calendar-ready log confirms local read permission; it does not prove that a
specific remote account has finished syncing. Private event titles are not logged.

```sh
python examples-sandbox/weather-notifications/notify.py 'Team sync' 'In 1 minute' \
  --source Calendar --template calendar
python examples-sandbox/weather-notifications/notify.py 'Build complete' 'All checks passed' \
  --template success --duration 30
python examples-sandbox/weather-notifications/manage_service.py status
python examples-sandbox/weather-notifications/manage_service.py uninstall
```

Native local programs can POST the existing notification JSON schema to
`http://127.0.0.1:8765/notify`, with the bearer token from
`state/weather-notifications/inbox/token`. Prefer the Python `notifications.send`
helper so the token never appears in shell history. Tokens and queued content
stay in ignored local state. The endpoint does not accept browser-origin calls.
Slack and other apps need an explicit sender/integration; this does not scrape
all macOS Notification Center messages. Themes can override background, accent,
text, and muted colors. Cards show up to two title lines and one message line.

Failures during USB mutation leave a pending ledger and prevent automatic
rewrites on restart. Resolve the device/state mismatch before restarting;
do not erase or regenerate the state ledger to bypass this check. Network
failures preserve the previous weather and retry after five minutes. Calendar
permission failures retry every minute while other features remain available.
Logs are not currently rotated. Calendar reminders depend on the account's
local sync freshness and may arrive later after sleep or network outages.

Source, tests, and example configuration are shareable; runtime state, calendar
results, inbox tokens, and logs are excluded from Git. Status output uses a strict
allowlist and never dumps launchd environment variables. The LaunchAgent supplies
an empty API-key variable; this service does not use an OpenAI API key.

## Follow the Mac display's sleep state

`display.json` selects `sleep_mode`: `animation` (default, dim moon and floating
z's), `black` (a black image), or `disabled`. Restart the service after changing
this file. A black image is not a verified backlight/power-off command.

The worker polls macOS display power once a second and requires a stable state
for three seconds. All online displays must sleep before the keyboard sleeps;
any awake display restores the newest cached weather and clears the reminder
timer. Notifications received during sleep are discarded, including queued
notices when waking, so old reminders do not replace the returning weather.
Weather can refresh its cache while the displays are off. No screen capture or
Accessibility permission is required. Unknown/empty display queries preserve
the last state rather than guessing that the displays are asleep.

This follows display power, not screen locking or a screen saver. It uses Apple's
[CGDisplayIsAsleep](https://developer.apple.com/documentation/coregraphics/cgdisplayisasleep(_:))
and [CGGetOnlineDisplayList](https://developer.apple.com/documentation/coregraphics/cggetonlinedisplaylist(_:_:_:)).
Each transition uses the existing block-0 updater, so changes include USB upload
latency. If the entire Mac sleeps or USB power is removed before an upload can
finish, a sleep animation cannot be guaranteed; the normal interrupted-write
checks still apply. Software transitions and payload sizes are tested; an actual
screen-off/wake cycle still needs observation on the connected hardware.
