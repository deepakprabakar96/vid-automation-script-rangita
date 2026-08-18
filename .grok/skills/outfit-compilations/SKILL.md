---
name: outfit-compilations
description: Build 6-second outfit compilation videos with background music from folders of clips. Use when the user wants to compile outfit clips, build compilations or reels from a shoot, add music to outfit videos, shuffle/reverse/randomise the order clips play in, or run compile_outfits.py. Handles the setup, the folder structure, clip ordering, preparing raw camera files, and verifying the output.
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

Outputs land as `super/<outfit>/<outfit>-CV.mp4`.

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
- Confirm `super/` actually matches the contract: each outfit folder holding clips named
  exactly `1`, `2`, `3`, and at least one audio file directly in `super/`.

That last check is where nearly every failure comes from. If clips are named `IMG_4821.MOV` or
sitting loose rather than grouped per outfit, follow the "Preparing messy input" section of
`AGENTS.md` — and ask the user before renaming or regrouping anything, since clip order is an
editorial decision.

## After running

Report the per-outfit track and offset from the log, and run the audio-hash check in
`AGENTS.md` to confirm the compilations genuinely differ rather than only appearing to.

Each outfit line also ends with the order its clips were cut in — e.g.
`outfit_01: ['3.mp4', '1.mp4', '2.mp4'] (random)`. Report that too whenever `--clip-order` was
used, along with the seed, so the user can reproduce or reject the result.
