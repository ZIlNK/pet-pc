import logging
import sys
from PyQt6.QtWidgets import QApplication

from .pet import DesktopPet
from .system_tray import SystemTrayIcon


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce noise from third-party libraries
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def main():
    # Check for verbose flag
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    # Check for hidden flag (start hidden to tray)
    start_hidden = "--hidden" in sys.argv or "-h" in sys.argv

    setup_logging(verbose)

    app = QApplication(sys.argv)
    # Set application name for proper tray behavior
    app.setApplicationName("Desktop Pet")

    pet = DesktopPet()

    # Create system tray icon
    tray_icon = None
    if pet.config_manager.tray.enabled:
        tray_icon = SystemTrayIcon(pet, pet.config_manager)
        pet.set_tray_icon(tray_icon)

        # Handle application quit request (minimize to tray instead)
        if pet.config_manager.tray.minimize_to_tray:
            app.setQuitOnLastWindowClosed(False)

        # Start hidden if requested
        if start_hidden or pet.config_manager.startup.start_hidden:
            pet.hide()
            tray_icon.set_pet_visible(False)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()