#!/usr/bin/env python3
"""
Outfit compilation builder.

Point it at a superfolder of outfit subfolders (or a single outfit folder).
Each outfit folder must contain 3 clips named for their order, and the
superfolder holds the audio file(s) that score the outfits:

    shoot/
        track_a.mp3
        track_b.mp3
        outfit_01/
            1.mp4
            2.mp4
            3.mp4
        outfit_02/
            ...

For each clip, the script scores a sliding 2-second window for sharpness
(in-focus) and stability (low motion/shake), picks the best window, cuts it,
and hard-cuts the three windows together into a 6-second compilation.

Clips play in filename order (1, 2, 3) by default. --clip-order reverse flips
that to 3, 2, 1, and --clip-order random shuffles each outfit independently —
pass --seed to make the shuffle reproducible.

Each track is divided into 6-second slots, and outfits rotate across the tracks
before advancing down them: with 6 tracks, outfits 1-6 take the first slot of
each track, outfits 7-12 the second slot, and so on. The first --skip-intro and
last --skip-outro seconds of every track are left out of the running (both
default to 6s). Slices repeat only once a track runs out of slots.

Requires: ffmpeg + ffprobe on PATH, and `pip install -r requirements.txt`.

Usage:
    python compile_outfits.py /path/to/superfolder
    python compile_outfits.py /path/to/superfolder --skip-intro 0 --skip-outro 0
    python compile_outfits.py /path/to/superfolder --no-music
    python compile_outfits.py /path/to/superfolder --music other_track.mp3
    python compile_outfits.py /path/to/superfolder --output-dir /path/to/out
    python compile_outfits.py /path/to/superfolder --clip-order reverse
    python compile_outfits.py /path/to/superfolder --clip-order random --seed 7
"""

import argparse
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".flac"}
CLIP_SECONDS = 2.0
# Clips are picked by filename stem, in this order. Anything else in the folder
# (previous compilations, stray files) is ignored.
CLIP_STEMS = ("1", "2", "3")

# Compilations collect here inside the superfolder rather than scattering into
# the source folders. --output-dir overrides it; --output-alongside restores the
# old per-folder placement.
OUTPUT_DIR_NAME = "compilations"
COMPILATION_SECONDS = len(CLIP_STEMS) * CLIP_SECONDS
# How the clips of one outfit are ordered in the compilation. "sequential" is
# filename order (1, 2, 3); "reverse" is 3, 2, 1; "random" shuffles each outfit
# independently.
CLIP_ORDERS = ("sequential", "reverse", "random")
DEFAULT_CLIP_ORDER = "sequential"
# Seconds trimmed off the head and tail of the track before it is divided into
# slots, so outfits don't land on an intro fade-in or a trailing outro.
DEFAULT_SKIP_SECONDS = 6.0
# Every slot but the first starts mid-waveform, so fade in as well as out.
MUSIC_FADE_IN_SECONDS = 0.25
MUSIC_FADE_SECONDS = 0.5

# Candidate window start points are sampled every STRIDE_SECONDS.
STRIDE_SECONDS = 0.1
# Fraction of the clip trimmed off the front/back before searching, to avoid
# the shake right as someone hits record / reaches to stop it.
START_BUFFER_FRAC = 0.12
END_BUFFER_FRAC = 0.08
# How much weight motion (instability) gets relative to sharpness. Higher =
# prefers steadier footage even if slightly softer.
MOTION_WEIGHT = 0.6


