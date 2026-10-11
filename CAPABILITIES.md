# RT82 capability investigation

Measurements below refer to the connected RT82 tested on 2026-10-11. An accepted
USB transfer and matching metadata do not establish correct playback.

## Current findings

- **7,031,890-byte QGIF**: END 512, clean looping, and both following guard
  images confirmed. Maximum capacity remains unknown.
- **11 distinct static slots** cycle correctly. More than ten complete metadata
  entries require unresolved paging; 16 selections produced broken/duplicate
  images. Eleven is not a proven firmware limit.
- **1,024 frames** played through in an earlier, smaller-file trial.
- One reserved-block append and narrow first-block erase/replacement work.
  General nonzero-block targeted erasure remains unresolved.
- No live RAM framebuffer/streaming command found; interactive DOOM remains
  research work. The normal CLI still operates on three-image sets.

## Single-slot replacement

The independent encoder changes the image format implementation, not the LCD's
flash command semantics. Earlier controlled tests established:

- Writing a replacement to previously erased spare storage and changing only its
  slot entry preserved the other images (visually confirmed).
- Rewriting occupied storage without erasing produced an invalid replacement.
- Command 0x18 with both tested nonzero offset encodings damaged other slots.

A later controlled trial succeeded after explicitly reserving spare storage in
the allocation table before the full-set erase (details below). A finite
append-only allocator is therefore supported by this experiment, though it is
implemented in the experimental `pool.py` client, limited to the tested layout. Such an allocator must track exactly which blocks were erased, never reuse a consumed
block, and point the selected slot to its new allocation. This does not require
copies of other GIF payloads during each append. It does require trustworthy
allocation state, known capacity, exclusive ownership of device writes, and an
explicit full reset when space runs out. Metadata alone cannot prove blank space.
Unknown existing images cannot currently be preserved through garbage collection.
The normal `upload --slot` command remains disabled.



### Independent encoder append trial

After the three length tests were visually confirmed, only slot 3 was replaced
with a 55,793-byte, 120-frame animation in block 8. The preceding full-set upload
requested an erase count of 9 and wrote images only into blocks 0 through 7.
Actual erase coverage was not established.
This experiment sent no erase command and no image writes to slots 1 or 2.
Their metadata entries were retained. Image transfer took 3.87 seconds (about
14.4 KB/s); the updated slot table matched on readback. The user reported slots 1 and 2 worked and slot 3 did not. The user subsequently clarified that they were unsure what slot 3 displayed.
The exact appearance is therefore uncertain. Replacement playback is
not confirmed; this does not yet distinguish invalid image data from an ignored
pointer, cached layout, or uncommitted playback metadata. None of those causes
is established.
The original table was subsequently restored without image writes or erasure. Block 8 is now consumed and must
not be reused without a verified erase. The previous slot 3 payload remains at
block 3, and its original metadata entry has been restored.

### Pointer alias test (visually confirmed)

A fresh set of the original label GIFs was uploaded (one block per slot). Then
all three table entries were set to the existing slot 2 image: block 1, length
16,840 bytes. The global block count stayed 3. No erase or image-write commands
were sent during this metadata-only change, and readback matched. If these
entries control playback and aliases are supported, all three selections should
display the static slot 2 label. The user confirmed that all three selections showed slot 2. This establishes
that metadata-only pointer changes affect playback and that this firmware
accepts these overlapping allocations. It does not verify spare-block writes.

## Animation length: three different limits

1. **Client default:** `encode` defaults to 40 frames. This is a software policy,
   not an established hardware maximum. `encode --max-frames N` explicitly lifts
   it for experiments. Upload the resulting `.qgif` with `replace-all`.
2. **Format:** the implemented QGIF header has a 16-bit frame count (1–65,535) and
   1–128 FPS. Those representable values are not promises of firmware support.
3. **Device storage and playback:** physical flash capacity and the firmware's
   counter/buffer limits have not yet been established.

At 240×136 there are 2,040 blocks of 4×4 pixels. Every record has a 255-byte
change bitmap plus eight bytes per changed block. There is an additional final
record to restore the first frame. Even identical frames consume bitmap space.

