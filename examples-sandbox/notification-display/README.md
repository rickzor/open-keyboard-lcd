# Resident default GIF + notifications

**Sandbox experiment.** A default mountain flyover stays resident in flash;
notifications temporarily replace the displayed screen without rewriting it.
This is separate from the full-set automation worker and reuses the existing
[HID driver](../../rt82.py), [flyover generator](../flyover/README.md), and
[notification inbox/cards](../automations/NOTIFICATIONS.md).

## Storage and behavior

The default is the one-minute, 8-FPS **Annapurna** flyover (3,470,545 bytes).
Block 0 is reserved exclusively for a notification of at most 65,536 bytes.
The flyover starts at block 1 and occupies 53 blocks. The complete allocation
is 54 blocks, or 3,538,944 bytes including alignment and the notification block.

Initialization replaces the old set once. Afterward:

1. The single visible playback slot points to the resident mountain.
2. A notification switches that pointer to block 0, uses the narrowly tested
   first-block erase sequence, and writes only the notification image.
3. Each new displayed notification restarts a 60-second timer.
4. After the timer expires and the inbox is drained, the pointer returns to the
   mountain. **No mountain image data is written or erased during this return.**

The physical slot cycle exposes one active position. The host changes its
pointer between the default and notification; no extra metadata page is needed.
Notification cards use the existing customizable presets and optional pulse.
The generic payload's `duration` is ignored here: the return delay is 60 seconds.
The inbox uses priority, then arrival order; duplicate IDs don't reset the timer.

The host worker must be running to accept notifications and perform the timed
return. If the computer or worker stops during a notification, the keyboard can
keep displaying it. Successful deadlines survive process restart. This does not
change keyboard firmware or add a keyboard-side timer.

## One-time preparation and upload

From the repository root, select the generated flyover collection:

```sh
.venv/bin/python examples-sandbox/notification-display/display.py prepare \
  /path/to/mountain-flyovers/collection.json state/notification-default-library
```

Preparation copies and verifies the default QGIF locally; it sends nothing to
USB. To choose another default, append `--names "Exact mountain name"`.
The shared library helper also supports multiple entries for future experiments,
but this experiment's default configuration contains exactly one mountain.

The following explicitly **replaces the keyboard's current image set**:

```sh
.venv/bin/python examples-sandbox/notification-display/display.py initialize \
  state/notification-default-library
```

Do not rerun initialization for notifications or worker restarts. Run it only
when intentionally replacing the default/library. Original GIFs and encoded
files remain available locally for recovery.

## Background worker and local notifications

```sh
.venv/bin/python examples-sandbox/notification-display/display.py run
```

This foreground worker hosts the authenticated loopback inbox on port 8765.
From another terminal or a local producer:

```sh
.venv/bin/python examples-sandbox/automations/notifications.py send \
  --template message --title "Hello" \
  --message "Back to Annapurna in one minute"
```

It uses the existing inbox folder and protected token file. Don't run a second
inbox server on the same port or another display worker against the keyboard.
Slack and other local producers can use this inbox; no new native app
subscriptions are implied. No login service or recurring job is installed.

Manual metadata-only return, with the worker stopped:

```sh
.venv/bin/python examples-sandbox/notification-display/display.py select 1
.venv/bin/python examples-sandbox/notification-display/display.py status
```

The default controller ledger is `state/notification-display/resident.json`.
Use `--state /path/to/state` before the subcommand to choose another ledger.
A process lock prevents competing workers using that state. Each USB transaction
also takes the shared driver lock and checks the device identity and complete
expected metadata. Changes made by another uploader cause this worker to stop.

## Interruption and experimental limits

Initialization records acknowledged-byte checkpoints. An explicit
`resume-initialize state/notification-default-library` checks the original
payload hashes, device identity, and table before resuming without erase.
A short suffix can be replayed with identical bytes because checkpoints lag
some acknowledgements. An identity/table mismatch stops the resume.
Notification writes interrupted midway remain marked pending; automatic repair
is not implemented. The worker never falls back to a full-set rewrite.

The larger predecessor experiment attempted four resident mountains. Its LCD
interface timed out after approximately 11.27–11.39 MB of acknowledged image
payload and then failed even read commands. This was not an explicit capacity
response. The smaller layout here avoids relying on that larger footprint. See the separate
[large-upload interruption note](../../research/large-upload-interruption.md)
for byte accounting, recovery observations, and unresolved causes.

The first-block erase sequence has separate visual evidence with small adjacent
images; pointer aliasing has also been tested separately. Their combined use
with this resident default requires on-keyboard confirmation. Matching metadata
and USB acknowledgements do not prove that neighboring flash contents survived.
Tests cover block-0-only notification writes, metadata-only return, timer reset,
duplicate suppression, device/state checks, and failure handling.

The reduced Annapurna upload completed on 2026-10-11, and the user confirmed
its playback looked good. A live worker then accepted two local notification
cards, each 18,721 encoded bytes. The second successfully displayed notification
extended the return deadline by 31.7 seconds. The worker returned to the resident
block-1 mountain pointer after the second 60-second timer and verified metadata.
Both notification operations used only the first-block write path; return used
configuration only. The user confirmed both notification cards appeared and
Annapurna returned cleanly. This validates the combined cycle on this keyboard;
long-running operation and recovery from interrupted notification writes remain
experimental. Automated tests exercise the controller independently of USB hardware.
