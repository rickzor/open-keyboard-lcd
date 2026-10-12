# Sandbox examples — mostly untested integrations

**Experimental prototypes, not production-ready features.** These examples have
local previews and automated checks, but have not been validated end to end on
the keyboard with real app accounts. Expect bugs, incomplete integrations, and
changes to configuration or behavior.

| Area | What has been checked | What remains unverified |
| --- | --- | --- |
| Animated weather | Live San Francisco fetch, local animation rendering | Recurring operation and on-keyboard updates |
| Calendar / Google-synced calendars | Helper compiles; fixture-based timing and restoration tests | Calendar permission flow, real events, on-keyboard alerts |
| GIPHY | Local framing logic and rating checks in code | Live API account, content suitability, storage approval, on-keyboard playback |
| Notification inbox | Local HTTP, validation, queue, templates, and restoration tests | Sustained operation and on-keyboard delivery |
| Slack adapter | Event mapping tests | Live Slack account, Socket Mode delivery, reconnect behavior |
| ChatGPT / dots / other producers | Generic local command and HTTP input | Native subscriptions or automatic app capture; none are included |

Automated tests are **not evidence of hardware or live-service validation**.
USB mode replaces the complete managed image set and writes flash; it does not
preserve arbitrary images already stored on the keyboard. Preview mode is the
default. No jobs or services are installed automatically.

Start with [automation prototypes](automations/README.md) or the
[notification inbox prototype](automations/NOTIFICATIONS.md).
The previously hardware-tested sample GIFs remain in [examples](../examples/README.md).

## Geographic flyover

[flyover](flyover/README.md) is a daily, optionally random location experiment:
a one-minute white-on-black geographic wireframe, bottom-edge coordinates, and
an explicit one-animation upload. Ten mountain presets are available, including
Annapurna, Mount Sir Donald, and Denali; the San Francisco and other city routes
are retained. Custom coordinates can generate a new route on demand. Geometry,
daily operation, and hardware playback need separate visual validation; it is
not a surveyed city model.

## Resident default GIF and notifications

[notification-display](notification-display/README.md) is a separate linked
experiment: upload one mountain flyover once, reserve block 0 for notifications,
and return to the resident default 60 seconds after the latest notification.
Switches change only the playback pointer; they do not reupload the default.
Combined hardware behavior remains experimental.

## Low-poly 3D weather display

[weather-display](weather-display/README.md) is the new visual experiment:
ten full-color weather loops on black, playing as one compact default reel.
Each loop also fits individually into the shared notification controller's
reserved first block. The weather state and assets are separate from Annapurna.

## Background weather and notifications

See [weather-notifications](weather-notifications/README.md) for the macOS login service, hourly weather, synced Google/iCloud calendar reminders, and local notification API.
