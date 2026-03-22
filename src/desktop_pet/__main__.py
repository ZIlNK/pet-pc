import sys
from PyQt6.QtWidgets import QApplication

from .pet import DesktopPet


def main():
    app = QApplication(sys.argv)
    pet = DesktopPet()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
