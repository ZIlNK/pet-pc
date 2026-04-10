#!/usr/bin/env python
"""
Standalone entry point for Desktop Pet.
This file is used by PyInstaller to build the executable.
"""
import logging
import sys


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
    """Main entry point for the application."""
    # Check for verbose flag
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    setup_logging(verbose)

    from PyQt6.QtWidgets import QApplication
    from desktop_pet.pet import DesktopPet

    app = QApplication(sys.argv)
    pet = DesktopPet()

    # Check if the pet was properly initialized (might be None if user cancelled setup)
    # The DesktopPet constructor will call QApplication.quit() if setup is cancelled
    if not pet.isVisible():
        sys.exit(0)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()