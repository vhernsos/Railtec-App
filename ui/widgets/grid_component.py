"""
grid_component.py
=================
Reusable grid canvas widget for the Railtec-App track creator.

Provides a precision drawing surface for designing train track layouts:
  - Infinite white-background grid with black lines (no clipping)
  - Mouse-wheel zoom (scroll up = finer grid; scroll down = coarser grid)
  - Right-click drag panning
  - Real-time "X m/square" distance meter overlay
  - Architecture ready for drawing layers (tracks, signals, intersections)

Usage::

    from ui.widgets.grid_component import GridWidget

    widget = GridWidget()
    widget.show()
"""

import math

from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QColor, QFont, QMouseEvent, QPaintEvent, QPainter, QPen, QWheelEvent
from PyQt5.QtWidgets import QWidget


class GridWidget(QWidget):
    """
    Interactive grid canvas widget for designing rail track circuits.

    The grid models a 2-D world measured in metres.  The *scale* attribute
    controls how many screen pixels correspond to one metre; adjusting it
    (via the mouse wheel) effectively zooms the canvas while keeping the
    world coordinate system stable.

    Coordinate conventions
    ----------------------
    - World space : metres, origin (0, 0) at the point that was in the
      viewport centre when the widget was first shown.
    - Screen space : pixels, (0, 0) at the top-left corner of the widget.
    - ``_offset``  : world coordinates of the screen origin (top-left corner).

    Drawing layers
    --------------
    Subclasses (or external code) can hook into the paint cycle by overriding
    :meth:`draw_content`.  It is called after the grid is painted but before
    the HUD overlay, so custom track / signal graphics appear on top of the
    grid and below the meter label.
    """

    # ------------------------------------------------------------------ #
    #  Class-level constants                                               #
    # ------------------------------------------------------------------ #

    # Preferred grid-line spacing in world units (metres).
    # The widget picks the entry that keeps cell pixels closest to
    # TARGET_CELL_PX.
    GRID_INTERVALS: list[int] = [
        10, 20, 50, 100, 200, 500,
        1_000, 2_000, 5_000, 10_000,
    ]

    #: Minimum metres per grid cell (= maximum zoom precision).
    MIN_METRES_PER_CELL: int = 10

    #: Pixel size we aim for when choosing which GRID_INTERVALS entry to use.
    TARGET_CELL_PX: int = 60

    #: Multiplier applied to *scale* on each wheel notch.
    ZOOM_STEP: float = 1.15

    # Grid appearance
    _BACKGROUND_COLOUR = QColor(255, 255, 255)
    _GRID_COLOUR = QColor(0, 0, 0)
    _GRID_PEN_WIDTH: float = 0.8

    # HUD appearance
    _HUD_BG_COLOUR = QColor(0, 0, 0, 185)
    _HUD_TEXT_COLOUR = QColor(255, 255, 255)
    _HUD_FONT_SIZE: int = 11
    _HUD_MARGIN: int = 10
    _HUD_PADDING: int = 8

    # ------------------------------------------------------------------ #
    #  Construction                                                        #
    # ------------------------------------------------------------------ #

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # --- view state ---------------------------------------------------
        # scale: screen pixels per world metre
        # Default: TARGET_CELL_PX pixels / 100 m  →  60 px / 100 m = 0.6 px/m
        self._scale: float = self.TARGET_CELL_PX / 100.0

        # World coordinates of the screen origin (top-left corner of the widget)
        self._offset: QPointF = QPointF(0.0, 0.0)

        # --- pan state ----------------------------------------------------
        self._panning: bool = False
        self._pan_start_screen: QPoint = QPoint()
        self._pan_start_offset: QPointF = QPointF()

        # --- widget setup -------------------------------------------------
        self.setMinimumSize(600, 400)
        self.setFocusPolicy(Qt.StrongFocus)
        # Prevent right-click from opening a context menu
        self.setContextMenuPolicy(Qt.PreventContextMenu)

    # ------------------------------------------------------------------ #
    #  Public helpers                                                      #
    # ------------------------------------------------------------------ #

    @property
    def scale(self) -> float:
        """Current scale factor: screen pixels per world metre."""
        return self._scale

    @property
    def offset(self) -> QPointF:
        """World coordinates of the screen origin (top-left corner)."""
        return QPointF(self._offset)

    def world_to_screen(self, world: QPointF) -> QPointF:
        """Convert a world-space point (metres) to screen-space (pixels)."""
        return QPointF(
            (world.x() - self._offset.x()) * self._scale,
            (world.y() - self._offset.y()) * self._scale,
        )

    def screen_to_world(self, screen: QPointF) -> QPointF:
        """Convert a screen-space point (pixels) to world-space (metres)."""
        return QPointF(
            screen.x() / self._scale + self._offset.x(),
            screen.y() / self._scale + self._offset.y(),
        )

    # ------------------------------------------------------------------ #
    #  Drawing hook for subclasses / external layers                      #
    # ------------------------------------------------------------------ #

    def draw_content(self, painter: QPainter) -> None:
        """Override this method to draw tracks, signals, etc. on top of the
        grid.  The painter's coordinate system is in *screen* pixels.
        Use :meth:`world_to_screen` to convert world coordinates."""
        pass

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _grid_interval(self) -> int:
        """Return the best grid interval (metres) for the current scale.

        Picks the smallest value from :attr:`GRID_INTERVALS` that produces a
        cell at least :attr:`TARGET_CELL_PX` pixels wide, so cells are always
        comfortably readable.  The :attr:`MIN_METRES_PER_CELL` lower bound
        enforces the maximum-zoom-precision requirement.
        """
        if self._scale <= 0:
            return self.GRID_INTERVALS[-1]

        # Ideal interval: the one that gives exactly TARGET_CELL_PX pixels.
        ideal_metres = self.TARGET_CELL_PX / self._scale

        # Never go below the minimum precision.
        ideal_metres = max(ideal_metres, float(self.MIN_METRES_PER_CELL))

        # Choose the smallest GRID_INTERVALS entry that is >= ideal_metres
        # so that cells are never smaller than TARGET_CELL_PX.
        for interval in self.GRID_INTERVALS:
            if interval >= ideal_metres:
                return interval

        return self.GRID_INTERVALS[-1]

    def _max_scale(self) -> float:
        """Maximum allowed scale (enforces MIN_METRES_PER_CELL precision)."""
        return self.TARGET_CELL_PX / self.MIN_METRES_PER_CELL

    def _min_scale(self) -> float:
        """Minimum allowed scale (10 000 m per cell = effectively unlimited)."""
        return self.TARGET_CELL_PX / 10_000.0

    # ------------------------------------------------------------------ #
    #  Paint                                                               #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w, h = self.width(), self.height()

        # 1. Background
        painter.fillRect(0, 0, w, h, self._BACKGROUND_COLOUR)

        # 2. Grid lines
        self._paint_grid(painter, w, h)

        # 3. Custom content layer (override draw_content to use)
        self.draw_content(painter)

        # 4. HUD overlay (always on top)
        self._paint_hud(painter, w, h)

        painter.end()

    def _paint_grid(self, painter: QPainter, w: int, h: int) -> None:
        interval = self._grid_interval()
        cell_px = interval * self._scale

        if cell_px <= 0:
            return

        pen = QPen(self._GRID_COLOUR, self._GRID_PEN_WIDTH)
        painter.setPen(pen)

        # World coordinates of the four viewport edges
        world_left = self._offset.x()
        world_top = self._offset.y()
        world_right = world_left + w / self._scale
        world_bottom = world_top + h / self._scale

        # First grid line at or before the left / top edge
        first_x = math.floor(world_left / interval) * interval
        first_y = math.floor(world_top / interval) * interval

        # --- Vertical lines -----------------------------------------------
        x = first_x
        while x <= world_right + interval:
            sx = round((x - world_left) * self._scale)
            painter.drawLine(sx, 0, sx, h)
            x += interval

        # --- Horizontal lines ---------------------------------------------
        y = first_y
        while y <= world_bottom + interval:
            sy = round((y - world_top) * self._scale)
            painter.drawLine(0, sy, w, sy)
            y += interval

    def _paint_hud(self, painter: QPainter, w: int, h: int) -> None:
        """Draw the distance-meter label in the top-left corner."""
        interval = self._grid_interval()

        if interval >= 1_000:
            label = f"{interval // 1_000} km/square"
        else:
            label = f"{interval} m/square"

        font = QFont("Arial", self._HUD_FONT_SIZE)
        font.setBold(True)
        painter.setFont(font)

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(label)
        text_h = fm.height()
        ascent = fm.ascent()

        p = self._HUD_PADDING
        m = self._HUD_MARGIN
        box_w = text_w + p * 2
        box_h = text_h + p

        # Background rounded rectangle
        painter.setBrush(self._HUD_BG_COLOUR)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(m, m, box_w, box_h, 4, 4)

        # Text
        painter.setPen(self._HUD_TEXT_COLOUR)
        painter.drawText(m + p, m + p // 2 + ascent, label)

    # ------------------------------------------------------------------ #
    #  Mouse events                                                        #
    # ------------------------------------------------------------------ #

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom in/out around the cursor position.

        Scroll up  → finer grid (more squares, fewer metres each).
        Scroll down → coarser grid (fewer squares, more metres each).
        """
        delta = event.angleDelta().y()
        if delta == 0:
            return

        cursor = event.pos()

        # World point currently under the cursor — keep it fixed after zoom.
        world_under_cursor = self.screen_to_world(QPointF(cursor))

        new_scale = (
            self._scale * self.ZOOM_STEP
            if delta > 0
            else self._scale / self.ZOOM_STEP
        )
        new_scale = max(self._min_scale(), min(self._max_scale(), new_scale))

        if new_scale == self._scale:
            return

        self._scale = new_scale

        # Recompute offset so the world point under the cursor stays put.
        self._offset = QPointF(
            world_under_cursor.x() - cursor.x() / self._scale,
            world_under_cursor.y() - cursor.y() / self._scale,
        )

        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton:
            self._panning = True
            self._pan_start_screen = event.pos()
            self._pan_start_offset = QPointF(self._offset)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            delta = event.pos() - self._pan_start_screen
            self._offset = QPointF(
                self._pan_start_offset.x() - delta.x() / self._scale,
                self._pan_start_offset.y() - delta.y() / self._scale,
            )
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
