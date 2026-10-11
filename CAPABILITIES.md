# RT82 capability investigation

Measurements below refer to the connected RT82 tested on 2026-10-11. An accepted
USB transfer and matching metadata do not establish correct playback.

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
had erased blocks 0 through 8 and written images only into blocks 0 through 7.
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
claims have not been adopted as device facts. No unknown-opcode sweep, firmware
flash, or high-address capacity probing was performed.

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
