# Optional current-source demo capture

The source ZIP does not contain video bytes. `scripts/render_demo_video.py` records actual interactions with the local workbench and checked-in static Judge Mode/study pages into a **new local preview**; it neither uploads nor publishes an MP4. The output path must be outside the source tree and must not exist.

Install optional capture tools in a separate environment that has Chrome available:

```text
python -m pip install playwright imageio-ffmpeg
python scripts/render_demo_video.py --root . --output ../biosure-demo-preview.mp4
```

If Chrome is not discoverable by Playwright, pass `--chrome-executable` with the path to an installed Chrome binary. The core BioSURE runtime and CI do not require these video dependencies. The script starts loopback-only servers, uses pre-existing project-authored fictional controls and one attributed CC BY 4.0 public excerpt, asserts the displayed actions, runs the policy CLI, captures a silent browser video, converts to H.264 and validates full decode, no audio and duration under 180 seconds before placing the output. It refuses to overwrite an existing file.

Browser automation, captions and CLI display are not human work, independent adjudication, source authentication, model superiority or time-saving evidence. The fictional policy contracts (5/5) are separate from one forged-reference control that now abstains (0/1 automatic repairs). This does not prove general safety. A false declared reference can still produce a false review candidate, but the public-input path selects no corrected output and changes no source file. Verify the original article pages and rights independently before scientific use.

Any preview requires visual inspection of scene order, text legibility, article attribution, boundaries and caption-to-action accuracy. The [v0.3.19 release MP4](https://github.com/HyunStudio/BioSURE-AI4S/releases/download/v0.3.19/biosure-demo-v0319.mp4) is the current public demonstration after its source tag, ZIP, CI, Pages and released bytes have been checked. The v0.3.14 selected-edit video remains historical and does not demonstrate current policy.

The earlier visually reviewed but unpublished local candidate, its silent caption transcript, measured duration, SHA-256 and scene limitations are recorded in [`current-preview.md`](current-preview.md). It is a historical QA reference, not the release MP4 or a source ZIP asset. The release page gives the current video's asset digest.
