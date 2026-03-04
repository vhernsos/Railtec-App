"""
Renderer - NAS 908 Station Schematic Rendering.

Draws the full station layout:
  - Track segments (CDV blocks) with occupation colours
  - Signals with correct aspect colours
  - Turnouts (switches) with position indicators
  - Trains
  - Station background / grid
"""

from __future__ import annotations
import pygame
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.train import Train
    from entities.signal import Signal
    from entities.track_segment import TrackSegment
    from entities.turnout import Turnout

# ── Palette (dark professional theme) ───────────────────────────────────────
COLOR_BG         = ( 18,  22,  30)   # Near-black background
COLOR_GRID       = ( 35,  42,  55)   # Subtle grid lines
COLOR_PLATFORM   = ( 55,  65,  80)   # Platform areas
COLOR_TEXT_TITLE = (200, 210, 230)
COLOR_TEXT_DIM   = (120, 130, 150)

GRID_SPACING_PX  = 40


class Renderer:
    """
    Handles all Pygame drawing for the station simulation.

    Usage:
        renderer = Renderer(screen)
        renderer.render(trains, signals, segments, turnouts)
    """

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.width, self.height = screen.get_size()
        pygame.font.init()
        self._font_sm  = pygame.font.SysFont("monospace", 10)
        self._font_md  = pygame.font.SysFont("monospace", 13)
        self._font_lg  = pygame.font.SysFont("monospace", 18, bold=True)

    def render(self,
               trains:   list["Train"],
               signals:  dict[str, "Signal"],
               segments: dict[str, "TrackSegment"],
               turnouts: dict[str, "Turnout"],
               tick:     int = 0) -> None:
        """Main render call – draws a full frame."""
        self._draw_background()
        self._draw_grid()
        self._draw_platform_areas()
        self._draw_segments(segments)
        self._draw_turnouts(turnouts)
        self._draw_signals(signals)
        self._draw_trains(trains)
        self._draw_title(tick)

    # ── Background & Grid ────────────────────────────────────────────────────

    def _draw_background(self) -> None:
        self.screen.fill(COLOR_BG)

    def _draw_grid(self) -> None:
        for x in range(0, self.width, GRID_SPACING_PX):
            pygame.draw.line(self.screen, COLOR_GRID, (x, 0), (x, self.height), 1)
        for y in range(0, self.height, GRID_SPACING_PX):
            pygame.draw.line(self.screen, COLOR_GRID, (0, y), (self.width, y), 1)

    def _draw_platform_areas(self) -> None:
        """Draw platform rectangles (grey filled areas beneath track lines)."""
        platforms = [
            pygame.Rect(100, 200, 700, 20),
            pygame.Rect(100, 280, 700, 20),
            pygame.Rect(100, 360, 700, 20),
        ]
        for p in platforms:
            pygame.draw.rect(self.screen, COLOR_PLATFORM, p, border_radius=2)
            label = self._font_sm.render("ANDÉN", True, COLOR_TEXT_DIM)
            self.screen.blit(label, (p.x + 5, p.y + 4))

    # ── Track Segments ────────────────────────────────────────────────────────

    def _draw_segments(self, segments: dict[str, "TrackSegment"]) -> None:
        for seg in segments.values():
            seg.draw(self.screen)

    # ── Turnouts ──────────────────────────────────────────────────────────────

    def _draw_turnouts(self, turnouts: dict[str, "Turnout"]) -> None:
        for t in turnouts.values():
            t.draw(self.screen)

    # ── Signals ───────────────────────────────────────────────────────────────

    def _draw_signals(self, signals: dict[str, "Signal"]) -> None:
        for sig in signals.values():
            sig.draw(self.screen)
        # ASFA beacon indicators (small diamonds)
        for sig in signals.values():
            self._draw_asfa_beacon(sig)

    def _draw_asfa_beacon(self, sig: "Signal") -> None:
        """Draw ASFA beacon as a small yellow diamond 5 m before the signal."""
        x, y = sig.pos_px
        # Offset beacon slightly to the left of the signal in pixel space
        bx = x - 18
        by = y + 5
        size = 5
        color = (230, 210, 50)
        points = [(bx, by - size), (bx + size, by),
                  (bx, by + size), (bx - size, by)]
        pygame.draw.polygon(self.screen, color, points)

    # ── Trains ────────────────────────────────────────────────────────────────

    def _draw_trains(self, trains: list["Train"]) -> None:
        for train in trains:
            train.draw(self.screen)

    # ── Title / HUD ───────────────────────────────────────────────────────────

    def _draw_title(self, tick: int) -> None:
        title  = self._font_lg.render("ADIF SIMULATION SYSTEM  – Estación Modelo",
                                      True, COLOR_TEXT_TITLE)
        sub    = self._font_sm.render(
            f"NAS 811 · NAS 908 · NAS 154 · NAG 0-8-5.0     Tick: {tick}",
            True, COLOR_TEXT_DIM,
        )
        self.screen.blit(title, (10, 8))
        self.screen.blit(sub,   (10, 30))

    def map_pos(self, pos_m: float, track_y: int,
                start_m: float, end_m: float,
                x_left: int = 100, x_right: int = 800) -> tuple[int, int]:
        """
        Convert a track metre position to pixel coordinates.

        Args:
            pos_m:   Train's metre position.
            track_y: Pixel Y coordinate of the track line.
            start_m: Start metre of the visible section.
            end_m:   End metre of the visible section.
            x_left:  Left pixel boundary.
            x_right: Right pixel boundary.
        """
        if end_m == start_m:
            return x_left, track_y
        frac = (pos_m - start_m) / (end_m - start_m)
        px = int(x_left + frac * (x_right - x_left))
        return px, track_y