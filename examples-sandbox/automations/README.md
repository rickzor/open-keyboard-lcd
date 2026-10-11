# Sandbox: background LCD automation prototypes

**Mostly untested end to end.** See the [validation matrix](../README.md) before
using these prototypes. Local rendering and automated tests do not establish
on-keyboard reliability or successful live app integration.

These examples run locally with the independent driver. They are **not installed
or started automatically**. A single Python process owns the display and prevents
weather, meeting alerts, and GIF updates from racing each other.

| Config | Behavior |
| --- | --- |
| `weather.json` | Animated weather every 30 minutes; San Francisco, CA by default |
| `meetings.json` | Apple Calendar/iCal alerts within the minute before a timed event, then restores the previous GIF |
| `giphy.json` | A new G-rated random GIF tagged `cute animals` every hour |
| `combined.json` | Both timed feeds plus meeting priority; hourly GIF wins coincident updates, weather appears halfway through the hour |

Intervals start when the process starts, not at wall-clock hour boundaries.
Only one process should own the keyboard. Do not run three separate USB runners.

## Preview without touching USB

From the repository root, after `./setup.sh`:

```sh
.venv/bin/python examples-sandbox/automations/lcd_automations.py demo
.venv/bin/python examples-sandbox/automations/lcd_automations.py once --config examples-sandbox/automations/weather.json
```

The default output is `state/automation-preview/current.gif`. Demo also produces
`meeting-preview.gif` and exercises restoration using sample data. Weather-only
`once` fetches actual current conditions. Change `latitude`, `longitude`,
`location`, and `units` (`fahrenheit` or `celsius`) in a copied config for another
location. There is no location permission prompt or automatic location tracking.

The weather widget has a two-second animated icon: pulsing sun, drifting clouds,
falling rain/snow, fog, or lightning, with readable stationary text. Data comes
from [Open-Meteo](https://open-meteo.com/en/docs); review its usage terms for your
integration. Network failures retain the previous display.

## Opt into a single managed keyboard slot

**Initialization replaces every existing keyboard GIF with one sample image.**
It does not recover unknown images from the keyboard. Keep your source files.
The normal driver now also accepts a complete two-image set:

```sh
./rt82 replace-all first.gif second.gif
```

Initialize the example's own state once, then run the chosen config:

```sh
.venv/bin/python examples-sandbox/automations/lcd_automations.py init --usb --replace-all-slots --state state/automation-usb
.venv/bin/python examples-sandbox/automations/lcd_automations.py run --usb --state state/automation-usb --config examples-sandbox/automations/weather.json
```

`run` remains in the foreground; it can be supervised by your preferred process
manager. No launchd job, cron job, or Codex automation is installed by these examples.
Stop with Ctrl-C. If stopped during an alert, restart with the same state directory
to restore after expiry. Keep preview and USB state directories separate.

Every update rewrites a **complete one-image set** using the known batch path.
This does not depend on the unresolved targeted-erase behavior. It does write
flash regularly; endurance is unknown. Images are bounded to 512 KiB, not because
that is the device limit, but to bound transfer time. Writes are serialized and
unchanged encoded images skip writes. These examples are not a RAM framebuffer.

Metadata checks reject another tool's changed layout. They cannot detect payload
changes with identical metadata, so exclusive ownership remains required. An
interrupted write leaves a persistent pending marker and stops further writes;
explicit `init --usb --replace-all-slots` is the recovery operation. The normal
CLI's cached set is separate and must not be used to restore the automation set.

## Apple Calendar / iCal

The helper uses **EventKit**, which reads calendars synced into macOS Calendar,
including iCloud and Google Calendar accounts. It does not read an `.ics` URL or require iCloud
credentials. macOS 14+ and Xcode Command Line Tools are required:

```sh
examples-sandbox/automations/build-calendar-reader.sh
examples-sandbox/automations/calendar-reader --authorize
```

The second command prompts for macOS Calendar access. Although Apple's API calls
this “full access,” this helper only queries events and never modifies them.
If macOS denies access, enable Calendar access for the responsible terminal/helper
in System Settings. Authorize in the same execution context used to run it.
The compiled helper is local and ignored by Git. See Apple's
[EventKit access documentation](https://developer.apple.com/documentation/eventkit/accessing-the-event-store)
and [usage-description requirement](https://developer.apple.com/documentation/bundleresources/information-property-list/nscalendarsfullaccessusagedescription).

Run `meetings.json` or `combined.json` after initialization. Polling occurs every
10 seconds; alerts trigger when an event starts in 1–60 seconds. All-day,
cancelled, and declined events are excluded. The alert remains until 15 seconds
after the start, then restores the exact pre-alert image. Overlapping alerts
retain the original restoration snapshot and extend its lifetime. Event keys
include start time and are deduplicated across restarts. Default wording is
“Upcoming meeting”; set `show_meeting_titles` to true to display private titles.
No event titles are sent to weather/GIPHY or written to logs. Rendered images
and local state may contain titles if enabled; protect your state directory.

Timing is best effort: sleep, permissions, polling, encoding, and USB transfer
latency can delay or miss alerts. This is a supplementary display, not a calendar
notification replacement. For offline testing, `calendar_fixture` can point to a
JSON array with `id`, `title`, and Unix-epoch `start`, plus optional `all_day` and
`declined` fields.

## GIPHY: fit width, then crop vertically

Supply your own `GIPHY_API_KEY` through the environment; do not put it in the
config or repository. The example requests the random endpoint with `rating=g`
and checks the response rating. Missing/rejected keys or failed downloads retain
the previous image. No API key was used to test the live integration here.

It downloads the **original rendition**, resizes proportionally to **240 pixels
wide**, then center-crops the top and bottom to **135 pixels tall**. If the scaled
image is shorter, it pads vertically with black. It adds the encoder's extra
black row. It uses
at most 24 frames at 10 FPS and overlays “Powered By GIPHY.” Source downloads are
bounded to 8 MB. Crop can remove peripheral text/subjects; there is no smart crop.

G-rating is a useful filter, **not a workplace-safety guarantee**. For stricter
control, set `approved_giphy_ids` to an explicit list of IDs you have reviewed;
nonlisted random selections are rejected. An empty list allows no GIFs.

Review [GIPHY's API requirements](https://developers.giphy.com/docs/api/) before
using this example in a deployed integration: GIPHY restricts storing/caching its
media without explicit approval and specifies attribution. A keyboard stores
encoded media in flash; this example's storage/restore behavior requires resolving
that requirement with GIPHY. The code is an opt-in integration example, not a
claim of approved GIPHY distribution. Old unreferenced local assets are removed,
but active and restorable GIFs must remain available until replaced.

## Validation status

Automated tests cover proportional width fitting and vertical cropping/padding, animated weather, event timing and
exclusions, alert overlap/restart restoration, interrupted writes, feed priority,
and one/two-image protocol counts and backup loading. The Calendar helper is
compiled locally; authorization and live calendar results require the user's
macOS permission. Live GIPHY needs a key. One/two-image writes require visual
confirmation on the keyboard; existing three-image hardware research does not
by itself validate every new automation path.

## Shared app notification inbox

[NOTIFICATIONS.md](NOTIFICATIONS.md) adds a local HTTP/Python inbox, nine
customizable card presets, a Slack Socket Mode adapter, and examples for
Calendar and local automation producers. Notifications temporarily replace
the managed image and then restore it; `combined.json` enables this inbox too.
