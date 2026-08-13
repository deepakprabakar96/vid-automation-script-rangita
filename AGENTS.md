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

Output lands next to the source clips as `<outfit_name>-CV.mp4`.

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
```

Hard requirements — the script refuses anything else:

- Each outfit folder has clips whose filenames are exactly `1`, `2`, `3` (any of `.mp4`,
  `.mov`, `.m4v`, `.avi`, `.mkv`). The number is the order they appear in the compilation.
  Other files in the folder are ignored, so previously generated `-CV.mp4` files are harmless.
- At least one audio file sits **directly** in `super/`, not inside an outfit folder
  (`.mp3`, `.m4a`, `.wav`, `.aac`, `.flac`).
- Outfit folders are processed in alphabetical order.

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

That's the whole job for a correctly-structured `super/`. Outputs appear as
`super/<outfit>/<outfit>-CV.mp4`.

Options:

| Flag | Default | What it does |
| --- | --- | --- |
| `--music FILE [FILE …]` | every audio file in `super/` | Use these tracks instead of auto-discovering |
| `--no-music` | off | Skip music entirely; the clips keep their own original audio |
| `--skip-intro SECONDS` | `6` | Leave this much off the head of every track |
| `--skip-outro SECONDS` | `6` | Leave this much off the tail of every track |
| `--output-dir DIR` | alongside each outfit folder | Write all compilations into one directory instead |

The script can also be pointed at a single outfit folder rather than a superfolder, in which
case pass the track explicitly with `--music`.

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
  outfit_01: ['1.mp4', '2.mp4', '3.mp4']
    1.mp4: best window starts at 0.48s
    music: track_a.mp3 @ 6.0s
    -> super/outfit_01/outfit_01-CV.mp4
```

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

## Working on the script itself

`video-edit-automation/compile_outfits.py` is a single file with no framework. The pieces worth
knowing:

- `find_best_window` — scores frames for sharpness (variance of Laplacian) and motion
  (frame-to-frame difference), then picks the best 2s window. `MOTION_WEIGHT` at the top trades
  steadiness against sharpness.
- `find_clips` — enforces the `1`/`2`/`3` naming contract.
- `find_music` / `plan_music_slots` / `build_music_plan` / `pick_slice` — track discovery and
  the slot-rotation arithmetic. `pick_slice` is pure arithmetic and is the place to change
  assignment behaviour.
- `cut_clip` / `concat_clips` / `add_music` — the ffmpeg calls.

Tunable constants sit together at the top of the file: `CLIP_SECONDS`, `DEFAULT_SKIP_SECONDS`,
the fade lengths, and the analysis parameters.

After any change, re-run on a superfolder with at least two outfits and two tracks, and repeat
the audio-hash check above — rotation bugs tend to look correct in the log while producing
identical audio.
