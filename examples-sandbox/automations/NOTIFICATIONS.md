# Sandbox: shared keyboard notification inbox

**Experimental, mostly untested integration.** The local queue and rendering
have automated coverage; live Slack and on-keyboard notification delivery have
not been validated. See the [validation matrix](../README.md).

Any local app, script, or automation can enqueue a short card. A single display
worker shows it temporarily, then restores the exact previous managed GIF.
This is a **push inbox**, not a scraper of macOS Notification Center. It does not
silently connect to Slack, Calendar, ChatGPT, or other accounts.

## Try it without changing the keyboard

Run these from the repository root after setup, in separate terminals:

```sh
# Establish the preview's previous GIF.
.venv/bin/python examples-sandbox/automations/lcd_automations.py demo

# Start the loopback-only HTTP inbox. No USB access here.
.venv/bin/python examples-sandbox/automations/notifications.py serve

# One worker renders cards and restores the previous GIF.
.venv/bin/python examples-sandbox/automations/lcd_automations.py run --config examples-sandbox/automations/notifications.json
```

Send an example from another terminal:

```sh
.venv/bin/python examples-sandbox/automations/notifications.py send \
  --source "My automation" --template success \
  --title "Build complete" --message "All checks passed. Ready to review." \
  --duration 20 --id build-42-complete
```

Watch `state/automation-preview/current.gif`: it changes to the notification,
then back to the original image. Use a fresh `--id` for each real event; retries
with the same ID are deduplicated for up to 24 hours. No job is installed and
nothing starts at login. Stop the server and worker with Ctrl-C.

For real hardware, first follow the explicit single-image initialization in
[README.md](README.md), then run the worker with `--usb --state state/automation-usb`.
This replaces the managed image in flash; it does not overlay a RAM framebuffer
or preserve unrelated unknown keyboard images. Keep just one display worker.
The inbox server and Slack adapter never open USB.

To combine with weather/meetings/GIPHY, use `combined.json`, or add
`"notifications": true` to your config. `notification_inbox` selects a custom
inbox directory; use the same `--inbox` path for the server and senders.

## Defaults and customization

| Template | Appearance | Icon |
| --- | --- | --- |
| `message` | Cool blue on midnight blue | Message bubble |
| `slack` | Lavender on plum | Message bubble |
| `calendar` | Rose on dark berry | Calendar |
| `reminder` | Warm amber on brown | Bell |
| `success` | Mint on forest green | Check |
| `warning` | Gold on dark ochre | Warning triangle |
| `error` | Coral on dark burgundy | Warning triangle |
| `automation` | Cyan on deep teal | Spark |
| `focus` | Periwinkle on indigo | Clock |

Cards use a quiet dark background, colored edge, source label, two-line title,
and up to two lines of supporting text. Long text is truncated to fit. An
optional pulsing status dot provides animation without flashing the whole screen.
The presets require no downloaded artwork or emoji fonts.

JSON fields:

| Field | Default / accepted values |
| --- | --- |
| `id` | Generated UUID; use a stable event ID for retry deduplication, max 160 characters |
| `source` | `Automation`, max 40 characters |
| `template` | `message`, or any preset above |
| `title` | Template's title; max 80 characters |
| `message` | Empty; max 240 characters |
| `duration` | 15 seconds; integer 5–120 |
| `ttl` | 300 seconds from receipt; integer 5–3600; expired queued events are dropped |
| `priority` | 5; integer 0–9, highest first, then oldest first |
| `animate` | `true`; set `false` for a static card |
| `icon` | Preset icon or `message`, `calendar`, `bell`, `check`, `warning`, `spark`, `focus` |
| `theme` | Optional `accent`, `background`, `text`, `muted`; each is a `#RRGGBB` color |

See [notification-example.json](notification-example.json). The CLI supports
`--template`, `--accent`, and `--static`; the Python/HTTP interface supports the
full schema. Custom text is rendered as text, never executed or opened as a URL.

## Local HTTP / Python integration

