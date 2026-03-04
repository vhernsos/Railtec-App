"""
main.py – ADIF Train Simulation & Automation System
Entry point.

Assembles the station layout, registers all entities with the interlocking,
and runs the Pygame main loop.

Standards: NAG 0-8-5.0 | NAS 811 | NAS 908 | NAS 154
"""

import sys
import pygame

from core.interlocking import InterlockingSystem, Route
from core.physics_engine import TrainType
from entities.signal import Signal
from entities.track_segment import TrackSegment
from entities.turnout import Turnout
from entities.train import Train, TrainState
from ui.renderer import Renderer
from ui.dashboard import Dashboard

# ── Window Configuration ─────────────────────────────────────────────────────
SCREEN_W    = 1280
SCREEN_H    = 720
FPS_TARGET  = 60
SIM_SPEED   = 1.0    # Simulation speed multiplier (1.0 = real-time equivalent)

# ── Station layout constants (pixels) ────────────────────────────────────────
Y_TRACK = {1: 220, 2: 300, 3: 380}   # Y pixel per platform track
X_LEFT  = 100
X_RIGHT = 840

# ── Station layout constants (metres) ────────────────────────────────────────
M_START = 0.0
M_END   = 2000.0    # 2 km station section


def build_station() -> tuple[
    dict[str, TrackSegment],
    dict[str, Signal],
    dict[str, Turnout],
    InterlockingSystem,
]:
    """
    Build the station topology:
      - 3 platform tracks (Vía 1, 2, 3)
      - Entry / exit block sections
      - Signals E1, E2, E3 (entry) and S1, S2, S3 (exit)
      - Turnouts A1, A2, A3
    """
    ilk = InterlockingSystem()

    # ── Helper: convert metres to pixels ─────────────────────────────────────
    def m2px(pos_m: float, track: int) -> tuple[int, int]:
        frac = (pos_m - M_START) / (M_END - M_START)
        px   = int(X_LEFT + frac * (X_RIGHT - X_LEFT))
        return px, Y_TRACK[track]

    # ── Track Segments (CDV) ─────────────────────────────────────────────────
    # Approach block (common entry)
    seg_approach = TrackSegment(
        segment_id="CDV-APP",
        start_m=0.0, end_m=300.0, gradient=0.0,
        start_px=m2px(0.0, 2), end_px=m2px(300.0, 2),
        next_segment_id="CDV-V1",
        track_type="conventional",
    )

    # Platform tracks
    seg_v1 = TrackSegment(
        segment_id="CDV-V1",
        start_m=300.0, end_m=1700.0, gradient=0.0,
        start_px=m2px(300.0, 1), end_px=m2px(1700.0, 1),
        next_segment_id="CDV-DEP",
    )
    seg_v2 = TrackSegment(
        segment_id="CDV-V2",
        start_m=300.0, end_m=1700.0, gradient=0.0,
        start_px=m2px(300.0, 2), end_px=m2px(1700.0, 2),
        next_segment_id="CDV-DEP",
    )
    seg_v3 = TrackSegment(
        segment_id="CDV-V3",
        start_m=300.0, end_m=1700.0, gradient=0.0,
        start_px=m2px(300.0, 3), end_px=m2px(1700.0, 3),
        next_segment_id="CDV-DEP",
    )

    # Departure block (common exit)
    seg_dep = TrackSegment(
        segment_id="CDV-DEP",
        start_m=1700.0, end_m=2000.0, gradient=0.0,
        start_px=m2px(1700.0, 2), end_px=m2px(2000.0, 2),
    )

    segments: dict[str, TrackSegment] = {
        s.segment_id: s for s in [seg_approach, seg_v1, seg_v2, seg_v3, seg_dep]
    }
    for s in segments.values():
        ilk.register_segment(s)

    # ── Signals ───────────────────────────────────────────────────────────────
    # Entry signals at chainage 290 m (before platform entry)
    sig_e1 = Signal("E1", "entry", 290.0, m2px(290.0, 1), "CDV-V1", slip_distance_m=50.0)
    sig_e2 = Signal("E2", "entry", 290.0, m2px(290.0, 2), "CDV-V2", slip_distance_m=50.0)
    sig_e3 = Signal("E3", "entry", 290.0, m2px(290.0, 3), "CDV-V3", slip_distance_m=50.0)

    # Exit signals at chainage 1710 m
    sig_s1 = Signal("S1", "exit", 1710.0, m2px(1710.0, 1), "CDV-DEP", slip_distance_m=50.0)
    sig_s2 = Signal("S2", "exit", 1710.0, m2px(1710.0, 2), "CDV-DEP", slip_distance_m=50.0)
    sig_s3 = Signal("S3", "exit", 1710.0, m2px(1710.0, 3), "CDV-DEP", slip_distance_m=50.0)

    signals: dict[str, Signal] = {
        s.signal_id: s for s in [sig_e1, sig_e2, sig_e3, sig_s1, sig_s2, sig_s3]
    }
    for s in signals.values():
        ilk.register_signal(s)

    # ── Turnouts ──────────────────────────────────────────────────────────────
    # Entry throat (A1 → Vía 1/2, A2 → Vía 2/3)
    tp = m2px(280.0, 2)
    t_a1 = Turnout(
        "A1", tp, "normal",
        common_end_px =m2px(250.0, 2),
        normal_end_px =m2px(310.0, 2),
        reverse_end_px=m2px(310.0, 1),
    )
    t_a2 = Turnout(
        "A2", m2px(270.0, 2), "normal",
        common_end_px =m2px(240.0, 2),
        normal_end_px =m2px(300.0, 2),
        reverse_end_px=m2px(300.0, 3),
    )

    # Exit throat (A3, A4)
    t_a3 = Turnout(
        "A3", m2px(1720.0, 2), "normal",
        common_end_px =m2px(1750.0, 2),
        normal_end_px =m2px(1700.0, 2),
        reverse_end_px=m2px(1700.0, 1),
    )
    t_a4 = Turnout(
        "A4", m2px(1730.0, 2), "normal",
        common_end_px =m2px(1760.0, 2),
        normal_end_px =m2px(1710.0, 2),
        reverse_end_px=m2px(1710.0, 3),
    )

    turnouts: dict[str, Turnout] = {
        t.turnout_id: t for t in [t_a1, t_a2, t_a3, t_a4]
    }
    for t in turnouts.values():
        ilk.register_turnout(t)

    # ── Routes ────────────────────────────────────────────────────────────────
    # ── Routes ────────────────────────────────────────────────────────────────
    routes = [
        Route("E1-V1", "E1", "S1", ["CDV-APP", "CDV-V1", "CDV-DEP"],
              {"A1": "reverse", "A3": "reverse"}, slip_distance=50.0),  # ← was slip_distance_m
        Route("E2-V2", "E2", "S2", ["CDV-APP", "CDV-V2", "CDV-DEP"],
              {"A1": "normal", "A3": "normal"}, slip_distance=50.0),  # ← was slip_distance_m
        Route("E3-V3", "E3", "S3", ["CDV-APP", "CDV-V3", "CDV-DEP"],
              {"A2": "reverse", "A4": "reverse"}, slip_distance=50.0),  # ← was slip_distance_m
    ]
    for r in routes:
        ilk.register_route(r)

    return segments, signals, turnouts, ilk


