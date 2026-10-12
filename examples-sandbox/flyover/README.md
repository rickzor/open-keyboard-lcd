# Sandbox: daily monochrome geographic flyover

For a resident library that is uploaded once and temporarily interrupted by
notifications, see the separate [notification-display experiment](../notification-display/README.md).

**Experimental renderer, not a complete or surveyed 3D city model.** Generates
one minute of white wireframe on pure black at 240×135 visible pixels, plus the
QGIF format's padded row. Camera coordinates update along the very bottom.
One generated animation is the **entire uploaded image set**—no guard GIFs,
extra slots, or other images are uploaded. Uploading replaces the existing set.

## Render or upload once

The default is now **Himalaya - Annapurna**. The ten mountain presets are Annapurna,
Matterhorn, Mont Blanc, Everest, K2, Fitz Roy, Torres del Paine, Mount Sir Donald,
Grand Teton, and **Denali**. They are distinct 14–18 km routes centered on the
named mountain, with different travel bearings. The coordinate routes are
cinematic approximations, not hiking/climbing or aviation navigation plans.
Each preset includes its center, bearing, length, and reference map link.
San Francisco, Seattle, and Cape Town are retained as the `city` collection.

From the repository root, after setup:

```sh
.venv/bin/python examples-sandbox/flyover/flyover.py --location "San Francisco"
```

The predefined San Francisco route starts high over the Marin Headlands,
passes the Golden Gate and San Francisco, then travels south toward San Bruno
Mountain. The camera descends gradually; total route progress spans 60 seconds.
Coordinates describe the camera's horizontal position, not its look-at target.
At 8 FPS the QGIF contains 480 frames. The source GIF alternates 120/130 ms delays
to represent 8 FPS despite GIF's 10 ms timing resolution. The final frame loops
back to the northern start; this is a flyover, not a closed geographic circuit.

Files appear in `state/flyover/<date>-<run>/`: `flyover.gif`, `flyover.qgif`,
`contact-sheet.png`, `scene-summary.json`, and `manifest.json`. The manifest
records coordinates, source attribution, feature counts, payload hash and limits.
The encoder rejects an output above the previously demonstrated 7,031,890-byte
single-image size; this is a conservative tested bound, not hardware capacity.

Explicitly generate and upload **just this animation**:

```sh
.venv/bin/python examples-sandbox/flyover/flyover.py --location "San Francisco" --upload
```

Do not run alongside the weather/notification display worker: each assumes
ownership of the complete image set. The standard uploader serializes USB access,
but separate applications can still overwrite each other's intended display.

## Daily random selection (opt in)

```sh
.venv/bin/python examples-sandbox/flyover/flyover.py --daily --random --upload
```

This remains running and checks the local date every 30 seconds. It generates
and uploads at most once per completed local day, starting immediately. It does
not install launchd, cron, or a Codex task. It resumes with the same completion
ledger after restart; preview and upload completion records are separate.
Network/render/upload errors stop the process, preserve previous outputs, and do
not mark the day complete. A supervisor or a later manual run may retry. An
interrupted upload may leave the display incomplete; keep the saved QGIF.

`locations.json` is an editable list of named routes. The daily selection is
pseudo-random and repeatable for the local date/list, making retries select the
same location. Random selection defaults to the ten `mountain` presets. Use
`--collection city` for the preserved cities or `--collection all` for both
collections. Named `--location` selection can access either collection.
Long-running daily operation remains untested.

Use `--locations my-locations.json` for your own list, `--location "City name"`
for a one-off city (Open-Meteo geocoding, first result), or `--route route.json`
for precise waypoints. Unlisted geocoded cities get a generic north-to-south
route, not a curated landmark tour. Check coordinates when a name is ambiguous.
A route file contains:

```json
{
  "name": "My location",
  "route": [[37.85, -122.526], [37.82, -122.478], [37.686, -122.436]],
  "labels": ["NORTH APPROACH", "MIDPOINT", "DESTINATION"]
}
```

### Custom locations: generated only on demand

Mountain names may be missing from the city geocoder. Supply an exact center,
travel bearing (clockwise from north), and route length instead:

```sh
.venv/bin/python examples-sandbox/flyover/flyover.py \
  --location "My mountain ridge" --center 46.6193 12.3027 \
  --length-km 14 --bearing 35
```

This generates one local GIF and QGIF when invoked. Add `--upload` explicitly
to replace the keyboard's set with just that animation. Repeated one-off
invocations render again, even on the same day; completion markers deduplicate
only `--daily` mode. Custom routes are not added to random rotation automatically.

Python callers can use `generate_location(name, latitude, longitude,
length_km=14, bearing=0)` and pass the returned dictionary to
`render(location, new_output_directory, cache_directory)`. The function creates
five waypoints centered on the supplied coordinates. Route generation itself
does not download data, render, upload, or start a scheduled job.

### Pre-render the mountain collection

```sh
.venv/bin/python examples-sandbox/flyover/render_collection.py \
  --out state/mountain-flyovers --workers 3
```

This renders the ten mountain presets, serializes public map queries, and runs
up to three CPU rendering workers. Completed matching outputs can be reused on
a retry after their QGIF hashes are checked. `collection.json` records completed
or failed routes. It never uploads the collection or installs a recurring job.
Each folder contains a GIF, QGIF, contact sheet, and source/geometry manifest.

Routes are bounded to 1–50 km, a 500 km² bounding region, and 32 terrain tiles;
poles and dateline-spanning routes are unsupported. Only a small cached query is
intended per daily run. Failed/incomplete data does not silently become an invented
landscape. `--cache` can select a shared geodata cache; delete it explicitly to
refresh data, since the sandbox cache has no automatic expiry.

## What is real and what is stylized

- Bare-earth terrain comes from [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/)
  using [Terrarium encoding](https://github.com/tilezen/joerd/blob/master/docs/formats.md).
  Heights below sea level are clamped to zero; water is left black. This is a
  coarse terrain model, not current aerial imagery or a building-height survey.
- [OpenStreetMap](https://www.openstreetmap.org/copyright) provides building
  footprints, major roads, coastlines, bridge-tagged geometry and vegetation
  polygons, fetched via the public [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API).
  Buildings are queried within 400 m of the route and deterministically sampled
  to a maximum of 2,200. Small structures may disappear at the LCD's resolution.
- Building heights use OSM height/level tags where present, otherwise simplified
  inferred heights. Extruded blocks represent houses and city buildings.
- Bridges use schematic raised decks and supports on mapped alignments, not
  faithful engineering models. Parks/woods have up to 550 stylized tree symbols
  distributed inside mapped green areas; these are not surveyed individual trees.
- Painter-sorted black faces and white edges approximate hidden-line removal.
  The renderer uses one-bit drawing: **no grey shading, colored accents, textured
  imagery, or anti-aliased colored pixels**. Occlusion and near-plane clipping
  are deliberately simple and may produce visual artifacts.

On-screen credits appear during the opening; the manifest and this README retain
source links. OSM data is ODbL; terrain uses multiple upstream datasets with
source-dependent attribution. Review upstream licenses before redistributing
geodata or output. An independently written renderer does not change data rights.

No live framebuffer/streaming command is used. Rendering happens on the computer;
the completed encoded animation is uploaded to flash and played by the keyboard.
Rendering, upload, and playback are separate validation steps.

## Initial validation

The San Francisco route was rendered on 2026-10-11: 480 frames at 8 FPS,
60 seconds, and a 4,249,833-byte QGIF. All rendered pixels were checked to be
exactly black or white, and the source GIF's frame delays sum to 60 seconds.
The six-frame contact sheet was visually inspected. The repository's 43 local
tests pass. The single-image USB upload was acknowledged and the complete image
table matched afterward. On-keyboard playback still awaits visual confirmation;
geographic fidelity and unattended daily operation remain unverified.

The ten final mountain presets were also rendered on 2026-10-11. Each GIF was
checked across all 480 frames for strictly black/white pixels and exactly
60,000 ms of total delay. QGIF payloads are 3,214,769–4,111,137 bytes, below the
previously tested byte bound, with matching manifest hashes. Preview images
were visually inspected. The local test suite now contains 45 passing tests.
These mountain animations have not been uploaded or visually confirmed on the
keyboard. The preserved San Francisco animation was not replaced by this batch.
