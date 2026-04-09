"""
main.py
=======
Entry point for the Railtec-App track creator.

Launches a window containing the GridWidget — the foundation layer of the
rail circuit designer.  Scroll the mouse wheel to zoom, and right-click-drag
to pan around the canvas.
"""

import sys

from PyQt5.QtWidgets import QApplication, QMainWindow

from ui.widgets.grid_component import GridWidget


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Railtec-App")
    app.setApplicationDisplayName("Railtec-App — Track Creator")

    window = QMainWindow()
    window.setWindowTitle("Railtec-App — Track Creator")
    window.resize(1200, 800)

    grid = GridWidget()
    window.setCentralWidget(grid)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