def find_best_window(video_path: Path, clip_seconds: float = CLIP_SECONDS) -> float:
    """Return the start time (seconds) of the best `clip_seconds` window."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps else 0

    if duration <= clip_seconds:
        cap.release()
        return 0.0

    # Downsample analysis to keep this fast on long clips: sample at ~10fps.
    analysis_fps = min(fps, 10.0)
    frame_stride = max(int(round(fps / analysis_fps)), 1)

    sharpness = []  # one entry per analyzed frame
    motion = []
    timestamps = []

    prev_gray = None
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % frame_stride == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (320, int(320 * gray.shape[0] / gray.shape[1])))
            sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
            if prev_gray is not None and prev_gray.shape == gray.shape:
                m = float(np.mean(cv2.absdiff(gray, prev_gray)))
            else:
                m = 0.0
            sharpness.append(sharp)
            motion.append(m)
            timestamps.append(idx / fps)
            prev_gray = gray
        idx += 1
    cap.release()

    if len(timestamps) < 2:
        return 0.0

    sharpness = np.array(sharpness)
    motion = np.array(motion)
    timestamps = np.array(timestamps)

    def norm(arr):
        span = arr.max() - arr.min()
        return (arr - arr.min()) / span if span > 1e-9 else np.zeros_like(arr)

    n_sharp = norm(sharpness)
    n_motion = norm(motion)
    per_frame_score = n_sharp - MOTION_WEIGHT * n_motion

    start_bound = duration * START_BUFFER_FRAC
    end_bound = duration * (1 - END_BUFFER_FRAC) - clip_seconds
    if end_bound <= start_bound:
        start_bound, end_bound = 0.0, duration - clip_seconds

    best_start, best_score = start_bound, -np.inf
    t = start_bound
    while t <= end_bound:
        mask = (timestamps >= t) & (timestamps < t + clip_seconds)
        if mask.sum() >= 2:
            score = per_frame_score[mask].mean()
            if score > best_score:
                best_score = score
                best_start = t
        t += STRIDE_SECONDS

    return round(float(best_start), 3)


def run(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n{result.stderr.decode(errors='replace')}"
        )


def cut_clip(src: Path, start: float, dest: Path, clip_seconds: float = CLIP_SECONDS):
    run([
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(src),
        "-t", f"{clip_seconds:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(dest),
    ])


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}\n{result.stderr.decode(errors='replace')}")
    return float(result.stdout.decode().strip())


def find_music(root: Path):
    """Return every audio file in `root`, sorted by name. Exits if there are none."""
    tracks = sorted(p for p in root.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    if not tracks:
        sys.exit(
            f"No audio file found in {root}. Put one or more tracks alongside the "
            f"outfit folders, pass --music, or use --no-music."
        )
    return tracks


def plan_music_slots(music_duration: float, skip_intro: float, skip_outro: float):
    """Divide the usable part of the track into COMPILATION_SECONDS-long slots.

    Returns the slot start offsets, in order. Slots sit entirely inside the
    usable region, so no slice bleeds into the skipped intro or outro. A track
    too short for even one slot returns an empty list.
    """
    region = music_duration - skip_intro - skip_outro
    n_slots = int(region // COMPILATION_SECONDS)
    return [skip_intro + i * COMPILATION_SECONDS for i in range(n_slots)]


def build_music_plan(tracks, skip_intro: float, skip_outro: float):
    """Pair each usable track with its slot offsets, dropping ones that are too short."""
    plan = []
    for track in tracks:
        duration = probe_duration(track)
        slots = plan_music_slots(duration, skip_intro, skip_outro)
        if not slots:
            print(f"  skipping {track.name}: {duration:.1f}s leaves under "
                  f"{COMPILATION_SECONDS:.0f}s after the intro/outro trim")
            continue
        plan.append((track, slots))
        print(f"  {track.name}: {len(slots)} slot(s)")

    if not plan:
        sys.exit(
            f"No usable track: every audio file is under {COMPILATION_SECONDS:.0f}s "
            f"once {skip_intro:.1f}s of intro and {skip_outro:.1f}s of outro are "
            f"trimmed. Use longer tracks or lower --skip-intro/--skip-outro."
        )
    return plan


def pick_slice(plan, index: int):
    """Rotate across tracks first, then advance down them a slot at a time.

    With 6 tracks, outfits 1-6 take the first slot of each track, outfits 7-12
    the second slot, and so on. Slot counts are per-track, so a shorter track
    wraps back to its own start sooner than a longer one.
    """
    track, slots = plan[index % len(plan)]
    return track, slots[(index // len(plan)) % len(slots)]


def add_music(video: Path, music: Path, dest: Path, music_start: float = 0.0):
    """Replace the video's audio with `music`, trimmed to length and faded."""
    duration = probe_duration(video)
    fade_out = min(MUSIC_FADE_SECONDS, duration / 2)
    fade_in = min(MUSIC_FADE_IN_SECONDS, duration / 2)
    run([
        "ffmpeg", "-y",
        "-i", str(video),
        "-ss", f"{music_start:.3f}", "-i", str(music),
        "-map", "0:v:0", "-map", "1:a:0",
        "-af", f"afade=t=in:st=0:d={fade_in:.3f},"
               f"afade=t=out:st={duration - fade_out:.3f}:d={fade_out:.3f}",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(dest),
    ])


