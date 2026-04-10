#!/usr/bin/env python
"""
Build script for Desktop Pet.
Creates a standalone executable using PyInstaller.

All resources (pets, config) are stored externally to the EXE for easy user modification.

Usage:
    python scripts/build.py              # Build DesktopPet only
    python scripts/build.py --tools      # Build all tools
    python scripts/build.py --all        # Build everything
    python scripts/build.py --dir        # Build directory-based distribution (faster startup)
    python scripts/build.py --small      # Build with aggressive size optimization
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def clean_build_dirs(project_root: Path) -> None:
    """Remove build artifacts."""
    dirs_to_clean = ["build", "dist", "__pycache__"]
    for dir_name in dirs_to_clean:
        dir_path = project_root / dir_name
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
                print(f"Cleaned: {dir_path}")
            except PermissionError as e:
                print(f"Warning: Could not clean {dir_path}: {e}")
                print("  The file may be in use. Please close any running instances and try again.")
                print("  Continuing with build...")

    # Remove spec files
    for spec_file in project_root.glob("*.spec"):
        spec_file.unlink()
        print(f"Cleaned: {spec_file}")


def copy_resources_to_dist(project_root: Path, dist_dir: Path) -> None:
    """Copy resources (pets, config) to the distribution directory."""
    print("\nCopying resources to distribution directory...")

    # Copy pets directory
    pets_source = project_root / "pets"
    pets_target = dist_dir / "pets"
    if pets_source.exists():
        if pets_target.exists():
            shutil.rmtree(pets_target)
        shutil.copytree(pets_source, pets_target)
        print(f"  Copied: pets/ ({sum(1 for _ in pets_target.rglob('*'))} files)")
    else:
        print("  Warning: pets/ directory not found")

    # Copy config directory
    config_source = project_root / "config"
    config_target = dist_dir / "config"
    if config_source.exists():
        if config_target.exists():
            shutil.rmtree(config_target)
        shutil.copytree(config_source, config_target)
        print(f"  Copied: config/ ({sum(1 for _ in config_target.rglob('*'))} files)")
    else:
        print("  Warning: config/ directory not found")


def get_pyinstaller_base_args() -> list:
    """Get common PyInstaller arguments."""
    return [
        "--noconfirm",  # Overwrite without asking
        # Hidden imports for PyQt6
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        # Exclude unnecessary modules to reduce size
        "--exclude-module=tkinter",
        "--exclude-module=unittest",
        "--exclude-module=pydoc",
        "--exclude-module=doctest",
        "--exclude-module=test",
        "--exclude-module=tests",
        "--exclude-module=pytest",
        "--exclude-module=IPython",
        "--exclude-module=jupyter",
        "--exclude-module=notebook",
        "--exclude-module=sphinx",
        "--exclude-module=docutils",
        "--exclude-module=pygments",
    ]


def get_opencv_imports() -> list:
    """Get imports needed for OpenCV-based tools."""
    return [
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--collect-data=cv2",
    ]


def build_desktop_pet(project_root: Path, one_file: bool = True, small: bool = False) -> None:
    """Build the main DesktopPet executable."""
    print("\n" + "=" * 50)
    print("Building DesktopPet...")
    print("=" * 50)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=DesktopPet",
        "--windowed",  # No console window
    ]
    cmd.extend(get_pyinstaller_base_args())

    if small:
        cmd.extend(_get_small_excludes())

    if one_file:
        cmd.append("--onefile")

    cmd.append(str(project_root / "main.py"))

    print(f"Mode: {'single file' if one_file else 'directory'}")
    print("Resources: External (not bundled)")

    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        output_dir = project_root / "dist"
        copy_resources_to_dist(project_root, output_dir)
        print(f"\nDesktopPet built successfully!")
        print(f"Output: {output_dir / 'DesktopPet.exe'}")
    else:
        print(f"\nDesktopPet build failed with exit code {result.returncode}")
        return False

    return True


def build_green_screen_gui(project_root: Path, one_file: bool = True) -> bool:
    """Build the green screen to WebP GUI tool."""
    print("\n" + "=" * 50)
    print("Building GreenScreenToWebP GUI...")
    print("=" * 50)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=GreenScreenToWebP",
        "--windowed",
    ]
    cmd.extend(get_pyinstaller_base_args())
    cmd.extend(get_opencv_imports())

    if one_file:
        cmd.append("--onefile")

    cmd.append(str(project_root / "scripts" / "green_screen_to_webp_gui.py"))

    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        print(f"\nGreenScreenToWebP GUI built successfully!")
        print(f"Output: {project_root / 'dist' / 'GreenScreenToWebP.exe'}")
        return True
    else:
        print(f"\nGreenScreenToWebP GUI build failed")
        return False


def build_green_screen_cli(project_root: Path, one_file: bool = True) -> bool:
    """Build the green screen to WebP CLI tool."""
    print("\n" + "=" * 50)
    print("Building GreenScreenToWebP CLI...")
    print("=" * 50)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=green-screen-to-webp",
        "--console",  # Console app
    ]
    cmd.extend(get_pyinstaller_base_args())
    cmd.extend(get_opencv_imports())

    if one_file:
        cmd.append("--onefile")

    cmd.append(str(project_root / "scripts" / "green_screen_to_Webp.py"))

    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        print(f"\nGreenScreenToWebP CLI built successfully!")
        print(f"Output: {project_root / 'dist' / 'green-screen-to-webp.exe'}")
        return True
    else:
        print(f"\nGreenScreenToWebP CLI build failed")
        return False


def build_webp_tool(project_root: Path, one_file: bool = True) -> bool:
    """Build the WebP anchor alignment tool."""
    print("\n" + "=" * 50)
    print("Building WebP Tool...")
    print("=" * 50)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=WebPTool",
        "--windowed",
    ]
    cmd.extend(get_pyinstaller_base_args())

    if one_file:
        cmd.append("--onefile")

    cmd.append(str(project_root / "scripts" / "webp_tool.py"))

    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        print(f"\nWebPTool built successfully!")
        print(f"Output: {project_root / 'dist' / 'WebPTool.exe'}")
        return True
    else:
        print(f"\nWebPTool build failed")
        return False


def build_gif_to_apng(project_root: Path, one_file: bool = True) -> bool:
    """Build the GIF to APNG converter."""
    print("\n" + "=" * 50)
    print("Building GIF to APNG converter...")
    print("=" * 50)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=gif-to-apng",
        "--console",
    ]
    cmd.extend(get_pyinstaller_base_args())

    if one_file:
        cmd.append("--onefile")

    cmd.append(str(project_root / "scripts" / "gif_to_apng.py"))

    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        print(f"\nGIF to APNG converter built successfully!")
        print(f"Output: {project_root / 'dist' / 'gif-to-apng.exe'}")
        return True
    else:
        print(f"\nGIF to APNG converter build failed")
        return False


def _get_small_excludes() -> list:
    """Get aggressive size optimization excludes."""
    return [
        "--exclude-module=email",
        "--exclude-module=html",
        "--exclude-module=http.server",
        "--exclude-module=xml.dom",
        "--exclude-module=xml.sax",
        "--exclude-module=xmlrpc",
        "--exclude-module=multiprocessing",
        "--exclude-module=concurrent",
        "--exclude-module=asyncio.tasks",
        "--exclude-module=curses",
        "--exclude-module=venv",
        "--exclude-module=ensurepip",
        "--exclude-module=zipapp",
    ]


def print_summary(project_root: Path, built_tools: list) -> None:
    """Print the final distribution summary."""
    dist_dir = project_root / "dist"

    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)

    print("\nDistribution contents:")
    print(f"  {dist_dir}/")

    for tool in built_tools:
        exe_name = tool if tool.endswith(".exe") else f"{tool}.exe"
        exe_path = dist_dir / exe_name
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"  ├── {exe_name} ({size_mb:.1f} MB)")

    if "DesktopPet" in built_tools:
        print("  ├── pets/")
        print("  │   └── default/")
        print("  └── config/")
        print("      ├── default_config.json")
        print("      └── user_config.json")

    print("\nUsage:")
    print("  1. Copy the entire 'dist' folder to distribute")
    print("  2. Users can modify pets/ and config/ directly")
    print("  3. No rebuilding needed for resource changes")


def main():
    parser = argparse.ArgumentParser(description="Build Desktop Pet executable and tools")
    parser.add_argument(
        "--dir",
        action="store_true",
        help="Build as directory instead of single file (faster startup)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build directories before building",
    )
    parser.add_argument(
        "--small",
        action="store_true",
        help="Enable aggressive size optimization (may reduce functionality)",
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        help="Build all auxiliary tools (GreenScreen GUI/CLI, WebP Tool, GIF to APNG)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build DesktopPet and all tools",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent

    if args.clean:
        clean_build_dirs(project_root)

    one_file = not args.dir
    built_tools = []

    # Build main application
    if not args.tools or args.all:
        if build_desktop_pet(project_root, one_file, args.small):
            built_tools.append("DesktopPet")

    # Build tools
    if args.tools or args.all:
        if build_green_screen_gui(project_root, one_file):
            built_tools.append("GreenScreenToWebP")
        if build_green_screen_cli(project_root, one_file):
            built_tools.append("green-screen-to-webp")
        if build_webp_tool(project_root, one_file):
            built_tools.append("WebPTool")
        if build_gif_to_apng(project_root, one_file):
            built_tools.append("gif-to-apng")

    if built_tools:
        print_summary(project_root, built_tools)
    else:
        print("\nNo builds completed successfully.")
        sys.exit(1)


if __name__ == "__main__":
    main()