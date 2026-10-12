# Next work

Hardware findings and limitations are in [CAPABILITIES.md](CAPABILITIES.md).
Eleven distinct static images and repeated block-0 replacement are visually confirmed;
nonzero-block targeted erasure is not.

- [ ] **Establish erasure of slot 2's actual storage without damaging neighbors.**
  Use distinct disposable labels, setup-only controls, and erase-only trials
  before replacement writes. Separate keyboard selection count from LCD image
  count, allocation count, and erase address/count. Record exact packets and
  visual outcomes. Existing index, byte-address, leading-metadata-byte, and
  keyboard-setup trials have not demonstrated a block-1 erase. Do not expose
  generic targeted erasure until the range is understood and repeatable.
- [ ] **Integrate the confirmed four-image layout into the CLI.**
  Generalize count validation, table planning, keyboard E3 count, manifests,
  backup/restore, and documentation together. Preserve the existing three-image
  workflow. Test four distinct payloads and refuse stale cached manifests.
  Four is a tested lower bound, not an established device maximum.
- [ ] **Turn the first-block experiment into a guarded updater.**
  Validate table layout and overlapping allocations before any erase; require
  exclusive device access and retain recoverable transaction state. Test larger
  and varying-length payloads, repeat cycles, interruption recovery, and power
  cycles. Confirmed replacements so far are 16,840 and 57,889 bytes; this does
  not prove every byte of a 64-KiB block is erased. Preserve other image entries
  and avoid requiring their source files for a one-image update.
- [ ] **Resolve metadata and firmware semantics.**
  Determine exact erase boundaries and whether the apparent allocation-driven
  prefix behavior is implemented in LCD firmware. The screen-info value 3 is
  not a hard three-image playback limit on the tested unit. Keep USB
  acknowledgements and table readback separate from payload validation.
- [ ] **Continue capacity and live-display research.**
  Independently confirmed lower bounds are 1,024 frames (315,369 bytes,
  64 seconds nominal at 16 FPS) and 7,031,890 bytes (519 frames at 8 FPS).
  These are separate
  frame-count and encoded-size results. Maximum capacity and a RAM framebuffer or
  streaming command remain unknown. Interactive DOOM requires a verified live
  display path; repeated flash updates are not a substitute.

- [ ] **Resolve the metadata boundary before increasing supported slot counts.**
  Eleven static labels cycle cleanly, but entry 11 crosses the first 56-byte
  payload boundary. Sixteen selections produced eleven distinct labels, two
  duplicate slot-1 images, and three white screens. Later metadata pages did
  not read back as intended; increasing commit length to 128 did not fix it.
  Determine paging semantics with controlled metadata-only trials before
  claiming a hardware maximum or supporting arbitrary images past entry 10.

- [ ] **Investigate the large resident-library transfer interruption.** Separate
  address, allocation, pacing, and cumulative-byte limits using the controlled
  trials in [the research note](research/large-upload-interruption.md). The
  observed 11.27 MB acknowledged lower bound is not a proven capacity limit.