def build_trains(signals: dict[str, Signal]) -> list[Train]:
    """Create the autonomous train agents."""
    trains = []

    # Train 1: AVE on Vía 1
    t1 = Train(
        train_id="T1",
        name="AVE 00102",
        pos_m=0.0,
        speed_kmh=0.0,
        max_speed_kmh=120.0,
        route_segments=["CDV-APP", "CDV-V1", "CDV-DEP"],
        route_signals=[(290.0, "E1"), (1710.0, "S1")],
        train_type=TrainType.LAMBDA_150,
        color_idx=0,
    )

    # Train 2: Regional on Vía 2
    t2 = Train(
        train_id="T2",
        name="MD  04501",
        pos_m=0.0,
        speed_kmh=0.0,
        max_speed_kmh=100.0,
        route_segments=["CDV-APP", "CDV-V2", "CDV-DEP"],
        route_signals=[(290.0, "E2"), (1710.0, "S2")],
        train_type=TrainType.LAMBDA_100,
        color_idx=1,
    )

    # Train 3: Cercanías on Vía 3
    t3 = Train(
        train_id="T3",
        name="C-4 07821",
        pos_m=0.0,
        speed_kmh=0.0,
        max_speed_kmh=80.0,
        route_segments=["CDV-APP", "CDV-V3", "CDV-DEP"],
        route_signals=[(290.0, "E3"), (1710.0, "S3")],
        train_type=TrainType.LAMBDA_100,
        color_idx=2,
    )

    trains = [t1, t2, t3]
    return trains


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("ADIF Train Simulation System – Estación Modelo")
    clock  = pygame.time.Clock()

    # ── Build world ───────────────────────────────────────────────────────────
    segments, signals, turnouts, ilk = build_station()
    trains = build_trains(signals)

    renderer  = Renderer(screen)
    dashboard = Dashboard(
        surface=screen,
        x_offset=SCREEN_W - Dashboard.PANEL_WIDTH - 5,
        trains=trains,
        signals=signals,
        segments=segments,
    )

    # ── Lock routes and start trains ──────────────────────────────────────────
    route_map = {
        "T1": ("E1-V1", "A1", "reverse"),
        "T2": ("E2-V2", "A1", "normal"),
        "T3": ("E3-V3", "A2", "reverse"),
    }

    for train in trains:
        route_id, turnout_id, pos = route_map[train.train_id]
        t = turnouts.get(turnout_id)
        if t:
            t.position = pos   # Pre-set turnout
        try:
            ilk.request_route(route_id, train.train_id)
        except Exception as e:
            dashboard.log(f"Route lock failed: {e}")
        train.start()

    tick = 0

    # ── Main loop ─────────────────────────────────────────────────────────────
    running = True
    while running:
        dt = clock.tick(FPS_TARGET) / 1000.0 * SIM_SPEED

        # ── Events ───────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    # Toggle all trains start/stop
                    for t in trains:
                        if t.state == TrainState.STOPPED:
                            t.start()
                        else:
                            t.trigger_manual_emergency()
                    dashboard.log("SPACE: toggle all trains")
                elif event.key == pygame.K_r:
                    dashboard._cmd_restore_all()
            dashboard.handle_event(event)

        # ── Simulation step ───────────────────────────────────────────────────
        ilk.update_signal_aspects()

        for train in trains:
            train.update(dt, signals, segments)
            # Update pixel position for renderer
            train.pos_px = renderer.map_pos(
                pos_m=train.pos_m,
                track_y=Y_TRACK[int(train.train_id[1])],
                start_m=M_START,
                end_m=M_END,
            )
            # Check ASFA log
            if train._log:
                for msg in train._log:
                    dashboard.log(f"{train.name}: {msg}")
                train._log.clear()

            # Wrap-around: restart train when it leaves the section
            if train.pos_m > M_END + 100:
                train.pos_m    = 0.0
                train.speed_kmh = 0.0
                train.state    = TrainState.STOPPED
                for seg in segments.values():
                    if seg._occupying_train == train.train_id:
                        seg.clear()
                # Re-lock route
                route_id = route_map[train.train_id][0]
                try:
                    ilk.release_route(route_id, train.train_id)
                    ilk.request_route(route_id, train.train_id)
                except Exception:
                    pass
                train.start()

        # ── Render ────────────────────────────────────────────────────────────
        renderer.render(trains, signals, segments, turnouts, tick)
        dashboard.draw()

        pygame.display.flip()
        tick += 1

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()