# Open Keyboard LCD — Epomaker RT82

Upload GIFs to an Epomaker RT82 keyboard directly over USB, without Chrome,
WebHID binding dialogs, or a running website. GIF conversion runs locally using an independently implemented Python QGIF
encoder. No manufacturer binaries, JavaScript, Node.js, or WebAssembly are needed. Commands can run unattended in the background.

**Uploads replace the complete set with one, two, or three images.**
The newly added one/two-image paths have automated coverage but still need
visual hardware confirmation. Updating one
image using local backups also rewrites the complete saved set. A true single-slot
update preserving unknown images on the keyboard is disabled in the supported CLI.
A controlled single-slot append into explicitly reserved space has worked;
an experimental tracked one-update pool is available below, while safe
general reclamation remains unresolved. Controlled experiments now demonstrate
repeat replacement of a 16,840-byte image at block 0 and a later
57,889-byte animated replacement while preserving adjacent images, using a reduced metadata allocation count. This narrow sequence is not
yet exposed in the CLI. See [CAPABILITIES.md](CAPABILITIES.md).

The independent encoder and USB client have been tested together on an RT82:
all three original sample GIFs displayed correctly on the keyboard. A later
controlled experiment also confirmed four independently stored GIFs, including
`examples/slot-4.gif`. Four-image operation is not yet integrated into the CLI.

## Tested limits so far

Hardware tests confirmed a **7,031,890-byte encoded QGIF** with END 512,
clean looping, and two other working images, plus an earlier **1,024-frame**
animation. Eleven distinct static images cycled correctly in a separate test;
metadata paging prevents reliable higher-count operation so far. These are
observed lower bounds, not maximum device specifications. The normal CLI accepts one to three images. See [CAPABILITIES.md](CAPABILITIES.md),
[PROTOCOL.md](PROTOCOL.md), and [TODO.md](TODO.md) for evidence and next steps.

Generate a capacity test locally (no USB writes):

```sh
.venv/bin/python make_capacity_test.py --frames 512 --output /tmp/rt82-size-512
```

This writes a source GIF, encoded QGIF, and inspection JSON. Large files take
several minutes to transfer; input GIF size differs from encoded device size.

## Setup

Developed on macOS with Python 3.13. The implementation uses POSIX file
locking; Windows is not supported. Linux HID permissions have not been tested.
Connect the RT82 by USB in wired mode.

```sh
chmod +x setup.sh rt82
./setup.sh
./rt82 devices
./rt82 probe
```

`python` must be Python 3. Setup creates a local
virtual environment and installs `hidapi` and Pillow. It does not upload images
or install a scheduled job. After setup, uploads require no network connection.

## Upload from local files

Replace the complete set with one, two, or three images (this removes other
selectable images):

```sh
./rt82 replace-all examples/slot-1.gif
./rt82 replace-all examples/slot-1.gif examples/slot-2.gif
```

Or use the original three-image set:

```sh
./rt82 replace-all examples/slot-1.gif examples/slot-2.gif examples/slot-3-morph.gif
```

Replace one image in the locally saved set, then resend the entire set:

```sh
./rt82 update-cached-set "$HOME/Desktop/RT82 GIFs/new-animation.gif" --slot 3
```

This command requires backups from a successful `replace-all` operation. It
checks those backups and the keyboard's slot metadata before writing. It cannot
detect external changes that leave identical metadata; establish a new complete
set after using another uploader. It cannot recover unknown GIFs from the device.

A directory can also be supplied; the newest `.gif` is selected:

```sh
./rt82 update-cached-set "$HOME/Desktop/RT82 GIFs" --slot 3 --if-changed
```

`--if-changed` skips the write when the encoded images match the saved set. Keep
`state/`: it contains encoded backups and transaction records. These are ignored
by Git. A process lock prevents concurrent updates through this checkout.

Commands do not open windows or ask for input. To run a command in the background,
use your normal shell or process manager. No scheduler is included.

## Experimental single-slot append

A controlled reserved-space update has been visually confirmed. `pool.py`
implements that exact bounded layout: three images of at most 64 KiB each, plus
one spare 64-KiB block. **Initialization replaces all three slots.**

```sh
.venv/bin/python pool.py init examples/slot-1.gif examples/slot-2.gif examples/slot-3-morph.gif
.venv/bin/python pool.py append replacement.gif --slot 3
.venv/bin/python pool.py status
```

