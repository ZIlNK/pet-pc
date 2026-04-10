#!/usr/bin/env python
"""Script to compress remaining WebP animations."""
import os
import sys
from pathlib import Path
from PIL import Image

TARGET_WIDTH = 200


def compress_webp_animation(input_path: Path, output_path: Path) -> dict:
    """Compress a WebP animation file."""
    print(f"Processing: {input_path.name}")

    img = Image.open(input_path)
    original_size = os.path.getsize(input_path)

    ratio = TARGET_WIDTH / img.width
    target_w = TARGET_WIDTH
    target_h = int(img.height * ratio)

    n_frames = getattr(img, 'n_frames', 1)
    duration = getattr(img, 'duration', 40)

    print(f"  Original: {img.width}x{img.height}, {n_frames} frames, {original_size/1024/1024:.1f} MB")
    print(f"  Target: {target_w}x{target_h}")

    frames = []
    for i in range(n_frames):
        img.seek(i)
        frame = img.copy()
        resized = frame.resize((target_w, target_h), Image.Resampling.LANCZOS)
        frames.append(resized)

    if len(frames) > 1:
        frames[0].save(
            output_path,
            format='WEBP',
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=0,
            lossless=False,
            quality=85,
        )
    else:
        frames[0].save(output_path, format='WEBP', lossless=False, quality=85)

    compressed_size = os.path.getsize(output_path)
    reduction = (1 - compressed_size / original_size) * 100

    print(f"  Compressed: {compressed_size/1024/1024:.1f} MB ({reduction:.1f}% reduction)")

    return {
        'original_size': original_size,
        'compressed_size': compressed_size,
        'reduction': reduction,
    }


def main():
    """Compress remaining large WebP files."""
    animations_dir = Path("pets/default/animations")

    # Files that still need compression (>10MB and no backup exists)
    large_files = [
        'read.webp',
        'sit.webp',
        'sit1.webp',
        'sleep.webp',
        'write.webp',
    ]

    total_original = 0
    total_compressed = 0

    for filename in large_files:
        filepath = animations_dir / filename
        if not filepath.exists():
            print(f"Skipping {filename} - not found")
            continue

        if os.path.getsize(filepath) < 10 * 1024 * 1024:
            print(f"Skipping {filename} - already small")
            continue

        backup_file = filepath.with_suffix('.webp.backup')

        # Create backup
        if not backup_file.exists():
            print(f"Creating backup: {backup_file.name}")
            import shutil
            shutil.copy(filepath, backup_file)

        try:
            result = compress_webp_animation(backup_file, filepath)
            total_original += result['original_size']
            total_compressed += result['compressed_size']
        except Exception as e:
            print(f"  Error: {e}")

        print()

    # Also show totals for already compressed files
    already_compressed = ['bored.webp', 'eat.webp', 'head.webp', 'head1_aligned.webp']
    for filename in already_compressed:
        filepath = animations_dir / filename
        backup_file = filepath.with_suffix('.webp.backup')
        if backup_file.exists():
            total_original += os.path.getsize(backup_file)
            total_compressed += os.path.getsize(filepath)

    print("=" * 50)
    print(f"Total original: {total_original/1024/1024:.1f} MB")
    print(f"Total compressed: {total_compressed/1024/1024:.1f} MB")
    print(f"Total reduction: {(1 - total_compressed/total_original)*100:.1f}%")
    print(f"Space saved: {(total_original - total_compressed)/1024/1024:.1f} MB")


if __name__ == "__main__":
    main()