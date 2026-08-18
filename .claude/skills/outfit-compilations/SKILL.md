---
name: outfit-compilations
description: Build 6-second outfit compilation videos with background music from folders of clips. Use when the user wants to compile outfit clips, build compilations or reels from a shoot, add music to outfit videos, shuffle/reverse/randomise the order clips play in, or run compile_outfits.py. Handles the setup, the folder structure, clip ordering, preparing raw camera files or pipeline-named assets (Test2_afeea_fullbody_ref_video_v1.mp4), running prepare_clips.py, and verifying the output.
---

# Outfit compilations

This project turns folders of outfit clips into 6-second compilations with music. Each outfit's
three clips are trimmed to their sharpest, steadiest 2-second window, cut together, and scored
with a distinct slice of background music.

**Read `AGENTS.md` in the project root before doing anything.** It is the single source of
truth: the folder contract, setup, every flag, how music slices are assigned, how to prepare
raw camera files, verification, and a troubleshooting table. This file only exists to point you
there.

## The short version

Users drop their outfit folders and audio tracks into `super/`, then:

```bash
.venv/bin/python video-edit-automation/compile_outfits.py super
```

Outputs land together in `super/compilations/<outfit>-CV.mp4`.

## Clip ordering

Clips play in filename order (`1`, `2`, `3`) unless told otherwise. `--clip-order` changes it:

```bash
… compile_outfits.py super --clip-order reverse            # 3 → 2 → 1
… compile_outfits.py super --clip-order random             # shuffled per outfit
… compile_outfits.py super --clip-order random --seed 7    # shuffled, reproducible
```

`random` shuffles each outfit independently, so outfits in one run differ from each other.
Always add `--seed N` when the user might want the result re-created, and tell them the seed —
without one the ordering is unrecoverable after the run. (`--seed` errors out with any mode
other than `random`.)

Clip order is an editorial decision. Keep the default unless the user asks for something else,
and if they want "a different order" without saying which, ask rather than picking one. `AGENTS.md`
has the full table of modes and when each fits.

## Before running

- Confirm `ffmpeg` and `ffprobe` are on PATH.
- Confirm `.venv/` exists; if not, create it — `AGENTS.md` has the two commands.
- Confirm at least one audio file sits directly in `super/`.
- Confirm `super/` matches the contract: each outfit folder holding clips named exactly `1`,
  `2`, `3`. If it doesn't, normalise first — see below.

That last check is where nearly every failure comes from.

## Normalising incoming footage

Clips arrive either already named `1`/`2`/`3`, or in the pipeline schema
(`Test2_afeea_fullbody_ref_video_v1.mp4`). `prepare_clips.py` handles both — run it whenever
the folders don't already match the contract:

```bash
.venv/bin/python video-edit-automation/prepare_clips.py /path/to/drop            # show the mapping
.venv/bin/python video-edit-automation/prepare_clips.py /path/to/drop --apply    # stage it
```

It groups by the `{project}_{id}` prefix, uses only `*_video` assets, puts `fullbody_ref_video`
at position `1` with poses after it, takes the highest `_v{n}`, and stages symlinks so the
originals are never renamed. `AGENTS.md` has the full rule set.

**Always run the dry-run first and show the user the mapping before `--apply`.** The mapping
fixes clip order, which is an editorial decision — report what it chose rather than presenting
it as your own judgement. Outfits with fewer than three clips are skipped; say which.

Files matching neither convention (`IMG_4821.MOV`, loose ungrouped clips) are listed as
unrecognised and are *not* handled automatically — follow "Preparing messy input" in
`AGENTS.md` and ask the user before renaming or regrouping anything.

## After running

Report the per-outfit track and offset from the log, tell the user the outputs are in
`super/compilations/`, and run the audio-hash check in `AGENTS.md` to confirm the compilations
genuinely differ rather than only appearing to.

Each outfit line also ends with the order its clips were cut in — e.g.
`outfit_01: ['3.mp4', '1.mp4', '2.mp4'] (random)`. Report that too whenever `--clip-order` was
used, along with the seed, so the user can reproduce or reject the result.
