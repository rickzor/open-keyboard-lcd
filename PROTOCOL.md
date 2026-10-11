# Observed RT82 LCD protocol

These are implementation notes from one RT82, not a firmware specification.

- Keyboard: VID:PID `36b0:30a3`, usage page `ff60`, usage `61`, 32-byte reports.
- LCD: VID:PID `1919:1919`, usage page `00ff`, 64-byte reports.
- HIDAPI writes prepend a zero report-ID byte.
- LCD packet: `AA command p1 p2 p3 p4 00 00`, then up to 56 payload bytes.
- Activate the LCD: keyboard `AA E2`, then five `AA E0` handshakes. The `E2`
  query can return an `E0` response on the tested device.
- Configuration read: `14`, offset zero, length 56. Payload byte 1 is GIF count;
  byte 2 is total 64-KiB blocks. Three five-byte entries begin at byte 3:
  start block, reserved byte, then 24-bit little-endian image length.
- Full-set sequence: `1B`; keyboard `E3` with GIF count; `14`; `15` at offsets
  0/56/112 with lengths 56/56/16; `16`; `18`; image chunks via `19`; `1A`.
- `19` uses a 24-bit little-endian byte address and a chunk length.
- Full-set erase starts at zero and uses total image blocks plus one, matching
  the inspected Hub batch sequence. Delay is 500 ms per erased block.
- A delayed `18` reply may arrive during the first write and is skipped while
  waiting for the expected write response.
- Time synchronization uses `10`, `17` with decimal time digits, then `11`.

## Unresolved single-slot behavior

Tests used a complete backup of three disposable images. Both nonzero block-index
and byte-address encodings of `18`, with a count of one, damaged another slot.
No-erase uploads into known blank space worked; same-address no-erase overwrites
did not. These results do not prove every firmware operation is incapable of
single-slot updates, but none has been established by this implementation.

The documented reads return screen information/configuration, not a supported
backup of the GIF payload. Physical flash capacity and general safe allocation
of unused space remain unknown. Do not use table matching as evidence that stored
image data is undamaged.

## Sources inspected

- [Epomaker Hub](https://hub.epomaker.com/oled)
- [Hub application bundle](https://hub.epomaker.com/assets/index-ikTzbcWR.js)
- [Manufacturer image tool](https://image.rdmctmzt.com/)
- [Public keyboard firmware source](https://github.com/Epomaker/rt82)

The keyboard source inspected exposed LCD interface declarations but not the LCD
controller's flash command handler. No firmware changes are performed here.
