# Outfit compilation builder

Turns folders of outfit clips into 6-second compilation videos with background music.

Each outfit contributes three clips. The tool finds the sharpest, steadiest 2-second window in
each one, cuts them together, and lays a slice of music underneath — a *different* slice for
every outfit, so a whole shoot's worth of compilations doesn't sound repetitive.

## Requirements

- **ffmpeg** (provides `ffmpeg` and `ffprobe`) — `brew install ffmpeg` on macOS
- **Python 3**

## Setup

Once per machine, from this directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -r video-edit-automation/requirements.txt
```

## Use

**0. If your clips aren't named `1`, `2`, `3` yet** — footage from the generation pipeline
arrives as `Test2_afeea_fullbody_ref_video_v1.mp4` and the like. Normalise it first:

```bash
.venv/bin/python video-edit-automation/prepare_clips.py /path/to/drop            # show the mapping
.venv/bin/python video-edit-automation/prepare_clips.py /path/to/drop --apply    # stage into super/
```

It groups everything sharing a `{project}_{id}` prefix into one outfit, puts the
`fullbody_ref_video` first, picks the highest `_v{n}` of each slot, ignores stills, and stages
symlinks named `1`/`2`/`3` — your originals keep their names. It prints the mapping and writes
nothing until you pass `--apply`.

**1. Put your files in `super/`** — one folder per outfit, clips named `1`, `2`, `3` in the
order they should appear, plus one or more music tracks loose in `super/`:

```
super/
    track_a.mp3
    track_b.mp3
    navy_blazer/
        1.mp4
        2.mp4
        3.mp4
    linen_shirt/
        1.mp4
        2.mp4
        3.mp4
```

Name the outfit folders whatever you like. The clips must be named exactly `1`, `2`, `3`, and
they play in that order unless you pass `--clip-order` (see below).

**2. Run it:**

```bash
.venv/bin/python video-edit-automation/compile_outfits.py super
```

**3. Collect the results** — every compilation lands together in `super/compilations/`:

```
super/compilations/navy_blazer-CV.mp4
super/compilations/linen_shirt-CV.mp4
```

Pass `--output-alongside` if you'd rather each one sat next to its own clips.

`super/` is yours to empty and refill whenever you want a new batch.

## Common adjustments

```bash
# leave more of the track's start and end unused (default 6 seconds each)
… compile_outfits.py super --skip-intro 20 --skip-outro 10

# use specific tracks instead of everything in super/
… compile_outfits.py super --music intro.mp3 outro.mp3

# no music; keep the clips' own audio
… compile_outfits.py super --no-music

# send the compilations somewhere other than super/compilations/
… compile_outfits.py super --output-dir ./exports

# put each compilation back in its own outfit folder
… compile_outfits.py super --output-alongside

# play the clips back to front: 3, 2, 1
… compile_outfits.py super --clip-order reverse

# shuffle each outfit's clips; --seed makes the shuffle repeatable
… compile_outfits.py super --clip-order random --seed 7
```

## Clip order

By default clip `1` plays, then `2`, then `3` — the order you chose when you named them.
`--clip-order reverse` flips that to `3, 2, 1`, and `--clip-order random` shuffles every outfit
separately, so a batch doesn't fall into the same rhythm each time.

Random ordering picks fresh each run. Add `--seed N` to lock it in: the same seed over the same
folders always produces the same orders, so a batch you like can be rebuilt exactly. Without a
seed, the order is only recorded in that run's log. Each outfit's line shows what was used:

```
  navy_blazer: ['3.mp4', '1.mp4', '2.mp4'] (random)
```

## How the music is divided

Each track is trimmed at both ends, and the rest is split into 6-second slots. Outfits rotate
across tracks before moving further into any one of them — with four tracks, the first four
outfits use the opening slot of tracks A, B, C, D; the next four use the second slot of A, B,
C, D. Consecutive outfits therefore always use different songs.

For no repeats at all across `n` outfits and `t` tracks, each track needs about
`12 + 6 × ceil(n/t)` seconds. The tool warns you when slices will start repeating.

## Working with a coding agent

`AGENTS.md` holds full instructions for AI coding agents — Claude, Grok, Cursor, and others.
Point your agent at that file and it can run the whole workflow, including sorting out raw
camera files that aren't named correctly yet.

A project skill lives in both places so either agent picks it up automatically:

- Grok: `.grok/skills/outfit-compilations/` (`/outfit-compilations`)
- Claude Code: `.claude/skills/outfit-compilations/`
