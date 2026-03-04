"""
TrackSegment (CDV – Circuito de Vía) Entity.

Represents a track circuit block. Each segment:
  - Has a unique ID and geometric start/end coordinates for rendering.
  - Tracks occupancy (is_occupied) used by the interlocking.
  - Stores gradient for physics calculations.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import pygame


# NAS 908 colours for track circuit states
CDV_COLOR_FREE:     tuple[int, int, int] = ( 80, 140, 200)   # Blue-grey: free
CDV_COLOR_OCCUPIED: tuple[int, int, int] = (220,  80,  30)   # Orange-red: occupied
CDV_COLOR_UNKNOWN:  tuple[int, int, int] = (180, 180,  30)   # Yellow: unknown / fault
TRACK_WIDTH_PX = 6


@dataclass
class TrackSegment:
    """
    A block section (CDV) of track.

    Attributes:
        segment_id:      Unique ID (e.g. "CDV-1A").
        start_m:         Start chainage (metres).
        end_m:           End chainage (metres).
        gradient:        Gradient in ‰ (per mille); positive = uphill.
        is_occupied:     True when a train's axles occupy this block.
        start_px:        Start pixel coordinate (x, y).
        end_px:          End pixel coordinate (x, y).
        next_segment_id: ID of the following segment (or None at end of line).
        is_faulty:       CDV failure – interlocking treats this as occupied.
        track_type:      "conventional" | "high_speed" | "yard"
    """
    segment_id:      str
    start_m:         float
    end_m:           float
    gradient:        float
    start_px:        tuple[int, int]
    end_px:          tuple[int, int]
    next_segment_id: str | None = None
    is_occupied:     bool       = False
    is_faulty:       bool       = False
    track_type:      str        = "conventional"

    @property
    def length_m(self) -> float:
        return abs(self.end_m - self.start_m)

    def occupy(self, train_id: str) -> None:
        """Mark this CDV as occupied by a train."""
        self.is_occupied = True
        self._occupying_train = train_id

    def clear(self) -> None:
        """Clear this CDV."""
        self.is_occupied = False
        self._occupying_train = None

    def trigger_fault(self) -> None:
        """Simulate CDV fault → interlocking treats as occupied (fail-safe)."""
        self.is_faulty   = True
        self.is_occupied = True

    def restore_fault(self) -> None:
        self.is_faulty   = False
        self.is_occupied = False

    def get_color(self) -> tuple[int, int, int]:
        if self.is_faulty:
            return CDV_COLOR_UNKNOWN
        return CDV_COLOR_OCCUPIED if self.is_occupied else CDV_COLOR_FREE

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the track segment with NAS 908-style CDV colouring."""
        pygame.draw.line(surface, self.get_color(),
                         self.start_px, self.end_px, TRACK_WIDTH_PX)

        # Segment ID label at midpoint
        try:
            mx = (self.start_px[0] + self.end_px[0]) // 2
            my = (self.start_px[1] + self.end_px[1]) // 2
            font  = pygame.font.SysFont("monospace", 8)
            label = font.render(self.segment_id, True, (160, 160, 160))
            surface.blit(label, (mx - 15, my + 6))
        except Exception:
            pass