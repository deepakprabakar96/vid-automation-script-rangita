# Outfit compilation builder — agent instructions

Instructions for any coding agent (Claude, Grok, Cursor, …) driving this project. All paths
are relative to the project root — the directory containing this file. Nothing depends on that
directory's name, so it can be renamed freely.

## What this project does

`video-edit-automation/compile_outfits.py` turns a set of outfit video folders into short
social-ready compilations.

For each outfit it takes three clips, finds the sharpest and steadiest 2-second window in each,
hard-cuts those three windows together into a **6-second video**, and lays a slice of
background music underneath. Each outfit gets a *different* slice of music, so a batch of
compilations doesn't sound repetitive.

Output collects in `super/compilations/` as `<outfit_name>-CV.mp4`.

A companion script, `video-edit-automation/prepare_clips.py`, sits in front of it and turns
whatever naming convention the footage arrives in into the `1`/`2`/`3` contract below. See
"Preparing messy input".

## The folder contract

Work happens inside `super/`. It ships empty — the user drops files in whenever they want
compilations:

```
super/
    track_a.mp3              one or more audio files, directly in super/
    track_b.mp3
    outfit_01/               one folder per outfit; name it anything
        1.mp4                the three clips, named exactly 1, 2, 3
        2.mp4
        3.mp4
    outfit_02/
        1.mp4
        2.mp4
        3.mp4
    compilations/            created by the script; every <outfit>-CV.mp4 lands here
```

Hard requirements — the script refuses anything else:

- Each outfit folder has clips whose filenames are exactly `1`, `2`, `3` (any of `.mp4`,
  `.mov`, `.m4v`, `.avi`, `.mkv`). The number is the order they appear in the compilation,
  unless `--clip-order` says otherwise. Other files in the folder are ignored, so previously
  generated `-CV.mp4` files are harmless.
- At least one audio file sits **directly** in `super/`, not inside an outfit folder
  (`.mp3`, `.m4a`, `.wav`, `.aac`, `.flac`).
- Outfit folders are processed in alphabetical order. `compilations/` is skipped, so re-running
  never treats previous output as an outfit.
- Clips may be symlinks — that is how `prepare_clips.py` stages them, and both ffmpeg and
  OpenCV follow them.

## Setup

Two prerequisites. Check both before running anything:

```bash
ffmpeg -version                     # ffmpeg and ffprobe must be on PATH
python3 --version
```

If ffmpeg is missing on macOS: `brew install ffmpeg`.

Create the virtual environment (once per machine):

```bash
python3 -m venv .venv
.venv/bin/pip install -r video-edit-automation/requirements.txt
```

Use `.venv/bin/python` directly rather than activating — it works the same from any shell and
in scripts.

## Running it

```bash
.venv/bin/python video-edit-automation/compile_outfits.py super
```

That's the whole job for a correctly-structured `super/`. Every compilation lands together in
`super/compilations/<outfit>-CV.mp4`, not in the source folders. Pass `--output-alongside` to
put each one back next to its own clips.

Options:

| Flag | Default | What it does |
| --- | --- | --- |
| `--music FILE [FILE …]` | every audio file in `super/` | Use these tracks instead of auto-discovering |
| `--no-music` | off | Skip music entirely; the clips keep their own original audio |
| `--skip-intro SECONDS` | `6` | Leave this much off the head of every track |
| `--skip-outro SECONDS` | `6` | Leave this much off the tail of every track |
| `--output-dir DIR` | `super/compilations/` | Write the compilations somewhere else |
| `--output-alongside` | off | Write each compilation into its own outfit folder instead |
| `--clip-order {sequential,reverse,random}` | `sequential` | Order the clips play in within each compilation |
| `--seed N` | none | Seed for `--clip-order random`, so a shuffle can be reproduced |

The script can also be pointed at a single outfit folder rather than a superfolder, in which
case pass the track explicitly with `--music`.

