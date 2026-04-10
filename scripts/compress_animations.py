#!/usr/bin/env python
"""Script to compress WebP animations by scaling and optimizing.

Reduces file size significantly by:
1. Scaling to actual display size (200x159)
2. Optionally reducing frame count
"""
import os
import sys
from pathlib import Path
from PIL import Image

# Target size for desktop pet display
TARGET_WIDTH = 200
TARGET_HEIGHT = 159


def compress_webp_animation(input_path: Path, output_path: Path, scale: float = None) -> dict:
    """Compress a WebP animation file.

    Args:
        input_path: Path to input WebP file.
        output_path: Path to output compressed WebP file.
        scale: Optional custom scale factor. If None, scales to TARGET_WIDTH.

    Returns:
        Dict with compression stats.
    """
    print(f"Processing: {input_path.name}")

    # Open original
    img = Image.open(input_path)
    original_size = os.path.getsize(input_path)

    # Calculate target size
    if scale is None:
        # Scale to target width, maintain aspect ratio
        ratio = TARGET_WIDTH / img.width
        target_w = TARGET_WIDTH
        target_h = int(img.height * ratio)
    else:
        target_w = int(img.width * scale)
        target_h = int(img.height * scale)

    # Get frame count
    n_frames = getattr(img, 'n_frames', 1)
    duration = getattr(img, 'duration', 40)  # Default 40ms per frame (25fps)

    print(f"  Original: {img.width}x{img.height}, {n_frames} frames, {original_size/1024/1024:.1f} MB")
    print(f"  Target: {target_w}x{target_h}")

    # Extract and resize all frames
    frames = []
    for i in range(n_frames):
        img.seek(i)
        # Copy frame and resize
        frame = img.copy()
        resized = frame.resize((target_w, target_h), Image.Resampling.LANCZOS)
        frames.append(resized)

    # Save as animated WebP
    if len(frames) > 1:
        # Save first frame with append images for rest
        frames[0].save(
            output_path,
            format='WEBP',
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=0,  # Loop forever
            lossless=False,
            quality=85,  # Good quality compression
        )
    else:
        # Single frame
        frames[0].save(
            output_path,
            format='WEBP',
            lossless=False,
            quality=85,
        )

    # Get compressed size
    compressed_size = os.path.getsize(output_path)
    reduction = (1 - compressed_size / original_size) * 100

    print(f"  Compressed: {compressed_size/1024/1024:.1f} MB ({reduction:.1f}% reduction)")

    return {
        'input': str(input_path),
        'output': str(output_path),
        'original_size': original_size,
        'compressed_size': compressed_size,
        'reduction': reduction,
        'frames': n_frames,
        'original_dimensions': (img.width, img.height),
        'new_dimensions': (target_w, target_h),
    }


def main():
    """Compress all WebP animations in pets/default/animations/."""
    animations_dir = Path("pets/default/animations")

    if not animations_dir.exists():
        print(f"Error: Directory not found: {animations_dir}")
        sys.exit(1)

    # Find all WebP files
    webp_files = list(animations_dir.glob("*.webp"))

    # Exclude already compressed files (small ones)
    large_files = [f for f in webp_files if os.path.getsize(f) > 10 * 1024 * 1024]  # > 10MB

    print(f"Found {len(large_files)} large WebP files to compress")
    print("=" * 50)

    results = []
    total_original = 0
    total_compressed = 0

    for webp_file in large_files:
        # Create output filename (same name, will replace original)
        # Or create with _compressed suffix for backup
        output_file = webp_file  # Direct replacement

        # Create backup first
        backup_file = webp_file.with_suffix('.webp.backup')
        if not backup_file.exists():
            print(f"  Creating backup: {backup_file.name}")
            os.rename(webp_file, backup_file)
            input_file = backup_file
        else:
            input_file = backup_file

        try:
            result = compress_webp_animation(input_file, output_file)
            results.append(result)
            total_original += result['original_size']
            total_compressed += result['compressed_size']
        except Exception as e:
            print(f"  Error: {e}")
            # Restore backup if compression failed
            if backup_file.exists() and not webp_file.exists():
                os.rename(backup_file, webp_file)

        print()

    # Summary
    print("=" * 50)
    print("COMPRESSION SUMMARY")
    print("=" * 50)

    for r in results:
        print(f"{Path(r['input']).name}:")
        print(f"  {r['original_dimensions'][0]}x{r['original_dimensions'][1]} -> {r['new_dimensions'][0]}x{r['new_dimensions'][1]}")
        print(f"  {r['original_size']/1024/1024:.1f} MB -> {r['compressed_size']/1024/1024:.1f} MB ({r['reduction']:.1f}% reduction)")

    print()
    print(f"Total original: {total_original/1024/1024:.1f} MB")
    print(f"Total compressed: {total_compressed/1024/1024:.1f} MB")
    print(f"Total reduction: {(1 - total_compressed/total_original)*100:.1f}%")
    print(f"Space saved: {(total_original - total_compressed)/1024/1024:.1f} MB")


if __name__ == "__main__":
    main()