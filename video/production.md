# Optional current-source demo capture

The v0.3.26 source ZIP includes the unchanged, verified v0.3.22 recording for same-origin Pages playback. It demonstrates the normal review-only flow, not the v0.3.24 edge-case fixes, v0.3.25 local-import hints and internal replay, or v0.3.26 browser hints. `scripts/render_demo_video.py` records actual interactions with the local browser text/PDF trial and checked-in static Judge Mode into a **new local preview**; it neither uploads nor publishes an MP4. The output path must be outside the source tree and must not exist. A reviewed recording is copied into `docs/media/` only as a separately audited release step.

Install optional capture tools in a separate environment that has Chrome available:

```text
python -m pip install playwright imageio-ffmpeg reportlab
python scripts/render_demo_video.py --root . --output ../biosure-demo-preview.mp4
```

If Chrome is not discoverable by Playwright, pass `--chrome-executable` with the path to an installed Chrome binary. The core BioSURE runtime and CI do not require the browser/video dependencies. The script starts loopback-only servers, generates one project-authored fictional PDF, checks actual text-layer extraction and Python worker decisions, shows a separately labeled CC BY 4.0 public-title static replay, runs the policy CLI, captures a silent browser video, converts to H.264 and validates full decode, no audio and duration under 180 seconds before placing the output. It refuses to overwrite an existing file. Version-pinned Pyodide/PDF.js code is fetched from a CDN; no document bytes are sent to it by the application.

Browser automation, captions and CLI display are not human work, independent adjudication, source authentication, model superiority or time-saving evidence. The fictional policy contracts (5/5) are separate from one forged-reference control that now abstains (0/1 automatic repairs). This does not prove general safety. A false declared reference can still produce a false review candidate, but the public-input path selects no corrected output and changes no source file. Verify original pages and rights independently before scientific use.

Any preview requires visual inspection of scene order, text legibility, article attribution, boundaries and caption-to-action accuracy. The [v0.3.26 release MP4](https://github.com/HyunStudio/BioSURE-AI4S/releases/download/v0.3.26/biosure-demo-v0322.mp4) is byte-identical to the verified v0.3.22 live-trial recording; Pages streams it from the same-origin `docs/media/` path. Confirm source tag, ZIP, CI, Pages, playback and released bytes before submission. The v0.3.19 workbench and v0.3.14 selected-edit videos remain historical.

The earlier visually reviewed but unpublished local candidate, its silent caption transcript, measured duration, SHA-256 and scene limitations are recorded in [`current-preview.md`](current-preview.md). It is a historical QA reference, not the release MP4 or a source ZIP asset. The release page gives the current video's asset digest.