## Clip ordering

By default the clips play in filename order — `1`, then `2`, then `3` — so the numbering the
user chose when preparing the folder is the cut they get. `--clip-order` changes that:

| Value | Playback order | When to use it |
| --- | --- | --- |
| `sequential` (default) | 1 → 2 → 3 | The deliberate edit: wide, mid, close-up detail |
| `reverse` | 3 → 2 → 1 | Open on the detail shot and pull out to the full look |
| `random` | shuffled per outfit | Variety across a large batch, where no single order is meant |

`random` shuffles **each outfit independently**, so two outfits in the same run usually get
different orders. Without `--seed` every run reshuffles; with `--seed N` the whole batch is
reproducible — the same seed, superfolder, and outfit set always yields the same orders. Pass
the seed whenever a result might need re-creating, and record it alongside the output.

`--seed` is rejected with any other `--clip-order`, since it would have no effect.

Ordering is applied *after* clips are matched to the `1`/`2`/`3` contract, so it never changes
which clips are used or which window is picked from each — only the sequence they are cut in.
The chosen order is echoed per outfit in the log, e.g.
`outfit_01: ['3.mp4', '1.mp4', '2.mp4'] (random)`.

Note that clip order is an editorial decision. Do not reach for `random` or `reverse` on a
user's behalf — use the default unless they asked for something else.

## How music is assigned

Worth understanding, because it explains the offsets in the log.

Each track is trimmed by `--skip-intro` at the head and `--skip-outro` at the tail, and what
remains is divided into whole 6-second **slots**. Outfits then rotate across tracks before
advancing down them. With 4 tracks:

```
outfit 1 → track A, slot 0     outfit 5 → track A, slot 1
outfit 2 → track B, slot 0     outfit 6 → track B, slot 1
outfit 3 → track C, slot 0     …
outfit 4 → track D, slot 0
```

So consecutive outfits use *different songs*, and a song is only revisited a full pass later,
at a later point in the track. Slot counts are per-track, so a short track wraps back to its
own start sooner than a long one. Slices repeat only when a track runs out of slots — the
script prints a note when that will happen.

For `n` outfits over `t` tracks with no repeats at all, each track needs `ceil(n/t)` slots,
i.e. roughly `12 + 6 * ceil(n/t)` seconds of runtime.

Music replaces the clips' original audio, with a 0.25s fade-in and 0.5s fade-out.

## Preparing messy input

Footage rarely arrives in the required shape. Before running the script, get it there.

**Assets in the pipeline naming schema.** The generation pipeline emits descriptive filenames
rather than `1`/`2`/`3`:

| asset | slot | example |
| --- | --- | --- |
| pose still | `{pose}` | `Test2_afeea_closepose_v1.jpg` |
| first-image candidate | `fullbody_ref` | `Test2_afeea_fullbody_ref_v2.jpg` |
| uploaded styled ref | `fullbody_ref_upload` | `Test2_afeea_fullbody_ref_upload_v1.jpg` |
| video from a pose | `{pose}_video` | `Test2_afeea_closepose_video_v1.mp4` |
| video from the first image | `fullbody_ref_video` | `Test2_afeea_fullbody_ref_video_v1.mp4` |

`video-edit-automation/prepare_clips.py` normalises these into the `1`/`2`/`3` contract. It
never touches the originals — it stages symlinks named `1`, `2`, `3` inside `super/`, so the
descriptive names and the mapping both survive:

```bash
.venv/bin/python video-edit-automation/prepare_clips.py /path/to/drop            # show the mapping
.venv/bin/python video-edit-automation/prepare_clips.py /path/to/drop --apply    # stage it
```

The rules it applies:

- **Only `*_video` assets become clips.** Stills, refs and uploads are counted and ignored.
- **One outfit per `{project}_{id}` prefix** (`Test2_afeea`), wherever in the tree the files sit.
  Clips for one outfit can be spread across folders.