Endpoint: `POST http://127.0.0.1:8765/notify`, JSON body, with
`Authorization: Bearer <local token>`. The server creates
`state/notifications/token` with owner-only permissions. Do not publish that
file. It returns HTTP 202 with `queued` or `duplicate`, meaning **accepted into
the queue**, not proof of on-keyboard display. Invalid input returns 400,
missing credentials 401, capacity limits 429. Request bodies are limited to 8 KiB;
100 undelivered notifications and 10,000 retained IDs are the bounds.

The Python client reads the token and sends directly to loopback, without proxies:

```python
# Add examples-sandbox/automations to your Python import path.
from notifications import send

send({
    "id": "calendar:event-42:2026-10-11T17:00",
    "source": "Calendar",
    "template": "calendar",
    "title": "Design review in 1 minute",
    "message": "Bring the latest mockups.",
    "duration": 60,
    "ttl": 90,
    "priority": 8,
    "theme": {"accent": "#FFB4D9"},
})
```

Shortcuts or other local automation tools can POST the same JSON and header.
Keep the endpoint on loopback; this example deliberately has no remote bind
option, CORS support, public webhook, or tunnel. Notification text is stored
locally until displayed/expired, then removed from the queue body. IDs remain
for deduplication. SQLite deletion is not a secure erase guarantee. Active
rendered card images may contain private text; protect the state directory.

## Source adapters

**Slack:** [slack_notifications.py](slack_notifications.py) uses Slack Socket Mode,
so there is no public inbound server. Install `slack-sdk` separately. Create your
own Slack app, enable Socket Mode, add the app-level `connections:write` scope,
subscribe to `app_mention`, grant bot `app_mentions:read`, and install it into
your workspace. Supply `SLACK_APP_TOKEN` and `SLACK_BOT_TOKEN` through the
environment, then run:

```sh
.venv/bin/python examples-sandbox/automations/slack_notifications.py
```

This forwards **mentions of the installed app**, not every notification or your
personal mentions/DMs. It writes into the same durable inbox and acknowledges
accepted event envelopes; it sends no Slack messages or reactions. Message text
is hidden by default; opt in with `--include-text`. Bot-generated mentions are
ignored. Live Slack requires your app credentials and was not tested against an
account. Follow the official [Socket Mode setup](https://docs.slack.dev/apis/events-api/using-socket-mode/)
and [Python SDK guide](https://docs.slack.dev/tools/python-slack-sdk/socket-mode/).

**Calendar / Google Calendar:** the existing EventKit example already uses the
same display controller and restoration logic. It gets first chance to display
an imminent meeting before queued generic notifications. Google calendars work
when synced into macOS Calendar. An external calendar adapter can instead call
`send()` using the `calendar` preset.

**ChatGPT dots, Codex, and other automations:** a process that can execute a local
command or Python snippet can call `notifications.py send` / `send()` when work
finishes. For example, use `source="ChatGPT"`, `template="automation"`, title
`"Your summary is ready"`. There is **no native dots subscription or ChatGPT
notification API integration included**. Existing cloud services cannot reach
this loopback endpoint directly. Configure a local producer explicitly; merely
running this server does not capture their notifications.

## Queue behavior and recovery

Queued priorities choose the next card; they do not interrupt an active generic
card. Each card is shown for at most its duration/remaining TTL, then the exact
pre-alert image is restored before the next card. Meeting alerts may take over
through the existing Calendar path, retaining the original restoration image.
Background providers pause while any alert is active. USB/encoding latency means
all timings are best effort, not deadlines or critical alerts.

The queue survives a server/worker restart. Display state records delivered event
keys so a crash between a successful display and queue acknowledgement will not
redisplay it after restoration. An interrupted USB write leaves the existing
persistent pending marker and requires explicit reinitialization. The examples
still cannot read unknown GIFs back from the device or detect another uploader
that changes data without changing metadata.

Tests exercise input validation, all presets, custom themes, priority, TTL,
deduplication, bounded queues, HTTP authentication and origin rejection, restart
restoration, duplicate delivery recovery, and Slack event mapping. Live app
permissions/accounts and on-keyboard rendering are separate validation steps.
# Linked resident-library experiment

The separate [notification-display experiment](../notification-display/README.md) reuses
this inbox and these card presets, reserves the first flash block for notices,
and returns to the resident default mountain 60 seconds after the latest
displayed notification. Run its worker instead of the automation worker when
testing that storage model; both must not control the keyboard together.
