# OttoAlign2

> The web interface, logs, and reports are in French. The code keeps technical names in English.

![OttoAlign2 Interface](OttoAlign2.png)

## Overview

OttoAlign2 automatically aligns clips from a target AAF or PTX session to the audio of a reference session. It selects a robust GCC correlation anchor per physical source file, then applies the same integer shift to its grouped placements to preserve phase coherence. It targets post-production workflows where multiple microphones cover the same source; it does not replace critical listening or final validation in the DAW.

## Features

- Processes all tracks and target clips that overlap with the reference.
- Lazy loading: only the actually overlapping portion is loaded, even if the source file lasts dozens of minutes.
- Sample rate read from each WAV; both media in a pair must share the same sample rate.
- Delay curve computed on the first channel, then applied identically to all channels of the target media.
- Configurable delay search, limited to ±150 ms by default.
- `OttoAlign_Report.txt` report listing aligned clips, skipped clips, and their average correction; preflight skips include track, clip, TC In/Out and duration.
- ZIP extraction protected against paths escaping the working directory; 2 GB HTTP limit for the full request.

### Non-destructive PTX processing

For each eligible PTX placement, OttoAlign2:

1. reads only the visible portion that overlaps with the reference;
2. copies the full source WAV into a temporary render and replaces only that audio portion;
3. calls `pt_api.relink_clip()` to create a new independent WAV, with a new BWF/PTX media identity;
4. retargets only the affected placement and assigns it a unique clip name (`_ALIGNED`, `_ALIGNED_2`, etc.).

The original PTX and its WAVs are never overwritten. Samples outside the processed portion remain those of the source file. The new WAV keeps the container and PCM subtype of the Pro Tools media, while renewing the metadata needed for relinking.

Production validation covers two independent **native Pro Tools** PTX layouts. The first aligned 388 of 404 placements against a roughly 42-minute reference. The second aligned 226 of 236 placements, grew a zero-suffix catalog from 71 to 297 media, produced no missing timeline media, and preserved a byte-for-byte no-op save. This second case also validates reconstruction of a 31-byte `0x1001` identity containing a false empty-block signature. Premiere variable `0x2106` headers and virtual clips can be read by `pt_api` 1.3.9, but their relink write path is not validated: Pro Tools rejected the `target4` outputs with `End of stream encountered`.

Before rendering a PTX placement, OttoAlign calls the read-only `pt_api.get_relink_write_status()` preflight. A known Premiere variable-header virtual clip is **skipped safely**: it remains unchanged in the copied PTX, creates no aligned WAV and receives no `_ALIGNED` suffix. `OttoAlign_Report.txt` records its track, clip name, TC In, TC Out (end boundary), duration and the reason. The job continues with other eligible placements. This is a safeguard, not Premiere relink support.

Validated workaround: consolidate affected clips in Pro Tools before running OttoAlign. On `target4`, consolidation produced a native 151-byte media header; OttoAlign completed normally and the resulting `target4_consolidated_otto.ptx` opened in Pro Tools. The tested clip had no additional handles. A wider consolidation followed by trimming is the recommended candidate when handles are needed, but that variant has not yet received the same manual validation.

### AAF processing

The legacy AAF path writes WAVs suffixed `_ottoaligned`, modifies locators in a read-write copy of the AAF, then passes the output to `orchestrator.py`. It is maintained, but the extensive Pro Tools validation described above covers the PTX path.

## Installation and usage

The currently validated environment uses Python 3.11.

```bash
python -m pip install -r requirements.txt
python server.py
```

Then open `http://localhost:8081`.

Each archive must contain exactly one complete `.aaf` or `.ptx` session, with an `Audio Files` folder placed alongside that session. Folders can be nested within the ZIP, but the session/folder pair must be unambiguous.

The `OttoAligned_Result.zip` result contains:

- `OttoAligned.ptx` or `OttoAligned.aaf`;
- the `Audio Files` folder required for the output;
- `OttoAlign_Report.txt`.

For a PTX target, the ZIP contains the target's original WAVs and the new aligned WAVs, since the session may still reference both families. The server then deletes the extracted data and keeps the final ZIP until download or cache clearing.

## Explicit limitations

- Physical media must be WAV files. The PTX path requires the Pro Tools layouts and metadata documented by the installed version of `pt_api`. Premiere virtual clips with variable headers are intentionally preserved and reported as skipped; they are not relinked.
- An overlap of less than 0.05 seconds is skipped.
- The reference and target media of a pair must have the same sample rate; no resampling is performed.
- The delay is computed from the first channel. The same curve is imposed on the other channels; no independent per-channel alignment is performed.
- The default search window is ±150 ms. A larger real-world offset will not be found without increasing `max_shift_ms` on a direct engine call.
- The DSP may introduce zeros at boundaries when the curve requests samples located outside the available portion.
- OttoAlign reads up to one second of available context on each side of a placement for analysis and rendering. This reduces edge artifacts while bounding processing cost; unusually wide handles still require a dedicated workflow validation.
- PTX generates a full independent WAV per aligned placement. This safeguard prevents shared media from changing elsewhere in the timeline, but can significantly increase the size of the result.
- A direct call refuses to overwrite an existing output session or an existing `_ottoaligned` WAV.
- Output PTX files must remain alongside their own `Audio Files` folder; internal PTX catalog names are never interpreted as system paths.
- In AAF, Clip Gain, Clip Mute, effects, complex transitions, and DAW-specific metadata are not guaranteed. Placements sharing the same mob/media do not benefit from the per-placement isolation offered by PTX relinking; an already-present `_ottoaligned` output name is refused rather than overwritten.
- Jobs are kept in memory by the Flask process. A restart loses their state, and this local server is not a distributed or multi-instance architecture.
- The 2 GB limit applies to the compressed request; no separate limit is currently imposed on the decompressed size of archives.

## `pt_api` dependency

`requirements.txt` pins `pt_api` to the `v1.3.9` tag. The application may process a mixed session containing Premiere-derived clips because the known unsafe placements are skipped; it must not be presented as supporting Premiere-derived PTX relinking.

---

*Designed by Sébastien Bédard*