- **Order**: `fullbody_ref_video` is clip `1`, then poses in `POSE_PRIORITY` order (`midpose`,
  `closepose`), then any unlisted pose alphabetically. New single-token poses need no code
  change; a new multi-token slot name needs an entry in `KNOWN_POSE_BASES`.
- **Highest `_v{n}` wins** within a slot. OS duplicate markers (`… (1).mp4`) are recognised and
  lose to the unsuffixed file.
- Fewer than three clips ⇒ that outfit is reported and skipped, the rest still stage.
- Folders already holding `1`/`2`/`3` pass through untouched, so the two conventions can arrive
  in the same drop.

It is **dry-run by default**. Show the user the printed mapping and let them confirm before
`--apply` — the mapping decides clip order, which is editorial. `--force` is needed to re-point
a clip that is already staged, and `--copy` writes real copies instead of symlinks (use it when
the source volume might be unmounted later).

**Clips not named 1/2/3.** Camera files land as `IMG_4821.MOV`, `DSC_0032.mp4`, etc. Decide
the order deliberately — the convention for these compilations is wide/front shot first,
mid-range second, close-up detail third. Then rename:

```bash
cd super/outfit_01
mv IMG_4821.MOV 1.mp4          # keep the container; just rename
```

If the intended order is capture order, list by modification time first and check it looks
right before renaming anything:

```bash
ls -lt --time-style=long-iso        # newest first; on macOS: ls -lt
```

Never rename in bulk without showing the user the mapping first — clip order is an editorial
decision, not a mechanical one.

**Clips loose in one folder rather than grouped per outfit.** Ask the user how clips group
into outfits; do not guess from filenames or timestamps. Then create one folder per outfit and
move the three clips in.

**More or fewer than three clips.** The script requires exactly the three named `1`, `2`, `3`.
If an outfit has five candidates, ask which three to use rather than picking. If it has two,
that outfit can't be built — report it and continue with the rest.

**Mixed containers.** `.mov` and `.mp4` in the same outfit are fine; the script re-encodes each
window anyway.

## Verifying the result

The log prints, per outfit, the window chosen from each clip and the track and offset used:

```
Clip order: sequential
  outfit_01: ['1.mp4', '2.mp4', '3.mp4'] (sequential)
    1.mp4: best window starts at 0.48s
    music: track_a.mp3 @ 6.0s
    -> super/outfit_01/outfit_01-CV.mp4
```

The bracketed list is the actual playback order, so with `--clip-order` it doubles as the
check that the requested ordering took effect. Report it back to the user along with the seed
when the run was random.

To confirm the music slices really are distinct rather than merely logged as distinct, hash the
audio of each output — every digest should differ:

```bash
for f in super/*/*-CV.mp4; do ffmpeg -v error -i "$f" -map 0:a -f md5 -; done | sort | uniq -d
```

Any output from that command means two compilations share identical audio.

Check shape with:

```bash
ffprobe -v error -show_entries stream=codec_type -show_entries format=duration \
    -of csv=p=0 super/outfit_01/outfit_01-CV.mp4
```

Expect `video`, `audio`, and a duration of about 6 seconds.

## Troubleshooting

