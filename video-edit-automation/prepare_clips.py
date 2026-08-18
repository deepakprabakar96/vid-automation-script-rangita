#!/usr/bin/env python3
"""Normalise incoming footage into the 1/2/3 clip contract compile_outfits.py needs.

Assets arrive in one of two conventions. The newer pipeline emits descriptive
names built from a project prefix, an outfit id, a slot and a version:

    Test2_afeea_closepose_v1.jpg              pose still            {pose}
    Test2_afeea_fullbody_ref_v2.jpg           first-image candidate fullbody_ref
    Test2_afeea_fullbody_ref_upload_v1.jpg    uploaded styled ref   fullbody_ref_upload
    Test2_afeea_closepose_video_v1.mp4        video from a pose     {pose}_video
    Test2_afeea_fullbody_ref_video_v1.mp4     video from first img  fullbody_ref_video

Only the *_video assets become compilation clips. Everything sharing the
{project}_{id} prefix is one outfit, wherever in the tree it happens to sit, and
files may carry an OS duplicate marker such as " (1)" before the extension.

The older convention — a folder already holding clips named 1, 2, 3 — still
arrives too, and passes straight through untouched.

Clips are staged as symlinks, so originals keep their descriptive names and the
mapping stays recoverable. Nothing is written until --apply: the default run
prints the mapping for review, because clip order is an editorial decision.

Usage:
    python prepare_clips.py /path/to/drop                      # show the mapping
    python prepare_clips.py /path/to/drop --apply              # stage it into super/
    python prepare_clips.py /path/to/drop --apply --dest super
"""

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
CLIP_STEMS = ("1", "2", "3")

# Poses whose name spans more than one underscore-delimited token. Single-token
# poses need no entry — the parser falls back to "last token is the pose", so a
# new sidepose or walkpose works without touching this file.
KNOWN_POSE_BASES = ("fullbody_ref",)

# The order poses take in the compilation: the full-body reference opens, closer
# framings follow. Poses not listed sort alphabetically after these.
POSE_PRIORITY = ("fullbody_ref", "midpose", "closepose")

VIDEO_SLOT_SUFFIX = "_video"
DUPE_RE = re.compile(r"\s*\((\d+)\)$")
VERSION_RE = re.compile(r"_v(\d+)$")


class Asset:
    """One parsed source file, and where it sorts among its outfit's clips."""

    def __init__(self, path: Path, outfit: str, pose: str, version: int, dupe: int):
        self.path = path
        self.outfit = outfit
        self.pose = pose
        self.version = version
        self.dupe = dupe

    def pose_rank(self):
        """Sort key placing known poses in POSE_PRIORITY order, others after."""
        if self.pose in POSE_PRIORITY:
            return (0, POSE_PRIORITY.index(self.pose), "")
        return (1, 0, self.pose)

    def pick_rank(self):
        """Sort key for choosing between files filling the same pose.

        Highest version wins. A tie falls to the file with no duplicate marker,
        then to the lowest marker — the copies macOS leaves behind are the ones
        we want to ignore, not prefer.
        """
        return (-self.version, self.dupe)


def parse_asset(path: Path):
    """Parse one file into an Asset, or None if it isn't a new-schema clip."""
    if path.suffix.lower() not in VIDEO_EXTS:
        return None

    stem = path.stem

    dupe = 0
    match = DUPE_RE.search(stem)
    if match:
        dupe = int(match.group(1))
        stem = stem[: match.start()]

    version = 0
    match = VERSION_RE.search(stem)
    if match:
        version = int(match.group(1))
        stem = stem[: match.start()]

    if not stem.endswith(VIDEO_SLOT_SUFFIX):
        return None
    stem = stem[: -len(VIDEO_SLOT_SUFFIX)]

    for base in KNOWN_POSE_BASES:
        if stem.endswith("_" + base):
            outfit = stem[: -len(base) - 1]
            if outfit:
                return Asset(path, outfit, base, version, dupe)

    if "_" not in stem:
        return None
    outfit, pose = stem.rsplit("_", 1)
    if not outfit or not pose:
        return None
    return Asset(path, outfit, pose, version, dupe)


def is_legacy_outfit_folder(folder: Path) -> bool:
    """True if the folder already satisfies the 1/2/3 contract."""
    stems = {
        p.stem for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and p.stem in CLIP_STEMS
    }
    return len(stems) == len(CLIP_STEMS)


