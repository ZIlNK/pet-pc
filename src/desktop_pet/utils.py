from pathlib import Path


def get_assets_path() -> Path:
    return Path(__file__).parent.parent.parent / "assets"


def get_image_path(filename: str) -> Path:
    return get_assets_path() / "images" / filename


def get_animation_path(animation_name: str, filename: str = None) -> Path:
    base_path = get_assets_path() / "animations" / animation_name
    if filename:
        return base_path / filename
    return base_path


def get_gif_path(gif_name: str) -> Path:
    if gif_name in ("walk_left", "walk_right"):
        return get_assets_path() / "animations" / f"{gif_name}.gif"
    return get_animation_path(gif_name, f"{gif_name}_animation.gif")