| Message | Cause and fix |
| --- | --- |
| `No audio file found in super` | No track directly in `super/`. Add one, pass `--music`, or use `--no-music`. |
| `No usable track: every audio file is under 6s once …` | Every track is too short after trimming (needs ~18s minimum at the defaults). Use longer tracks or lower `--skip-intro`/`--skip-outro`. |
| `skipping <track>: N.Ns leaves under 6s after the intro/outro trim` | Informational — that one track is dropped, the rest still run. |
| `skip <folder>: no clip named 2, 3` | That outfit folder lacks correctly named clips. See "Preparing messy input". |
| `No video files or subfolders found in …` | Pointed at an empty `super/`, or at the wrong directory. |
| `ffmpeg not found on PATH` | Install ffmpeg (`brew install ffmpeg`). |
| `ModuleNotFoundError: No module named 'cv2'` | Run via `.venv/bin/python`, or create the venv per "Setup". |
| `Note: N outfit folder(s) but only M distinct slice(s) …` | Informational — some outfits will reuse a slice. Add more or longer tracks to avoid. |
| `--seed only applies to --clip-order random.` | `--seed` was passed without `--clip-order random`. Add it, or drop the seed. |
| `<outfit>: only N clip(s) … skipping` | `prepare_clips.py` found fewer than three `*_video` assets for that prefix. Wait for the rest, or build that outfit by hand. |
| `CONFLICT with <name> (use --force)` | A clip is already staged pointing elsewhere — usually a newer `_v{n}` arrived. Re-run with `--force` once the new mapping looks right. |
| `Unrecognised video files …` | Matched neither convention. Follow "Clips not named 1/2/3" below it. |
| `No clips in either naming convention found under …` | `prepare_clips.py` was pointed at the wrong folder. |
| `--output-dir and --output-alongside can't be used together.` | Pick one. |
| `argument --clip-order: invalid choice` | Only `sequential`, `reverse`, and `random` are accepted. |
| A random run can't be reproduced | It was run without `--seed`; the order is gone. Re-run with a seed to lock future batches. |

## Working on the script itself

`video-edit-automation/compile_outfits.py` is a single file with no framework. The pieces worth
knowing:

- `find_best_window` — scores frames for sharpness (variance of Laplacian) and motion
  (frame-to-frame difference), then picks the best 2s window. `MOTION_WEIGHT` at the top trades
  steadiness against sharpness.
- `find_clips` — enforces the `1`/`2`/`3` naming contract, always returning filename order. The
  contract is deliberately narrow: schema knowledge lives in `prepare_clips.py`, not here, so
  new naming conventions never reach this file.
- `order_clips` — applies `--clip-order` to that list. Pure and side-effect free; `random` draws
  from a single `random.Random` created in `main`, so one seed governs a whole batch while each
  outfit still shuffles independently. New ordering modes go here plus `CLIP_ORDERS`.
- `find_music` / `plan_music_slots` / `build_music_plan` / `pick_slice` — track discovery and
  the slot-rotation arithmetic. `pick_slice` is pure arithmetic and is the place to change
  assignment behaviour.
- `cut_clip` / `concat_clips` / `add_music` — the ffmpeg calls.

`video-edit-automation/prepare_clips.py` is the normalisation layer in front of it:

- `parse_asset` — pulls outfit, pose, version and duplicate marker off one filename, stripping
  them in that order (extension, ` (N)`, `_v{n}`, `_video`). Returns `None` for anything that
  isn't a new-schema clip.
- `group_outfits` — groups by outfit, resolves version/duplicate races via `Asset.pick_rank`,
  and orders the winners via `Asset.pose_rank`.
- `stage` — writes the symlinks, and is the only function that touches the filesystem; it is a
  no-op unless `--apply` is passed.
- `POSE_PRIORITY` and `KNOWN_POSE_BASES` at the top are what a new slot name usually needs.

Tunable constants sit together at the top of the file: `CLIP_SECONDS`, `DEFAULT_SKIP_SECONDS`,
`CLIP_ORDERS` / `DEFAULT_CLIP_ORDER`, the fade lengths, and the analysis parameters.

After any change, re-run on a superfolder with at least two outfits and two tracks, and repeat
the audio-hash check above — rotation bugs tend to look correct in the log while producing
identical audio.

Ordering changes need the same distrust of the log: verify the rendered file, not just the
printed list. Build fixture clips whose *content* identifies them (a distinct tone or a big
number burned into each), run every mode, and confirm the output plays them in the logged
order. Also re-run `--clip-order random --seed N` twice and diff the logs — they must match.
