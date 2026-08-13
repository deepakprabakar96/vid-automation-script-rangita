---
name: outfit-compilations
description: Build 6-second outfit compilation videos with background music from folders of clips. Use when the user wants to compile outfit clips, build compilations or reels from a shoot, add music to outfit videos, or run compile_outfits.py. Handles the setup, the folder structure, preparing raw camera files, and verifying the output.
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
