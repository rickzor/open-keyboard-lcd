# Persistent live weather display

The main mode shows one continuous screen: temperature, weather condition,
location, and a small full-color low-poly 3D icon on pure black. The icon loops
for two seconds while the text stays still. Open-Meteo is checked immediately
on startup and every hour thereafter. There is no carousel or return timer.

Edit `weather.json` for location label, latitude, longitude, and Fahrenheit or
Celsius. The default is San Francisco, CA. Configuration is reread each check.
The footer shows the provider's observation time in the location's timezone.
If a fetch fails, the last screen remains displayed and the worker retries in
five minutes. An unchanged encoded card does not cause another flash write.

After the initialization below, stop the demo/notification worker and run:

```sh
.venv/bin/python examples-sandbox/weather-display/live_weather.py
```

Use `--once` for one refresh, `--config` for another configuration file,
`--state` for the initialized controller directory, or `--out` for previews.
This is a local long-running worker: it must remain running for hourly checks.
No login service is installed. The keyboard continues playing its last screen
while the computer is asleep or the worker is stopped. Network access uses
Open-Meteo without an API key; coordinates are sent to that provider.

Updates use only the tested block-0 erase/write sequence and one visible slot.
Previously resident demo images remain hidden in flash. Cards must fit 64 KiB;
USB failures stop the worker instead of retrying a possibly partial write.
The experimental controller checks keyboard identity and expected metadata
before every update. Do not run other keyboard display writers alongside it.

## Original demo and first-time initialization

A separate linked sandbox experiment: ten procedural, full-color animated weather
icons against pure black. Synthetic demonstration conditions, not a live forecast.
It reuses the [resident notification controller](../notification-display/README.md)
with its own state at `state/weather-display`.

The default reel cycles through sun, moon, sun/cloud, moon/cloud, cloud, fog,
rain, snow, thunder, and wind. Each loop is two seconds at 8 FPS; the complete
20-second reel has 160 frames and encodes to 254,745 bytes. The procedural
renderer also exports every loop separately as GIF and QGIF. Individual loops
are 27,881–45,441 bytes: all ten fit the 65,536-byte notification block. This is
not a measured maximum number of animations the hardware supports.

## Generate, prepare, and upload

From the repository root:

```sh
.venv/bin/python examples-sandbox/weather-display/render_weather.py --out state/weather-assets
.venv/bin/python examples-sandbox/weather-display/weather_display.py prepare \
  state/weather-assets/collection.json state/weather-default-library
.venv/bin/python examples-sandbox/weather-display/weather_display.py initialize \
  state/weather-default-library
```

Initialization replaces the keyboard's previous image set. The complete reel
lives at block 1 onward. Block 0 remains reserved for temporary notification
animations; returning to the reel only changes metadata and never reuploads it.
All ten loops play automatically within one GIF, without host-driven switching
or extra selectable slots. The renderer uses small flat-shaded polygon meshes,
with no vendor artwork, shaders, models, or proprietary encoders.

Use `weather_display.py run` for the existing notification inbox and 60-second
return behavior. Stop other display workers first: they cannot share ownership
of the same keyboard. No login service or scheduled job is installed.

Python callers can use `ResidentDisplay.show_animation(encoded_qgif, unique_id)`
under the controller lock to display one of the local weather animations in the
notification block. It checks dimensions and byte length before any USB write.
The HTTP inbox still accepts the ordinary notification card schema; arbitrary
GIF uploads over HTTP are not implemented. The main reel and each standalone
loop are locally validated; on-keyboard rendering needs visual confirmation.

On 2026-10-11 the reel upload and metadata verification completed. A 42,881-byte
animated thunder notification was then written exclusively to block 0. After
60 seconds the controller returned to the resident reel through metadata only.
The complete visual result awaits user confirmation.
