"""Utility functions for path resolution, supporting both development and frozen (PyInstaller) environments.

All resources (pets, config) are stored externally to the EXE for easy user modification.
"""
import sys
from pathlib import Path


def get_executable_dir() -> Path:
    """Get the directory containing the executable or script.

    - In frozen mode (PyInstaller): returns the EXE's parent directory
    - In development: returns the project root directory
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - use EXE directory
        return Path(sys.executable).parent
    else:
        # Running in development - use project root
        return Path(__file__).parent.parent.parent


def get_base_path() -> Path:
    """Get the base path for bundled resources.

    This is kept for compatibility but now points to the executable directory.
    All resources are external to allow user modifications.
    """
    return get_executable_dir()


def get_assets_path() -> Path:
    """Get the path to the assets directory (legacy, may not exist in packaged app)."""
    return get_base_path() / "assets"


def get_config_path() -> Path:
    """Get the path to the config directory.

    All config files are stored in {EXE_DIR}/config/ for easy user access.
    """
    return get_executable_dir() / "config"


def get_user_config_path() -> Path:
    """Get the path to user-writable config directory.

    This is the same as get_config_path() since all config is now external.
    """
    return get_config_path()


def get_pets_path() -> Path:
    """Get the path to the pets directory.

    All pet packages are stored in {EXE_DIR}/pets/ for easy user access.
    """
    return get_executable_dir() / "pets"


def get_image_path(filename: str) -> Path:
    """Get the path to an image file in assets/images."""
    return get_assets_path() / "images" / filename


def get_animation_path(animation_name: str, filename: str = None) -> Path:
    """Get the path to an animation directory or specific file."""
    base_path = get_assets_path() / "animations" / animation_name
    if filename:
        return base_path / filename
    return base_path


def get_gif_path(gif_name: str) -> Path:
    """Get the path to a GIF file."""
    if gif_name in ("walk_left", "walk_right"):
        return get_assets_path() / "animations" / f"{gif_name}.gif"
    return get_animation_path(gif_name, f"{gif_name}_animation.gif")