The append writes only the replacement image and updates its slot entry; it
sends no erase command and does not read local copies of the other images.
There is **one append per initialization**, even if the replacement is tiny.
Once consumed, the block is never automatically reused. Reinitialization needs
all three desired images again. Interrupted writes disable the pool until an
explicit reinitialization; they do not silently free the attempted allocation.

Keep `state/append-pool.json`. Use only this checkout/client with this keyboard
while a pool is active. HID identity/path and metadata checks catch some changes,
but cannot detect every external write or a replacement device reusing the same
path. A normal full upload through this checkout invalidates the pool. No flash
readback/checksum is available, and larger reserve pools are not enabled because
the device's physical capacity and erase semantics are not established.

## Other commands

```sh
./rt82 sync-time
./rt82 screen-info
./rt82 qgif-info /tmp/slot-1.qgif
./rt82 encode examples/slot-1.gif /tmp/slot-1.qgif
.venv/bin/python -m unittest discover -p 'test_*.py'
```

Encoding uses 240×136 pixels, a default cap of 40 frames, and a constant frame rate derived
from the first GIF frame's duration, matching the inspected Hub preprocessing behavior. The frame rate is clamped
to the format's 1–128 FPS range. Pre-encoded `.qgif` files can also be supplied.

The 40-frame cap is a client default, not a verified firmware limit. To encode
a longer experimental file, use `./rt82 encode input.gif output.qgif --max-frames 1024`,
then upload that QGIF using `replace-all`. See [CAPABILITIES.md](CAPABILITIES.md)
for animation-length trials, single-slot findings, and live-display/DOOM research.
Playback through all 1,024 frames of a nominal 64-second test has been visually
confirmed on the tested RT82; the device maximum remains unknown.

The independent encoder fits two RGB565 colors per 4×4 block, assigns two-bit
pixel selectors, and writes delta bitmaps for animation. Its output need not be
byte-identical to the manufacturer encoder; compression and color approximation
can differ. See [QGIF_FORMAT.md](QGIF_FORMAT.md) for the observed wire format.

## Why single-slot upload is disabled

Controlled tests on disposable images found:

- Erasing with either the website's block index or a byte address damaged another
  slot, including when erasing exactly one block.
- Writing to known-erased spare space without an erase command preserved the
  other slots and displayed the new animation correctly.
- Overwriting occupied space without erasure preserved the other slots but did
  not correctly replace the animation.

The `upload --slot` command refuses before USB access. Acknowledgements and slot
metadata do not prove that other stored GIF payloads are intact. General targeted erasure and image readback remain unresolved. A narrow
first-block erase/replacement sequence has now worked repeatedly with neighboring
images intact; arbitrary nonzero blocks and payloads beyond the tested
57,889-byte replacement remain unverified.
See [PROTOCOL.md](PROTOCOL.md).

## Next work

See [TODO.md](TODO.md) for targeted slot-2 erase investigation, four-image CLI
support, a guarded first-block updater, and capacity/live-display research.

## USB access

The macOS implementation opens the vendor HID interface without exclusively
seizing the keyboard. Run outside restrictive application sandboxes. Grant any
USB/Input Monitoring permission requested by your operating system to the process
running the client. An interrupted flash write can leave an incomplete image set;
the supplied encoded images are retained locally for re-upload.

## License and attribution

Original client code is MIT licensed; see [LICENSE](LICENSE). This is an
independent project, not an official Epomaker driver.

The Python QGIF encoder was written from observations of generated files, without
copying vendor implementation code. Pillow and hidapi are installed separately
and retain their own licenses. This repository starts with fresh history and
contains no manufacturer binaries or implementation code.

## Sandbox examples — mostly untested

These are **experimental prototypes**, not validated end-to-end features.
See the [validation matrix](examples-sandbox/README.md) and
[automation examples](examples-sandbox/automations/README.md) for animated weather
(default San Francisco, every 30 minutes), local Apple Calendar alerts one
minute before meetings with restoration, and an hourly G-rated GIPHY selection.
GIPHY fits the original rendition to the screen width, then crops vertically. Examples
use one managed slot, preview locally by default, and install no scheduled jobs.

A [shared notification inbox](examples-sandbox/automations/NOTIFICATIONS.md) accepts
local app/automation messages and includes customizable Slack, Calendar, success,
warning, error, reminder, focus, and automation cards with automatic restoration.
