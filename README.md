# Open Keyboard LCD — Epomaker RT82

Upload GIFs to an Epomaker RT82 keyboard directly over USB, without Chrome,
WebHID binding dialogs, or a running website. GIF conversion runs locally using an independently implemented Python QGIF
encoder. No manufacturer binaries, JavaScript, Node.js, or WebAssembly are needed. Commands can run unattended in the background.

**Current limitation: uploads replace all three custom GIF slots.** Updating one
image using local backups also rewrites all three slots. A true single-slot
update preserving unknown images on the keyboard is unresolved and disabled.

The independent encoder and USB client have been tested together on an RT82:
all three included sample GIFs displayed correctly on the keyboard.

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

Replace every custom GIF with the included examples:

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

## Other commands

```sh
./rt82 sync-time
./rt82 encode examples/slot-1.gif /tmp/slot-1.qgif
.venv/bin/python -m unittest discover -p 'test_*.py'
```

Encoding uses 240×136 pixels, up to 40 frames, and a constant frame rate derived
from the first GIF frame's duration, matching the inspected Hub preprocessing behavior. The frame rate is clamped
to the format's 1–128 FPS range. Pre-encoded `.qgif` files can also be supplied.

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
metadata do not prove that other stored GIF payloads are intact. A working
solution needs a targeted erase operation or image readback; neither is currently
established. See [PROTOCOL.md](PROTOCOL.md).

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
