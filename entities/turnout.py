"""
Turnout (Aguja / Desvío) Entity - NAS 908 Symbology.

Implements:
  - Normal / Reverse positions
  - Lock state (locked by interlocking during a route)
  - Failure simulation (Avería de aguja)
  - Visual rendering per NAS 908
"""

from __future__ import annotations
from dataclasses import dataclass
import pygame


# NAS 908 colours for turnout states
TURNOUT_COLOR_NORMAL:  tuple[int, int, int] = ( 80, 200,  80)   # Green: normal
TURNOUT_COLOR_REVERSE: tuple[int, int, int] = (200, 160,  30)   # Amber: reverse
TURNOUT_COLOR_LOCKED:  tuple[int, int, int] = ( 30, 120, 220)   # Blue: locked
TURNOUT_COLOR_FAILED:  tuple[int, int, int] = (220,  30,  30)   # Red: failed


@dataclass
class Turnout:
    """
    A set of points (aguja) in the station.

    Attributes:
        turnout_id:   Unique ID (e.g. "A1", "A3").
        pos_px:       Pixel coordinate for the point tip.
        position:     Current position: "normal" | "reverse".
        is_locked:    True when locked by the interlocking for an active route.
        is_failed:    True when an Avería has been triggered.
        normal_end_px:   Pixel coordinate of the normal (straight) leg end.
        reverse_end_px:  Pixel coordinate of the reverse (diverging) leg end.
        common_end_px:   Pixel coordinate of the common (entry) leg end.
    """
    turnout_id:      str
    pos_px:          tuple[int, int]
    position:        str = "normal"   # "normal" | "reverse"
    is_locked:       bool = False
    is_failed:       bool = False
    normal_end_px:   tuple[int, int] = (0, 0)
    reverse_end_px:  tuple[int, int] = (0, 0)
    common_end_px:   tuple[int, int] = (0, 0)

    def set_normal(self) -> None:
        """Move turnout to normal (straight) position."""
        if self.is_locked:
            raise RuntimeError(f"Turnout {self.turnout_id} is locked – cannot move.")
        if self.is_failed:
            raise RuntimeError(f"Turnout {self.turnout_id} is failed – cannot move.")
        self.position = "normal"

    def set_reverse(self) -> None:
        """Move turnout to reverse (diverging) position."""
        if self.is_locked:
            raise RuntimeError(f"Turnout {self.turnout_id} is locked – cannot move.")
        if self.is_failed:
            raise RuntimeError(f"Turnout {self.turnout_id} is failed – cannot move.")
        self.position = "reverse"

    def lock(self) -> None:
        self.is_locked = True

    def unlock(self) -> None:
        self.is_locked = False

    def trigger_failure(self) -> None:
        """Simulate turnout failure (stuck / derailment risk)."""
        self.is_failed = True

    def restore(self) -> None:
        self.is_failed  = False
        self.is_locked  = False

    def get_color(self) -> tuple[int, int, int]:
        if self.is_failed:
            return TURNOUT_COLOR_FAILED
        if self.is_locked:
            return TURNOUT_COLOR_LOCKED
        return TURNOUT_COLOR_NORMAL if self.position == "normal" else TURNOUT_COLOR_REVERSE

    def draw(self, surface: pygame.Surface) -> None:
        """
        Draw the turnout using NAS 908 symbology:
          - Common leg always drawn in base color.
          - Active leg drawn thicker.
          - Inactive leg drawn dimmer.
        """
        color = self.get_color()
        tip   = self.pos_px
        dim   = tuple(max(0, c - 80) for c in color)

        # Common leg
        pygame.draw.line(surface, color, self.common_end_px, tip, 6)

        if self.position == "normal":
            pygame.draw.line(surface, color, tip, self.normal_end_px, 6)
            pygame.draw.line(surface, dim,   tip, self.reverse_end_px, 3)
        else:
            pygame.draw.line(surface, color, tip, self.reverse_end_px, 6)
            pygame.draw.line(surface, dim,   tip, self.normal_end_px, 3)

        # ID label
        try:
            font  = pygame.font.SysFont("monospace", 9)
            label = font.render(self.turnout_id, True, (220, 220, 140))
            surface.blit(label, (tip[0] + 5, tip[1] - 12))
        except Exception:
            pass