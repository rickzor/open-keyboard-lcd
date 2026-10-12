# Large resident-library upload interruption

Experiment recorded on 2026-10-11, Epomaker RT82 LCD interface. This note records
an interrupted transfer, **not a confirmed 11 MB flash or GIF size limit**.
It is separate from the weather/notification implementation because its result
applies to a larger, multi-image resident-library experiment.

## Planned layout

Blocks are 65,536 bytes. Sizes below are encoded QGIF image payloads, excluding
USB report framing, commands, and alignment gaps.

| Image | Start block | Payload bytes |
| --- | ---: | ---: |
| Notification placeholder | 0 | 16,840 |
| Annapurna | 1 | 3,470,545 |
| Mount Sir Donald | 54 | 4,111,137 |
| Denali | 117 | 3,214,769 |
| Fitz Roy | 167 | 3,540,273 |

Planned payload: **14,353,564 bytes**. Planned allocation: **222 blocks**, or
14,548,992 bytes including unused alignment space. The initialization performed
a full-set erase/setup before sequential writes; it never reached final commit.

## Observed transfer boundary

The placeholder and first three mountain transfers completed their image writes:
10,813,291 payload bytes in total. The durable checkpoint for the fourth mountain
records `image_index=3`, `offset=458808` (the next byte after an acknowledged
56-byte write). That establishes **11,272,099 acknowledged payload bytes**
across the entire initialization, approximately 11.27 MB or 10.75 MiB.

The next progress boundary would correspond to 11,386,731 total payload bytes.
The earlier session therefore described the failure as approximately
11.27–11.39 MB based on coarse progress reporting. This is an estimated reporting
window, not a recovered exact failing packet or independently verified upper
bound. The persisted checkpoint establishes the lower bound; additional reports
may have been acknowledged after it. Future experiments should persist the exact
failed report address and cumulative counters.

At the confirmed checkpoint, Fitz Roy's next absolute flash address is
`167 × 65536 + 458808 = 11,403,320 = 0xAE0038`. The higher address includes gaps
between images: do not confuse flash address with cumulative payload bytes,
individual GIF size, or total USB traffic.

## Failure and recovery

The LCD interface stopped responding and subsequently timed out even on
read-only commands. The host reported IOKit timeout `0xE00002D6`; no explicit
"storage full" response was observed. This does not establish that the whole
USB keyboard disconnected, that any single GIF exceeded a decoder limit, or
that all acknowledged bytes were durably stored and playable.

After a physical power cycle, an explicit no-erase resume refused to continue
because the expected device identity or metadata did not match. That combined
check did not isolate which part differed. It intentionally did not bypass the
check or automatically erase the device.

The subsequent reduced layout (notification block plus the 3,470,545-byte
Annapurna animation) uploaded successfully. The user visually confirmed two
notification cards and the clean return to Annapurna; returning changed only
the playback pointer. The later weather experiment uses much smaller cards
and does not retest this large-transfer boundary.

## Open questions and next experiment

Possible causes include an address boundary, allocation/erase semantics,
transfer duration or pacing, firmware state, or a transient transport failure.
The available evidence does not distinguish these explanations.

- Use disposable images and record exact command, address, cumulative payload,
  elapsed time, acknowledgement latency, and the first failed response.
- Separate total allocation, highest written address, total bytes transferred,
  individual image size, and transfer duration in controlled trials.
- Repeat around the observed boundary with pacing/cooldown variations and
  read-only health checks; stop at the first error rather than issuing writes
  to an unresponsive interface.
- Confirm playback after successful completion and after a power cycle.
- Preserve checkpoint/state checks; do not retry an erase automatically or call
  this a capacity limit until a repeatable boundary is demonstrated.

Evidence summarized here comes from the retained local initialization ledger
and session observations. Raw device identifiers, local filesystem paths, and
private runtime state are deliberately omitted from this public note.
