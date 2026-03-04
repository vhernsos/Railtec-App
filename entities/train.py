"""
Train Entity – Autonomous Agent with Physics & ASFA compliance.

Each train:
  - Moves autonomously along its assigned route.
  - Obeys signal aspects (Red=Stop, Yellow=Slow, Green=Proceed).
  - Interacts with ASFA beacons (NAS 154).
  - Uses the PhysicsEngine (NAG 0-8-5.0) for braking distances.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
import pygame

from core.physics_engine import PhysicsEngine, ASFASupervisor, ASFABeaconType, TrainType


class TrainState(Enum):
    RUNNING          = "running"
    BRAKING          = "braking"
    STOPPED          = "stopped"
    EMERGENCY_BRAKE  = "emergency_brake"
    WAITING          = "waiting"


# Train visual colours
TRAIN_COLORS = {
    0: (  60, 140, 220),   # Blue
    1: ( 220,  80,  60),   # Red-orange
    2: (  60, 200, 120),   # Green
    3: ( 200, 160,  40),   # Amber
    4: ( 160,  60, 220),   # Purple
}

TRAIN_WIDTH_PX  = 30
TRAIN_HEIGHT_PX = 14


@dataclass
class Train:
    """
    Autonomous train agent.

    Attributes:
        train_id:        Unique identifier.
        name:            Display name (e.g. "AVE 00102").
        pos_m:           Current position in metres on the track.
        speed_kmh:       Current speed in km/h.
        max_speed_kmh:   Maximum allowed line speed.
        route_segments:  Ordered list of segment IDs forming the train's path.
        route_signals:   Ordered list of (position_m, signal_id) tuples.
        state:           Current operational state.
        train_type:      λ classification for NAG 0-8-5.0 braking tables.
        color_idx:       Index into TRAIN_COLORS.
        pos_px:          Current pixel position for rendering (computed by renderer).
        length_m:        Physical length of the train in metres.
    """
    train_id:       str
    name:           str
    pos_m:          float
    speed_kmh:      float
    max_speed_kmh:  float
    route_segments: list[str]
    route_signals:  list[tuple[float, str]]   # [(pos_m, signal_id), ...]
    state:          TrainState = TrainState.STOPPED
    train_type:     TrainType  = TrainType.LAMBDA_100
    color_idx:      int        = 0
    pos_px:         tuple[int, int] = field(default=(0, 0))
    length_m:       float = 200.0   # typical passenger consist

    # Runtime internals (not constructor args)
    _physics:       PhysicsEngine  = field(init=False)
    _asfa:          ASFASupervisor = field(init=False)
    _current_seg_idx: int          = field(init=False, default=0)
    _target_speed:    float        = field(init=False, default=0.0)
    _emergency:       bool         = field(init=False, default=False)
    _gradient:        float        = field(init=False, default=0.0)
    _log:             list[str]    = field(init=False, default_factory=list)

    def __post_init__(self):
        self._physics       = PhysicsEngine(self.train_type)
        self._asfa          = ASFASupervisor()
        self._target_speed  = self.max_speed_kmh

    # ── Speed & Movement ────────────────────────────────────────────────────

    def update(self, dt: float, signals: dict[str, "Signal"],   # noqa: F821
               segments: dict[str, "TrackSegment"]) -> None:    # noqa: F821
        """
        Advance the train's simulation by dt seconds.

        Args:
            dt:       Time step in seconds.
            signals:  Dict of all Signal objects keyed by signal_id.
            segments: Dict of all TrackSegment objects keyed by segment_id.
        """
        if self.state == TrainState.STOPPED:
            return

        # Update gradient from current segment
        self._update_gradient(segments)

        # Evaluate nearest upcoming signal
        self._evaluate_signals(signals)

        # Apply traction / braking
        self._apply_dynamics(dt)

        # Advance position
        dist_m = (self.speed_kmh / 3.6) * dt
        self.pos_m += dist_m

        # Update CDV occupancy
        self._update_cdv(segments)

        # Check ASFA beacons
        self._check_asfa_beacons(signals, dist_m)

    def _update_gradient(self, segments: dict) -> None:
        seg = self._current_segment(segments)
        if seg:
            self._gradient = seg.gradient

    def _current_segment(self, segments: dict):
        if self._current_seg_idx < len(self.route_segments):
            seg_id = self.route_segments[self._current_seg_idx]
            return segments.get(seg_id)
        return None

    def _evaluate_signals(self, signals: dict) -> None:
        """
        Find the next signal on the route and adjust target speed accordingly.
        Implements NAG 0-8-5.0 braking point calculation.
        """
        if self._emergency:
            self._target_speed = 0.0
            self.state         = TrainState.EMERGENCY_BRAKE
            return

        next_sig_data = self._next_signal_data()
        if next_sig_data is None:
            self._target_speed = self.max_speed_kmh
            self.state         = TrainState.RUNNING
            return

        sig_pos_m, sig_id = next_sig_data
        sig = signals.get(sig_id)
        if sig is None:
            return

        dist_to_sig = sig_pos_m - self.pos_m

        if sig.aspect == "green":
            self._target_speed = self.max_speed_kmh
            self.state         = TrainState.RUNNING

        elif sig.aspect == "yellow":
            # Reduce speed – must be able to stop at next red
            braking = self._physics.compute_braking(
                speed_kmh=self.speed_kmh,
                gradient=self._gradient,
                signal_pos_m=sig_pos_m,
            )
            restricted_speed = min(self.max_speed_kmh * 0.5, 80.0)
            self._target_speed = restricted_speed
            if dist_to_sig <= braking.distance_m:
                self.state = TrainState.BRAKING
            else:
                self.state = TrainState.RUNNING

        elif sig.aspect == "red":
            braking = self._physics.compute_braking(
                speed_kmh=self.speed_kmh,
                gradient=self._gradient,
                signal_pos_m=sig_pos_m,
            )
            self._target_speed = 0.0
            if dist_to_sig <= braking.distance_m + 50:   # +50 m safety margin
                self.state = TrainState.BRAKING
            else:
                self.state = TrainState.RUNNING

    def _apply_dynamics(self, dt: float) -> None:
        """Apply acceleration or braking to converge toward target speed."""
        ACCEL_MS2  = 0.8    # m/s² typical passenger train acceleration
        if self._emergency:
            # Emergency braking: 1.2 m/s² (service), 2.5 m/s² (emergency)
            decel = 2.5
            self.speed_kmh = max(0.0, self.speed_kmh - decel * 3.6 * dt)
            if self.speed_kmh == 0.0:
                self.state     = TrainState.STOPPED
                self._emergency = False
            return

        if self.state == TrainState.BRAKING:
            decel = self._physics.current_deceleration(self.speed_kmh, self._gradient)
            self.speed_kmh = max(self._target_speed,
                                 self.speed_kmh - decel * 3.6 * dt)
        elif self.state == TrainState.RUNNING:
            if self.speed_kmh < self._target_speed:
                self.speed_kmh = min(self._target_speed,
                                     self.speed_kmh + ACCEL_MS2 * 3.6 * dt)
            elif self.speed_kmh > self._target_speed:
                self.speed_kmh = max(self._target_speed,
                                     self.speed_kmh - ACCEL_MS2 * 3.6 * dt)

        if self.speed_kmh <= 0.0 and self._target_speed == 0.0:
            self.speed_kmh = 0.0
            self.state     = TrainState.STOPPED

    def _update_cdv(self, segments: dict) -> None:
        """Update CDV occupation: mark current segment as occupied."""
        for i, seg_id in enumerate(self.route_segments):
            seg = segments.get(seg_id)
            if seg is None:
                continue
            if seg.start_m <= self.pos_m <= seg.end_m:
                seg.occupy(self.train_id)
                self._current_seg_idx = i
            elif seg.is_occupied and seg._occupying_train == self.train_id:
                # Train has left this segment
                if self.pos_m > seg.end_m:
                    seg.clear()

    def _check_asfa_beacons(self, signals: dict, dist_moved: float) -> None:
        """Check if the train just passed over an ASFA beacon."""
        for sig_pos_m, sig_id in self.route_signals:
            beacon_pos = sig_pos_m - 5.0   # 5 m before signal face
            # Did we just cross this beacon?
            if self.pos_m - dist_moved <= beacon_pos <= self.pos_m:
                sig = signals.get(sig_id)
                if sig is None:
                    continue
                event = self._asfa.process_beacon(
                    beacon_type=ASFABeaconType.SIGNAL,
                    signal_aspect=sig.aspect,
                    train_speed_kmh=self.speed_kmh,
                    line_speed_kmh=self.max_speed_kmh,
                )
                if event.requires_emergency:
                    self._trigger_emergency(f"ASFA EB at {sig_id} ({sig.aspect})")
                elif event.requires_brake:
                    self.state = TrainState.BRAKING
                    self._log.append(f"ASFA service brake at {sig_id}")

    def _next_signal_data(self) -> tuple[float, str] | None:
        """Return the (pos_m, signal_id) of the next signal ahead."""
        for sig_pos_m, sig_id in self.route_signals:
            if sig_pos_m > self.pos_m:
                return sig_pos_m, sig_id
        return None

    def _trigger_emergency(self, reason: str) -> None:
        self._emergency = True
        self.state      = TrainState.EMERGENCY_BRAKE
        self._log.append(f"[EB] {reason}")

    def trigger_manual_emergency(self) -> None:
        """Manual override: operator triggers emergency stop."""
        self._trigger_emergency("Manual operator override")

    def start(self) -> None:
        if self.state == TrainState.STOPPED:
            self.state = TrainState.RUNNING

    def get_telemetry(self) -> dict:
        """Return telemetry dict for the dashboard."""
        return {
            "id":          self.train_id,
            "name":        self.name,
            "speed_kmh":   round(self.speed_kmh, 1),
            "pos_m":       round(self.pos_m, 1),
            "state":       self.state.value,
            "segment":     self.route_segments[min(self._current_seg_idx,
                                                   len(self.route_segments) - 1)],
        }

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the train as a rectangle at pos_px using NAS 908-style colouring."""
        color = TRAIN_COLORS.get(self.color_idx % len(TRAIN_COLORS), (100, 100, 200))

        if self.state == TrainState.EMERGENCY_BRAKE:
            color = (255, 40, 40)   # Flash red during emergency

        x, y = self.pos_px
        rect = pygame.Rect(x - TRAIN_WIDTH_PX // 2,
                           y - TRAIN_HEIGHT_PX // 2,
                           TRAIN_WIDTH_PX,
                           TRAIN_HEIGHT_PX)
        pygame.draw.rect(surface, color, rect, border_radius=3)
        pygame.draw.rect(surface, (200, 200, 200), rect, 1, border_radius=3)

        # Speed label
        try:
            font  = pygame.font.SysFont("monospace", 8)
            label = font.render(f"{self.speed_kmh:.0f}", True, (255, 255, 255))
            surface.blit(label, (x - 8, y - 5))
        except Exception:
            pass