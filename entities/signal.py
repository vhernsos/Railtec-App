"""
Signal Entity - NAS 908 Symbology & NAS 811 Placement Rules.

Implements 3-aspect colour-light signals with:
  - Aspect management (red / yellow / green / off)
  - Failure simulation (Avería)
  - ASFA beacon association (NAS 154)
  - Slip distance tracking (NAS 811)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import pygame


class SignalAspect(Enum):
    RED    = "red"
    YELLOW = "yellow"
    GREEN  = "green"
    OFF    = "off"     # Power failure / maintenance


# NAS 908 official RGB colours for signal aspects
ASPECT_COLORS: dict[str, tuple[int, int, int]] = {
    "red":    (220,  40,  40),
    "yellow": (230, 200,  30),
    "green":  ( 30, 200,  80),
    "off":    ( 50,  50,  50),
}

# NAS 811: minimum overlap (distancia de deslizamiento) in metres
DEFAULT_SLIP_DISTANCE_M: float = 50.0


@dataclass
class Signal:
    """
    Colour-light signal compliant with NAS 908 symbology.

    Attributes:
        signal_id:        Unique identifier (e.g. "E1", "S3").
        signal_type:      "entry" | "exit" | "block" | "shunting"
        position_m:       Track chainage position in metres.
        pos_px:           Pixel coordinates for rendering (x, y).
        next_segment_id:  The TrackSegment immediately beyond this signal.
        slip_distance_m:  NAS 811 overlap distance protecting the conflict point.
        aspect:           Current displayed aspect.
        is_failed:        True when an Avería (failure) has been triggered.
        asfa_beacon_pos:  Position of associated ASFA beacon (signal_pos - 5 m).
    """
    signal_id:       str
    signal_type:     str
    position_m:      float
    pos_px:          tuple[int, int]
    next_segment_id: str
    slip_distance_m: float = DEFAULT_SLIP_DISTANCE_M
    aspect:          str   = "red"
    is_failed:       bool  = False

    @property
    def asfa_beacon_pos_m(self) -> float:
        """ASFA beacon is placed 5 m before the signal face (NAG 0-8-5.0, p.10)."""
        return self.position_m - 5.0

    def set_aspect(self, aspect: str) -> None:
        """Set the signal aspect; failed signals are forced to red (fail-safe)."""
        if self.is_failed:
            self.aspect = "red"
            return
        if aspect not in ASPECT_COLORS:
            raise ValueError(f"Invalid aspect '{aspect}' for signal {self.signal_id}")
        self.aspect = aspect

    def trigger_failure(self) -> None:
        """Simulate an Avería (signal failure) – forces aspect to Red."""
        self.is_failed = True
        self.aspect    = "red"

    def restore(self) -> None:
        """Restore signal to normal operation after maintenance."""
        self.is_failed = False
        self.aspect    = "red"   # Always restore to Red first (safe state)

    def get_color(self) -> tuple[int, int, int]:
        return ASPECT_COLORS.get(self.aspect, ASPECT_COLORS["off"])

    def draw(self, surface: pygame.Surface) -> None:
        """
        Draw signal on the Pygame surface using NAS 908 symbology.
        - Mast: vertical dark grey line.
        - Head: circle with current aspect colour.
        - Failure indicator: orange X overlay.
        """
        x, y = self.pos_px
        mast_color  = (100, 100, 110)
        head_radius = 10
        mast_height = 28

        # Mast
        pygame.draw.line(surface, mast_color, (x, y), (x, y + mast_height), 2)

        # Signal head (black surround)
        pygame.draw.circle(surface, (30, 30, 30), (x, y), head_radius + 2)
        # Lit lens
        pygame.draw.circle(surface, self.get_color(), (x, y), head_radius)

        # Failure overlay (NAS 908: crossed-out signal)
        if self.is_failed:
            color_fail = (255, 140, 0)
            pygame.draw.line(surface, color_fail,
                             (x - head_radius, y - head_radius),
                             (x + head_radius, y + head_radius), 2)
            pygame.draw.line(surface, color_fail,
                             (x + head_radius, y - head_radius),
                             (x - head_radius, y + head_radius), 2)

        # Signal ID label
        try:
            font = pygame.font.SysFont("monospace", 9)
            label = font.render(self.signal_id, True, (200, 200, 200))
            surface.blit(label, (x + head_radius + 3, y - 6))
        except Exception:
            pass