For N frames, a constant image uses `10 + 16,320 + 255*(N+1)` bytes. A stream
changing every block in every record uses at most `10 + 16,575*(N+1)` bytes.
Consequently duration depends on frame rate, visual changes, and storage; there
is no justified universal maximum number of seconds yet. The 24-bit size field
and byte-sized allocation fields are protocol bounds, not measured capacity.

### Uploaded length trials

| Slot | Frames | FPS | Nominal loop | Encoded bytes | 64-KiB blocks |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 120 | 8 | 15 seconds | 55,793 | 1 |
| 2 | 256 | 16 | 16 seconds | 94,849 | 2 |
| 3 | 1,024 | 16 | 64 seconds | 315,369 | 5 |

All three transfers were acknowledged and metadata matched. The user visually
confirmed that all three animations play all the way through. This establishes
a tested lower bound of 1,024 frames and 315,369 bytes for a single animation;
it does not establish the maximum. The 64-second duration is nominal from the
encoded frame rate, not a stopwatch measurement. Each test shows START, QUARTER, HALFWAY, then a green
END label during its last quarter, with a moving dot and binary frame counter.
The complete 466,011-byte upload took 36.51 seconds including setup, erase,
write acknowledgements, and clock synchronization (about 12.8 KB/s end to end).

Use `./rt82 qgif-info file.qgif` for validated frame count, duration, allocation,
and USB report counts without touching hardware. `./rt82 screen-info` reads the
LCD's dimensions and raw information. Its `image_size_field_raw` has unknown
units and must not be treated as flash capacity.

## Live display and DOOM

The inspected RT82 Hub path exposes configuration, clock update, flash erase,
flash write, and display initialization. No arbitrary RAM framebuffer command
was found. The ODM tool also uses 0x1D/0x1E for a separate static-image path,
explicitly erasing before writing. That is not evidence of a streaming endpoint,
and those commands have not been sent to this keyboard.

The public keyboard source exposes LCD UART mode, GIF selection, test-color, and
USB activation declarations. It does not include the LCD controller's USB/flash
command handler. Changing the keyboard's QMK code alone is therefore not an
established route to arbitrary LCD pixel updates.

For scale, a raw 240×135 RGB565 frame is 64,800 bytes: 648 KB/s at 10 FPS or
1.944 MB/s at 30 FPS before USB overhead. A fully changed frame in our QGIF
variant is 16,575 bytes: 165.75 KB/s at 10 FPS. These are data-rate calculations,
not measured USB ceilings. The current acknowledged flash uploader is much
slower, and flash rewriting is unsuitable as a continuously refreshed framebuffer.
Pipelining USB writes could improve upload speed but cannot create a RAM endpoint.

The practical DOOM route would run the game on the computer and stream pixels
through a verified RAM/display command, possibly after an LCD firmware change.
Running DOOM on the LCD controller itself additionally requires identifying its
CPU, RAM, flash, display bus, and a recoverable programming interface. None has
been verified. A prerecorded DOOM animation is a separate, already plausible
use of the existing GIF playback path; it would not be interactive gameplay.

## Sources and evidence discipline