def scan(root: Path):
    """Walk `root`, returning (assets, legacy folders, ignored, unrecognised)."""
    assets = []
    legacy = []
    ignored = []          # stills and refs: real assets, just not clips
    unrecognised = []     # neither convention — a human has to decide

    if is_legacy_outfit_folder(root):
        return [], [root], [], []

    for path in sorted(root.rglob("*")):
        if path.is_dir():
            if is_legacy_outfit_folder(path):
                legacy.append(path)
            continue
        if not path.is_file() or path.name.startswith("."):
            continue
        if any(parent in legacy for parent in path.parents):
            continue
        if path.suffix.lower() not in VIDEO_EXTS:
            ignored.append(path)
            continue
        asset = parse_asset(path)
        if asset is not None:
            assets.append(asset)
        else:
            unrecognised.append(path)

    return assets, legacy, ignored, unrecognised


def group_outfits(assets):
    """Group assets by outfit, resolving versions and duplicates.

    Returns {outfit: (chosen, dropped)} where `chosen` is the ordered clip list
    and `dropped` holds the losing versions and any pose beyond the third.
    """
    by_outfit = defaultdict(lambda: defaultdict(list))
    for asset in assets:
        by_outfit[asset.outfit][asset.pose].append(asset)

    result = {}
    for outfit in sorted(by_outfit):
        chosen, dropped = [], []
        for pose_assets in by_outfit[outfit].values():
            pose_assets.sort(key=Asset.pick_rank)
            chosen.append(pose_assets[0])
            dropped.extend(pose_assets[1:])
        chosen.sort(key=Asset.pose_rank)
        dropped.extend(chosen[len(CLIP_STEMS):])
        result[outfit] = (chosen[: len(CLIP_STEMS)], dropped)
    return result


def stage(clips, dest_folder: Path, copy: bool, force: bool, apply: bool):
    """Link (or copy) `clips` into dest_folder as 1, 2, 3. Returns a status list."""
    statuses = []
    for stem, asset in zip(CLIP_STEMS, clips):
        target = dest_folder / f"{stem}{asset.path.suffix.lower()}"
        source = asset.path.resolve()

        existing = None
        for ext in VIDEO_EXTS:
            candidate = dest_folder / f"{stem}{ext}"
            if candidate.exists() or candidate.is_symlink():
                existing = candidate
                break

        if existing is not None:
            resolved = existing.resolve() if existing.is_symlink() else existing
            if resolved == source and existing == target:
                statuses.append((asset, target, "already staged"))
                continue
            if not force:
                statuses.append((asset, target, f"CONFLICT with {existing.name} (use --force)"))
                continue
            if apply:
                existing.unlink()

        statuses.append((asset, target, "copy" if copy else "link"))
        if apply:
            dest_folder.mkdir(parents=True, exist_ok=True)
            if copy:
                shutil.copy2(source, target)
            else:
                target.symlink_to(source)
    return statuses


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="Folder holding the incoming assets")
    parser.add_argument("--dest", type=Path, default=Path("super"),
                        help="Where outfit folders are staged (default: super)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually stage the clips (default: print the mapping only)")
    parser.add_argument("--copy", action="store_true",
                        help="Copy the clips instead of symlinking them")
    parser.add_argument("--force", action="store_true",
                        help="Replace staged clips that point somewhere else")
    args = parser.parse_args()

    root = args.path
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")

    assets, legacy, ignored, unrecognised = scan(root)
    outfits = group_outfits(assets)

    if not outfits and not legacy:
        sys.exit(f"No clips in either naming convention found under {root}")

    if not args.apply:
        print("Dry run — nothing will be written. Re-run with --apply to stage.\n")

    staged = skipped = 0
    for outfit, (clips, dropped) in outfits.items():
        dest_folder = args.dest / outfit
        if len(clips) < len(CLIP_STEMS):
            poses = ", ".join(c.pose for c in clips) or "none"
            print(f"{outfit}: only {len(clips)} clip(s) ({poses}) — needs "
                  f"{len(CLIP_STEMS)}, skipping")
            skipped += 1
            continue

        print(f"{outfit} -> {dest_folder}/")
        for asset, target, status in stage(clips, dest_folder, args.copy,
                                           args.force, args.apply):
            print(f"    {asset.path.name}  ->  {target.name}   [{asset.pose}, {status}]")
        for asset in dropped:
            print(f"    (dropped) {asset.path.name}   [{asset.pose} v{asset.version}]")
        staged += 1

    for folder in legacy:
        print(f"{folder}: already named 1/2/3 — left as is")

    if unrecognised:
        print(f"\nUnrecognised video files ({len(unrecognised)}) — neither convention. "
              "See \"Preparing messy input\" in AGENTS.md; clip order is an editorial "
              "decision, so these are never guessed at:")
        for path in unrecognised:
            print(f"    {path}")

    if ignored:
        print(f"\nIgnored {len(ignored)} non-video file(s) (stills, refs, audio).")

    print(f"\n{staged} outfit(s) ready, {skipped} skipped, {len(legacy)} already "
          f"in the old convention.")
    if not args.apply and staged:
        print("Re-run with --apply once the mapping above looks right.")


if __name__ == "__main__":
    main()