def concat_clips(clip_paths, dest: Path):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")
        list_path = Path(f.name)
    try:
        run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_path),
            "-c", "copy",
            str(dest),
        ])
    finally:
        list_path.unlink(missing_ok=True)


def find_clips(folder: Path):
    """Return the clips named 1/2/3 in order, or None if any are missing."""
    by_stem = {
        p.stem: p for p in folder.iterdir()
        if p.suffix.lower() in VIDEO_EXTS and p.stem in CLIP_STEMS
    }
    missing = [s for s in CLIP_STEMS if s not in by_stem]
    if missing:
        print(f"  skip {folder.name}: no clip named {', '.join(missing)}")
        return None
    return [by_stem[s] for s in CLIP_STEMS]


def order_clips(clips, clip_order: str, rng: random.Random):
    """Return the clips in playback order for the given --clip-order mode.

    `clips` arrives in filename order. "random" draws from `rng`, so one seeded
    generator shared across the run keeps a whole batch reproducible while still
    shuffling each outfit independently.
    """
    if clip_order == "sequential":
        return list(clips)
    if clip_order == "reverse":
        return list(reversed(clips))
    if clip_order == "random":
        shuffled = list(clips)
        rng.shuffle(shuffled)
        return shuffled
    raise ValueError(f"Unknown clip order: {clip_order}")