- [Official RT82 keyboard source](https://github.com/Epomaker/rt82), especially
  `lib/rdr_lib/rdr_common.h` LCD declarations.
- [Epomaker Hub](https://hub.epomaker.com/oled): inspected RT82 command table and
  single/batch upload implementations.
- [Manufacturer image tool](https://image.rdmctmzt.com/): inspected screen-info,
  GIF, and static-image transfer implementations.
- [Official tool link](https://epomaker.com/blogs/software/epomaker-rt82-image-tool).

Third-party format documents found during research contain header layouts that
contradict our generated and hardware-tested files. Their capacity and framebuffer
claims have not been adopted as device facts. No unknown-opcode sweep or firmware flash was performed. The capacity trials
below progressively expanded image-storage writes, using disposable images.

## Static spare-block control

After the successful pointer alias test, the exact working 16,840-byte slot 1
payload was copied to block 3 without erasure. Only slot 3 was redirected there.
The user saw two intact slot 2 screens and one corrupt image. This separates
pointer selection from successful image copying: pointer aliasing works, but
this spare-block write did not produce a valid copy. Encoding differences cannot
explain this failure because the payload was byte-identical to the working image.
The original three pointers were restored and their metadata verified.

The earlier description of a "known-erased spare block" was too strong: we knew
which erase request had been sent, not its actual erased range. A follow-up
experiment explicitly reserves block 3 in the allocation table (total 4 blocks)
before a full-set erase request of 5 blocks. The preceding baseline used total 3
and an erase request of 4. This tests whether an advertised allocation boundary
or erase-count behavior explains the spare-block failure; it cannot by itself
identify which firmware field controls erasure.

### Explicit reservation result: visually confirmed

The user confirmed two clean slot 1 screens and one clean slot 2 screen after
this trial. The original slot 1 and slot 2 payloads were not rewritten during
the append. Only a 16,840-byte copy of slot 1 was written at block 3, and only
slot 3's image entry was changed. Image transfer took 1.22 seconds. No erase
command was sent during the append. Block 3 is now consumed.

This establishes a working single-slot append under controlled initialization,
without requiring other image payloads during the append itself. It does not
establish safe append into arbitrary untracked space on an existing keyboard,
nor indefinite updates. The successful preparation changed both the allocation
total (3 to 4) and requested erase count (4 to 5), so the exact firmware erase
semantics remain unresolved. The conclusion is the tested sequence works, not
that either field alone has been proved responsible.

A supported implementation should explicitly initialize reserved storage, track
consumed blocks durably before sending any writes, reject uncertain or stale
state, and stop when the pool is exhausted. A failed/interrupted write must also
consume its allocation. Recovering space still requires a full-set operation
with all desired images available; unknown existing images cannot currently be
preserved through that reset. The generic `upload --slot` command remains disabled. The separate experimental
`pool.py` client implements a durable ledger for the tested one-spare-block layout;
it does not expose targeted erasure or expand the reserve beyond tested bounds.

## Reusing occupied space: prefix-offset erase trial

A further bounded experiment tests the hypothesis that erasure addresses include
a metadata block preceding image storage. On the visually confirmed reserved
set, logical block 3 contained a copy of slot 1. The test sent erase command
`AA 18 04 00 00 01 00 00 01 ...` (index 4, count 1), then wrote the existing
slot 2 payload at logical byte address `0x030000`. The slot table did not change.
Image transfer took 1.24 seconds. All exchanges completed and metadata matched, but the user observed one clean
slot 2 and two damaged screens. The tested prefix-offset encoding is therefore
not a safe targeted erase. A full restore of the original disposable set completed with matching metadata. The expected slot 1, slot 2, slot 2 result did not occur.

This is an experimental hypothesis, not an established offset conversion. The
normal client does not expose this targeted-erase operation. The experiment uses
only disposable images and the address range touched by the preceding full reset.

## Experimental pool client

`pool.py init` performs the tested full initialization with three one-block
images, allocation total 4, and erase request 5. `pool.py append` replaces any
one slot using block 3 and then reports the pool exhausted. Other GIF payloads
are not needed during append. The durable state is written and fsynced before
mutation; failed/incomplete attempts are never retried automatically. Identity,
layout, and exact metadata checks reject mismatched state. All commands share
the normal client's process lock. A normal full-set upload invalidates this
checkout's pool ledger before mutation. Other tools/checkouts cannot be monitored,
so exclusive ownership of device writes remains a precondition.

Unit tests cover reservation bounds, writes confined to the spare block, no
erase during append, unchanged other entries, exhaustion, disconnects, stale
metadata, device mismatch, initialization failure, and full-upload invalidation.
The client completed initialization and a slot 3 append on the keyboard with
matching metadata. A second append was rejected before USB access because the
ledger was exhausted. The user visually confirmed all three images were clean after this client run.
This verifies the implemented one-append sequence on the tested RT82.

## Controlled erase investigation: reusable first-block images

All tests below used disposable images and visually confirmed baselines. USB
acknowledgements and unchanged slot tables were recorded but were not treated
as proof of playback or flash contents. Block numbers are logical 64-KiB image
addresses. "Index" and "count" name the fields supplied by the host, not proven
firmware interpretations.

| Marker blocks | Metadata allocation count | Requested erase index / count | Observed result |
| --- | --- | --- | --- |
| 0, 1, 2 | 3 | 2 / 1 | All three images corrupted; no replacement writes |
| 0, 1, 2 | 3 | No erase (same setup/finish) | All three intact |
| 0, 3, 6 | 7 | 2 / 1 | All three images looked bad |
| 0, 3, 6 | 1 | No erase (metadata change only) | All three intact |
| 0, 3, 6 | 1 | 2 / 1 | Slot 1 white; slots 2 and 3 intact |
| 0, 3, 6 | 1 | 3 / 1 | Slot 1 affected; slots 2 and 3 intact |
| 0, 3, 6 | 1 | 3 / 7 | Slots 2 and 3 intact; slot 1 not explicitly described |
| 0, 1, 2 | 1 | 3 / 1 | Slots 2 and 3 intact; slot 1 not explicitly described |

Changing the allocation count changes the observed damage. Changing the tested
index values or requested counts did not move damage to the surviving markers.
This supports an allocation-driven erase beginning at the start of image storage.
It does not establish every byte erased, all possible field interpretations,
physical flash geometry, or a way to target a nonzero block.

### Changed-content reuse and repeat cycle: visually confirmed

On the adjacent layout with allocation count 1, after the index-3/count-1 erase,
only block 0 was written with the different 16,840-byte slot 2 payload. The user
confirmed two clean slot 2 labels and the original animated slot 3. No further
erase or image writes to neighboring blocks occurred during that replacement.

Then the same erase was issued again and only block 0 was written with the
original 16,840-byte slot 1 payload. The user confirmed clean slot 1, slot 2,
and animated slot 3. Thus changed-content reuse and a repeat erase/write cycle
worked while preserving immediate neighbors. The replacement operations read
only their respective replacement payloads, not neighboring image backups.

The tested sequence retains all slot entries and lengths, sets metadata byte 2
to 1, uses the normal setup/commit sequence, sends
`AA 18 03 00 00 01 00 00 01 ...`, waits one second, writes the replacement with
0x19 beginning at address zero, then uses the normal finish/time-sync sequence.
Slot pointers were 0, 1, 2; lengths were 16,840, 16,840, and 57,889 bytes.
The reduced allocation count stayed at 1 throughout playback and the repeat.
Restoring that count afterward has not been tested as part of this sequence.

This is a narrowly tested first-block operation, not general targeted erasure.
Beyond the later 57,889-byte length-change trial below, all bytes of a 64-KiB block, arbitrary
layouts, nonzero-block erasure, and behavior across power cycles remain unverified.
It is not yet exposed as a general CLI command. The append-pool ledger was
invalidated before these experiments; cached full-set manifests must not be
assumed to match the current experimental metadata or payloads.

### Larger first-block replacement: visually confirmed

The same allocation-1/index-3/count-1 erase sequence was used to replace the
16,840-byte block-0 label with the 57,889-byte, 24-frame slot-3 animation. Only
the first entry's length changed; the neighboring entries and payloads were
retained. The user confirmed both animated slot-3 screens and the static slot-2
label worked. This extends the tested first-block replacement size and verifies
a length change; it still does not establish the entire 64-KiB range.

The next nonzero-block investigation tests the unknown leading metadata byte,
which the inspected website sets to zero. A metadata-only change to 1 precedes
any erase test. Treating it as an erase base is a hypothesis, not a decoded field.

### Leading metadata byte: no demonstrated shift to slot 2

Changing metadata byte 0 from 0 to 1 without erasure left all three images
visually intact. With that byte held at 1, repeating index 3/count 1 erasure
damaged one of the two animated slot-3 images; the static slot-2 image survived.
The animated copies at blocks 0 and 2 were not individually distinguished by
the user. This did not demonstrate shifting the erase to block 1. Rewriting
only block 0 with its original animation, without erase or metadata changes,
is the next isolation step.

Rewriting only block 0 restored all three images, visually confirmed. This
localizes recoverable image damage to block 0 in the leading-byte-1 test; byte 0
did not shift erasure to block 1 under these conditions. Next, the erase address
is encoded as little-endian byte address 0x010000 (`AA 18 00 00 01 01 00 00 01 ...`),
with the same metadata and count 1. No replacement writes accompany this test.

The 0x010000 byte-addressed erase again damaged one animated image rather than
the static slot-2 label, according to the user. This did not establish a block-1
erase. A block-0-only restore follows to localize the damage. Another observed
variable remains: Hub's single-image path sends keyboard E3 payload
`00 00 00 01 00 00 (slot+1)` for its zero-based slot index, while these trials
have held the last byte at 3. Testing value 2 separately is a source-backed
setup hypothesis, not an established erase selector.

After the byte-address test, rewriting only block 0 restored all three images
(visually confirmed). Changing keyboard E3's final setup byte from 3 to 2
without erasure left all three images working, also visually confirmed. The
next controlled test repeats the 0x010000 byte-address/count-1 erase with that
setup value 2 while holding the LCD metadata unchanged.

### Keyboard setup value 2: possible selection-count effect

After the setup-2 byte-addressed erase, the user reported only two apparent
selections: a static slot-2 label and a white screen. The animated third image
was not accessible or not observed. This differs from the earlier setup-only
report that all three looked good; identical animated labels made counting
selections ambiguous. Do not treat the earlier report as proof that E3 value 2
preserves access to all three slots. Restoring E3 value 3 without erasure or
image writes will test visibility separately from stored-image damage.

### Four keyboard selections: visually confirmed

At the user's request, keyboard E3's final value was changed to 4 without
erasure or image writes; the LCD metadata still declared three images. The user
confirmed four selectable positions: two broken screens, static slot 2, and
animated slot 3. One damaged image already existed from the earlier erase.
Four selectable positions do not yet prove four independently stored images,
and conflict with treating the screen-info field value 3 as a hard limit.

The next metadata-only test copies the valid slot-2 entry (block 1, 16,840 bytes)
into the candidate fourth five-byte entry at offset 18. It retains the LCD
image count 3 and keyboard count 4, changing only that candidate entry. No
image writes or erase requests accompany this alias test.

After the fourth-entry alias write, the user reported one static slot 2 and one
animated slot 3 and confirmed four positions remained accessible. The two other
positions were not explicitly redescribed. Playback through the candidate
fourth entry is therefore not confirmed. The next metadata-only trial changes
the LCD image count from 3 to 4 while retaining the candidate fourth entry,
keyboard count 4, and all image data.

With the LCD image count changed to 4, the user confirmed two static slot-2
labels, one animated slot-3 screen, and one white screen. This establishes
playback via the fourth five-byte table entry at offset 18 when both counts
are 4. The fourth entry aliases block 1; four independently stored payloads
have not yet been tested. The screen-info value 3 is therefore not a hard
three-entry playback limit on this device under these conditions. A no-erase
block-0-only restore to the original slot-1 label follows, retaining four entries.

### Four independent images: visually confirmed

A complete disposable set was initialized with keyboard E3 count 4, LCD image
count 4, allocation count 4, and entries at blocks 0, 1, 2, and 3. The full-set
erase request used index 0/count 5, followed by each payload at its own address.
The original slot-1 and slot-2 labels and animated slot-3 image were retained;
a new green slot-4 label was encoded locally. Payload sizes were 16,840, 16,840,
57,889, and 16,840 bytes. The user confirmed all four displayed correctly.

This establishes four independently stored and selectable images on this unit,
not merely four pointers aliasing fewer images. Four is a tested lower bound,
not a maximum. The screen-info field reporting 3 cannot be treated as a hard
playback limit. The normal CLI still accepts three images; this four-image
experiment used a separate bounded harness and has not generalized the CLI.

State after the four-image trial: four valid independent labels with metadata
header `00 04 04`. Slot 4 no longer shares slot 2's storage. The default cached
three-image manifest remains stale; it must not be used as an automatic restore
of this four-image set. The experiment retained all four encoded payloads and
a table/hash log separately. Nonzero-block targeted erasure remains unresolved.

## Expanded slot and size limits (2026-10-11)

### Confirmed playback, not maximum specifications

| Encoded QGIF bytes | Total frames | FPS | Nominal loop | Following guard blocks | Visual result |
| ---: | ---: | ---: | ---: | --- | --- |
| 470,601 | 32 | 8 | 4 s | 8–14 | END 32 observed; looping and guards not explicitly confirmed |
| 915,034 | 71 | 8 | 8.875 s | 14, 15 | End marker and both guards worked |
| 1,783,970 | 135 | 8 | 16.875 s | 28, 29 | End marker, clean loop, both guards confirmed |
| 3,504,850 | 263 | 8 | 32.875 s | 54, 55 | User confirmed “256 works and all slots show up” after end/loop/guard check |
| **7,031,890** | **519** | **8** | **64.875 s** | **108, 109** | **END 512, clean loop, both guards explicitly confirmed** |

The latest fully observed encoded-size lower bound is **7,031,890 bytes**
(7.03 decimal MB, about 6.71 MiB) for one animation. This is the size of the
QGIF stream sent to the device, not the input GIF file. The earlier 1,024-frame
trial remains a separate frame-count lower bound. Neither maximum size nor
maximum duration nor maximum frame count is established.

The largest trial used image starts 0, 108, 109, with two 16,840-byte guards,
metadata `00 03 6e` (3 images, 110 allocation blocks), and a full-set erase
request of 111. Its first metadata page was:

```text
00036e0000524c6b6c00c841006d00c841000000000000000000000000000000000000000000000000000000000000000000000000000000
```

All three slots remained readable and the large animation looped. This tests
storage into logical block 109; it does not measure physical chip capacity or
prove every byte of the advertised allocation is usable. The screen-info raw
size field remains 158 with unknown units. The screen-info slot field remains
3 despite confirmed playback of more slots.

The size tests use changing backgrounds and pixel stripes. From END 64 onward,
the end marker appears only at the final changing frame, followed by seven
identical frames to hold it for about a second. END 32 appeared in the last
quarter, so that earlier observation is weaker. The initial guard labels said
“OF 8” after reducing to three images; the 128/256/512 trials corrected them to
“2 OF 3” and “3 OF 3.” A 320-frame intermediate file was generated but never
uploaded; the user requested doubling directly from 256 to 512 instead.

`make_capacity_test.py` regenerates these larger test patterns without accessing
USB. `capacity-evidence.json` retains payload hashes, sizes, table requests,
readback, and visual observations. Font rasterization affects exact encoded
bytes: the recorded files used macOS Arial Bold. Do not infer identical bytes
from another system's font or Pillow version.

### Slot-count results and metadata boundary

- Four independently stored images were confirmed as described above.
- Eight distinct static images at blocks 0–7 were confirmed, with both counts
  set to 8, allocation 8, and erase request 9.
- Sixteen distinct 16,840-byte images were written at blocks 0–15, both counts
  16 and allocation 16, erase request 17. Actual playback was eleven numbered
  labels, two duplicate slot-1 labels, then three white screens: 16 selections,
  but not 16 valid independently selected images.
- Changing only the two selection counts to 11 produced SLOT 1 through SLOT 11
  and a direct wrap to SLOT 1, confirmed. No erase or image writes accompanied
  this control. Its image captions still said “OF 16,” since only metadata changed.

**Eleven distinct static images is the observed count lower bound; it is not a
proven hardware maximum or general arbitrary-payload support for eleven slots.**
The known first configuration payload is 56 bytes. A three-byte prefix leaves
room for ten complete five-byte entries and three bytes of the eleventh. The
remaining two length bytes of entry 11 lie in the unresolved next page.

The 16-entry trial sent the full 128-byte table with command 0x15 at offsets
0, 56, 112. Offset-zero readback matched. Reads at offsets 56 and 112 did not
match the intended payload; the offset-56 response included an embedded 0x15
packet header. This may reflect unsupported paging or another buffer-layout
detail; it is not a decoded firmware memory map. A metadata-only retry changing
0x16's commit length from 56 to 128 did not fix readback or the bad positions.
Exact responses and requested tables are retained in `capacity-evidence.json`.

The next slot-count work is to establish metadata paging semantics, not declare
11 the device limit. The production CLI still replaces exactly three images;
these larger-count tests used bounded research scripts. Do not use cached
three-image manifests after independent hardware experiments without first
establishing a new complete set.
