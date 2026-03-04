"""
Interlocking Logic - NAS 811 Compliance
Manages route locking, CDV (track circuit) occupation, turnout alignment,
and signal authorization for conflict-free train movements.

References:
  - NAS 811: CMS Installation Design, signal placement & overlap distances.
  - "Distancia de deslizamiento" (slip distance) protects conflict points.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.signal import Signal
    from entities.track_segment import TrackSegment
    from entities.turnout import Turnout


class RouteState(Enum):
    IDLE      = "idle"
    REQUESTED = "requested"
    LOCKED    = "locked"
    RELEASED  = "released"


@dataclass
class Route:
    """
    Represents an interlocked route through the station.

    Attributes:
        route_id:      Unique identifier (e.g. "E1-V3")
        entry_signal:  The entry signal protecting this route.
        exit_signal:   The exit signal at the far end.
        segments:      Ordered list of TrackSegment IDs that form the route.
        turnouts:      Dict mapping Turnout ID → required position ("normal"/"reverse").
        state:         Current locking state.
        slip_distance: NAS 811 "distancia de deslizamiento" in metres.
    """
    route_id:       str
    entry_signal:   str
    exit_signal:    str
    segments:       list[str]
    turnouts:       dict[str, str]   # {turnout_id: "normal" | "reverse"}
    state:          RouteState = RouteState.IDLE
    slip_distance:  float = 50.0     # NAS 811 default overlap

    # Internal: which train currently holds this route
    train_id:       str | None = None


class InterlockingError(Exception):
    """Raised when an interlocking violation is detected."""


class InterlockingSystem:
    """
    Central interlocking controller.

    Responsibilities:
      1. Verify all CDVs (track circuits) on a route are free.
      2. Verify all turnouts are in the required position.
      3. Lock the route and authorize the entry signal to show Green.
      4. Detect and prevent conflicting route requests.
      5. Release the route after the train has cleared.
    """

    def __init__(self):
        self._routes:   dict[str, Route]        = {}
        self._signals:  dict[str, "Signal"]     = {}
        self._segments: dict[str, "TrackSegment"] = {}
        self._turnouts: dict[str, "Turnout"]    = {}

        # Active locks: route_id → train_id
        self._locked_routes: dict[str, str] = {}

    # ── Registration ─────────────────────────────────────────────────────────

    def register_route(self, route: Route) -> None:
        self._routes[route.route_id] = route

    def register_signal(self, signal: "Signal") -> None:
        self._signals[signal.signal_id] = signal

    def register_segment(self, segment: "TrackSegment") -> None:
        self._segments[segment.segment_id] = segment

    def register_turnout(self, turnout: "Turnout") -> None:
        self._turnouts[turnout.turnout_id] = turnout

    # ── Route Request Logic ──────────────────────────────────────────────────

    def request_route(self, route_id: str, train_id: str) -> bool:
        """
        Request a route for a specific train.

        Returns True if the route was successfully locked.
        Raises InterlockingError if safety conditions are not met.
        """
        if route_id not in self._routes:
            raise InterlockingError(f"Unknown route: {route_id}")

        route = self._routes[route_id]

        # 1. Already locked by someone else?
        if route.state == RouteState.LOCKED and route.train_id != train_id:
            raise InterlockingError(
                f"Route {route_id} is already locked by train {route.train_id}"
            )

        # 2. Check for conflicting routes (overlapping segments)
        self._check_conflicts(route)

        # 3. All CDVs on the route must be free
        self._check_cdv_clear(route)

        # 4. All turnouts must be in the required position
        self._check_turnout_positions(route)

        # 5. All conditions met → lock the route
        route.state   = RouteState.LOCKED
        route.train_id = train_id
        self._locked_routes[route_id] = train_id

        # 6. Authorize entry signal → Green
        entry_sig = self._signals.get(route.entry_signal)
        if entry_sig:
            entry_sig.set_aspect("green")

        return True

    def release_route(self, route_id: str, train_id: str) -> None:
        """
        Release a route once the train has cleared it (section by section).
        The entry signal is immediately set to Red.
        """
        if route_id not in self._routes:
            return

        route = self._routes[route_id]
        if route.train_id != train_id:
            return   # Not our route to release

        route.state   = RouteState.RELEASED
        route.train_id = None
        self._locked_routes.pop(route_id, None)

        # Set entry signal back to Red
        entry_sig = self._signals.get(route.entry_signal)
        if entry_sig:
            entry_sig.set_aspect("red")

        route.state = RouteState.IDLE

    def update_signal_aspects(self) -> None:
        """
        Recalculate all signal aspects based on block occupancy.
        Called every simulation tick.

        Rules (simplified 3-aspect system):
          - If the block ahead is occupied → Red
          - If the block 2 ahead is occupied → Yellow
          - Otherwise → Green
        """
        for sig_id, signal in self._signals.items():
            if signal.is_failed:
                signal.set_aspect("red")   # Fail-safe: failed signals → Red
                continue

            next_seg = self._get_next_segment(signal)
            if next_seg is None:
                continue

            if next_seg.is_occupied:
                signal.set_aspect("red")
            else:
                # Look one block further for Yellow condition
                further_seg = self._get_segment_after(next_seg)
                if further_seg and further_seg.is_occupied:
                    signal.set_aspect("yellow")
                else:
                    # Check route lock: don't show green without a locked route
                    route_locked = any(
                        r.entry_signal == sig_id and r.state == RouteState.LOCKED
                        for r in self._routes.values()
                    )
                    if route_locked:
                        signal.set_aspect("green")
                    else:
                        signal.set_aspect("red")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _check_conflicts(self, route: Route) -> None:
        """Ensure no locked route shares segments with the requested route."""
        for locked_id, _ in self._locked_routes.items():
            locked_route = self._routes[locked_id]
            shared = set(route.segments) & set(locked_route.segments)
            if shared:
                raise InterlockingError(
                    f"Route {route.route_id} conflicts with locked route "
                    f"{locked_id} on segments: {shared}"
                )

    def _check_cdv_clear(self, route: Route) -> None:
        """Verify all CDV (track circuits) on the route are unoccupied."""
        for seg_id in route.segments:
            seg = self._segments.get(seg_id)
            if seg is None:
                raise InterlockingError(f"Unknown segment: {seg_id}")
            if seg.is_occupied:
                raise InterlockingError(
                    f"CDV occupied on segment {seg_id} – cannot lock route "
                    f"{route.route_id}"
                )

    def _check_turnout_positions(self, route: Route) -> None:
        """Verify all required turnouts are correctly set."""
        for turnout_id, required_pos in route.turnouts.items():
            t = self._turnouts.get(turnout_id)
            if t is None:
                raise InterlockingError(f"Unknown turnout: {turnout_id}")
            if t.position != required_pos:
                raise InterlockingError(
                    f"Turnout {turnout_id} is {t.position}, "
                    f"need {required_pos} for route {route.route_id}"
                )

    def _get_next_segment(self, signal: "Signal") -> "TrackSegment | None":
        return self._segments.get(signal.next_segment_id)

    def _get_segment_after(self, segment: "TrackSegment") -> "TrackSegment | None":
        if segment.next_segment_id:
            return self._segments.get(segment.next_segment_id)
        return None