def process_outfit_folder(folder: Path, output_dir: Path, music: Path = None,
                          music_offset: float = 0.0,
                          clip_order: str = DEFAULT_CLIP_ORDER,
                          rng: random.Random = None) -> bool:
    """Build one compilation. Returns True if a file was written."""
    clips = find_clips(folder)
    if clips is None:
        return False

    clips = order_clips(clips, clip_order, rng or random.Random())

    print(f"  {folder.name}: {[c.name for c in clips]} ({clip_order})")
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        segment_paths = []
        for i, clip in enumerate(clips):
            start = find_best_window(clip)
            seg = tmp / f"seg_{i}.mp4"
            print(f"    {clip.name}: best window starts at {start:.2f}s")
            cut_clip(clip, start, seg)
            segment_paths.append(seg)

        out_path = output_dir / f"{folder.name}-CV.mp4"
        if music is None:
            concat_clips(segment_paths, out_path)
        else:
            silent = tmp / "concat.mp4"
            concat_clips(segment_paths, silent)
            add_music(silent, music, out_path, music_offset)
            print(f"    music: {music.name} @ {music_offset:.1f}s")
        print(f"    -> {out_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="Outfit folder, or parent folder of outfit folders")
    parser.add_argument("--output-dir", type=Path, default=None,
                         help=f"Where to write compilations (default: <superfolder>/{OUTPUT_DIR_NAME})")
    parser.add_argument("--output-alongside", action="store_true",
                         help="Write each compilation into its own outfit folder instead")
    parser.add_argument("--music", type=Path, nargs="+", default=None,
                         help="Audio file(s) to use (default: every audio file in the superfolder)")
    parser.add_argument("--no-music", action="store_true",
                         help="Build compilations without music, ignoring any track present")
    parser.add_argument("--skip-intro", type=float, default=DEFAULT_SKIP_SECONDS,
                         help=f"Seconds of the track's head to leave unused (default: {DEFAULT_SKIP_SECONDS:.0f})")
    parser.add_argument("--skip-outro", type=float, default=DEFAULT_SKIP_SECONDS,
                         help=f"Seconds of the track's tail to leave unused (default: {DEFAULT_SKIP_SECONDS:.0f})")
    parser.add_argument("--clip-order", choices=CLIP_ORDERS, default=DEFAULT_CLIP_ORDER,
                         help=f"Order the clips play in within each compilation (default: {DEFAULT_CLIP_ORDER})")
    parser.add_argument("--seed", type=int, default=None,
                         help="Seed for --clip-order random, so the same shuffle can be reproduced")
    args = parser.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} not found on PATH. Install ffmpeg (e.g. `brew install ffmpeg`) and retry.")

    if args.music is not None and args.no_music:
        sys.exit("--music and --no-music can't be used together.")
    for track in args.music or []:
        if not track.is_file():
            sys.exit(f"Music file not found: {track}")
    if args.skip_intro < 0 or args.skip_outro < 0:
        sys.exit("--skip-intro and --skip-outro must be zero or positive.")
    if args.seed is not None and args.clip_order != "random":
        sys.exit("--seed only applies to --clip-order random.")
    if args.output_dir is not None and args.output_alongside:
        sys.exit("--output-dir and --output-alongside can't be used together.")

    root = args.path
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")

    is_outfit_folder = any(
        p.suffix.lower() in VIDEO_EXTS and p.stem in CLIP_STEMS for p in root.iterdir()
    )
    outfit_folders = [root] if is_outfit_folder else sorted(
        p for p in root.iterdir() if p.is_dir() and p.name != OUTPUT_DIR_NAME
    )

    if not outfit_folders:
        sys.exit(f"No video files or subfolders found in {root}")

    if args.no_music:
        plan = []
    else:
        tracks = args.music or find_music(root)
        print(f"Music: {len(tracks)} track(s), {COMPILATION_SECONDS:.0f}s per slot")
        plan = build_music_plan(tracks, args.skip_intro, args.skip_outro)
        # Rotation revisits a track every len(plan) outfits, so repeats start once
        # the shortest track runs out of slots.
        distinct = len(plan) * min(len(slots) for _, slots in plan)
        if len(outfit_folders) > distinct:
            print(f"Note: {len(outfit_folders)} outfit folder(s) but only {distinct} "
                  f"distinct slice(s) before the shortest track wraps; some slices repeat.")

    rng = random.Random(args.seed)
    if args.clip_order == "random":
        seed_note = f"seed {args.seed}" if args.seed is not None else "unseeded"
        print(f"Clip order: random ({seed_note})")
    else:
        print(f"Clip order: {args.clip_order}")

    print(f"Processing {len(outfit_folders)} outfit folder(s)...")
    # A single outfit folder keeps writing alongside itself; a superfolder
    # collects every compilation in one place.
    default_out = None if (is_outfit_folder or args.output_alongside) else root / OUTPUT_DIR_NAME

    built = 0
    written = {}
    for folder in outfit_folders:
        out_dir = args.output_dir or default_out or folder
        out_path = out_dir / f"{folder.name}-CV.mp4"
        if out_path in written:
            print(f"  warning: {folder.name} overwrites the compilation from "
                  f"{written[out_path]} at {out_path}")
        written[out_path] = folder.name
        music, offset = pick_slice(plan, built) if plan else (None, 0.0)
        if process_outfit_folder(folder, out_dir, music, offset,
                                 args.clip_order, rng):
            built += 1

    print(f"Done. Built {built} compilation(s).")


if __name__ == "__main__":
    main()
