# Observed RT82 LCD protocol

These are implementation notes from one RT82, not a firmware specification.

- Keyboard: VID:PID `36b0:30a3`, usage page `ff60`, usage `61`, 32-byte reports.
- LCD: VID:PID `1919:1919`, usage page `00ff`, 64-byte reports.
- HIDAPI writes prepend a zero report-ID byte.
- LCD packet: `AA command p1 p2 p3 p4 00 00`, then up to 56 payload bytes.
- Activate the LCD: keyboard `AA E2`, then five `AA E0` handshakes. The `E2`
  query can return an `E0` response on the tested device.
- Configuration read: `14`, offset zero, length 56. Payload byte 1 is GIF count;
  byte 2 is total 64-KiB blocks. Five-byte entries begin at byte 3 (see the metadata paging limitation below):
  start block, reserved byte, then 24-bit little-endian image length.
- Full-set sequence: `1B`; keyboard `E3` with GIF count; `14`; `15` at offsets
  0/56/112 with lengths 56/56/16; `16`; `18`; image chunks via `19`; `1A`.
- `19` uses a 24-bit little-endian byte address and a chunk length.
- Full-set erase requests index zero and count total image blocks plus one,
  matching the inspected Hub batch sequence. The client waits 500 ms per
  requested block; these parameters do not prove actual erase coverage.
- A delayed `18` reply may arrive during the first write and is skipped while
  waiting for the expected write response.
- Time synchronization uses `10`, `17` with decimal time digits, then `11`.

## Unresolved single-slot behavior

Controlled tests show that metadata allocation count affects the erase's observed
reach. With that count set to 1, requested indices 2 and 3 affected the image at
block 0 while higher-block images survived. Request count 7 also left images at
blocks 3 and 6 intact. A changed-content replacement and repeat erase/write cycle
at block 0 preserved adjacent images at blocks 1 and 2 (visually confirmed).
Tested replacements include 16,840-byte labels and a later 57,889-byte
animation with the first entry length changed.
See [CAPABILITIES.md](CAPABILITIES.md) for the exact sequence and controls.

This supports allocation-driven prefix erasure; it is not an exact firmware
specification or a verified nonzero-block erase. Generic `upload --slot` remains
disabled. The experimental append pool remains limited to its tested layout.

The documented reads return screen information/configuration, not a supported
backup of the GIF payload. Physical flash capacity and general safe allocation
of unused space remain unknown. Do not use table matching as evidence that stored
image data is undamaged.

## Four-image playback

Keyboard E3 setup count 4 and LCD metadata image count 4 enabled playback of
four distinct payloads at blocks 0–3, visually confirmed. The fourth entry starts
at metadata offset 18. The screen-info value 3 is not a hard playback limit on
the tested unit. The standard CLI remains limited to three images pending
integration; see CAPABILITIES.md for the experimental initialization sequence.

## Sources inspected

- [Epomaker Hub](https://hub.epomaker.com/oled)
- [Hub application bundle](https://hub.epomaker.com/assets/index-ikTzbcWR.js)
- [Manufacturer image tool](https://image.rdmctmzt.com/)
- [Public keyboard firmware source](https://github.com/Epomaker/rt82)

The keyboard source inspected exposed LCD interface declarations but not the LCD
controller's flash command handler. No firmware changes are performed here.

## Expanded count and capacity observations

Both keyboard E3's final count byte and LCD metadata byte 1 were changed for
count trials. Eight distinct images and eleven static labels were confirmed.
The first 56-byte page contains ten complete entries plus three bytes of entry
11. Sixteen selections produced eleven distinct labels, two duplicate slot-1
images, and three white screens. Sending entries through 0x15 offsets 56/112
and increasing 0x16 commit length to 128 did not fix later-page readback.
Treat this as unresolved paging, not a proven eleven-slot firmware maximum.

A 7,031,890-byte QGIF at block 0 plus guards at blocks 108/109 played correctly,
including END 512 and clean looping. Metadata count/allocation was 3/110 and
the full-set erase request count was 111. This establishes tested playback,
not physical capacity. `capacity-evidence.json` contains exact tables, hashes,
responses and observations; CAPABILITIES.md explains the limits of the evidence.
