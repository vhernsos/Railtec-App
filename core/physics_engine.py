"""
Physics Engine - NAG 0-8-5.0 Compliance
Implements braking curves, braking distances, and ASFA supervision logic.

References:
  - NAG 0-8-5.0 Annex 1 & 2: Braking distances by speed, gradient, and lambda (λ)
  - NAS 154: ASFA Digital supervision reactions
"""

import math
from dataclasses import dataclass
from enum import Enum


class TrainType(Enum):
    """
    λ (lambda) classification per NAG 0-8-5.0.
    Lambda represents the braking coefficient of the train.
    Higher lambda = better braking performance.
    """
    LAMBDA_80  = 80   # Freight trains, heavy consists
    LAMBDA_100 = 100  # Standard passenger
    LAMBDA_120 = 120  # High-performance passenger / tilting trains
    LAMBDA_150 = 150  # High-speed units (AVE)


# ── NAG 0-8-5.0 Annex 1 & 2 ────────────────────────────────────────────────
# Braking distance table (meters) indexed by [lambda][speed_km_h][gradient_permil]
# Format: BRAKING_TABLE[lambda][speed] = {gradient: distance_m}
# Gradients in ‰ (per mille): negative = downhill, 0 = level, positive = uphill
# Values are illustrative approximations of the official ADIF tables.

BRAKING_TABLE: dict[int, dict[int, dict[int, float]]] = {
    80: {
        60:  {-20: 520, -10: 470, 0: 420, 10: 375, 20: 330},
        80:  {-20: 870, -10: 790, 0: 710, 10: 635, 20: 560},
        100: {-20:1280, -10:1160, 0:1050, 10: 940, 20: 835},
        120: {-20:1780, -10:1610, 0:1460, 10:1310, 20:1165},
        140: {-20:2370, -10:2150, 0:1950, 10:1755, 20:1560},
        160: {-20:3070, -10:2790, 0:2530, 10:2280, 20:2030},
    },
    100: {
        60:  {-20: 420, -10: 375, 0: 335, 10: 300, 20: 265},
        80:  {-20: 710, -10: 640, 0: 575, 10: 515, 20: 455},
        100: {-20:1050, -10: 950, 0: 855, 10: 765, 20: 680},
        120: {-20:1460, -10:1320, 0:1190, 10:1065, 20: 945},
        140: {-20:1950, -10:1770, 0:1595, 10:1430, 20:1270},
        160: {-20:2530, -10:2300, 0:2075, 10:1860, 20:1655},
    },
    120: {
        60:  {-20: 340, -10: 305, 0: 275, 10: 245, 20: 218},
        80:  {-20: 575, -10: 520, 0: 468, 10: 418, 20: 370},
        100: {-20: 855, -10: 775, 0: 698, 10: 625, 20: 555},
        120: {-20:1190, -10:1080, 0: 975, 10: 872, 20: 775},
        140: {-20:1595, -10:1450, 0:1308, 10:1172, 20:1042},
        160: {-20:2075, -10:1890, 0:1706, 10:1530, 20:1360},
    },
    150: {
        60:  {-20: 265, -10: 238, 0: 214, 10: 192, 20: 170},
        80:  {-20: 450, -10: 407, 0: 366, 10: 328, 20: 290},
        100: {-20: 670, -10: 608, 0: 548, 10: 490, 20: 436},
        120: {-20: 935, -10: 850, 0: 768, 10: 688, 20: 612},
        140: {-20:1255, -10:1143, 0:1033, 10: 926, 20: 824},
        160: {-20:1635, -10:1492, 0:1350, 10:1212, 20:1078},
        200: {-20:2500, -10:2285, 0:2075, 10:1870, 20:1670},
        250: {-20:4200, -10:3850, 0:3510, 10:3180, 20:2850},
        300: {-20:6800, -10:6250, 0:5720, 10:5210, 20:4720},
    },
}

# ASFA protection distance: beacon placed 5 m before the signal (NAG 0-8-5.0, p.10)
ASFA_BEACON_OFFSET_M: float = 5.0

# Default visibility distance per track type (metres) – Section 6.1 NAG 0-8-5.0
VISIBILITY_DISTANCE_M: dict[str, float] = {
    "conventional": 400.0,
    "high_speed":   600.0,
    "yard":         200.0,
}


@dataclass
class BrakingResult:
    """Result object returned by braking calculations."""
    distance_m: float          # Total braking distance in metres
    braking_point_m: float     # Position where braking must START
    gradient_permil: float     # Gradient used
    lambda_value: int          # λ used
    speed_kmh: float           # Entry speed used
    asfa_beacon_pos_m: float   # Position of the ASFA beacon (signal_pos - 5 m)


class PhysicsEngine:
    """
    Implements braking distance calculations per NAG 0-8-5.0.

    Usage:
        engine = PhysicsEngine(train_type=TrainType.LAMBDA_100)
        result = engine.compute_braking(speed_kmh=120, gradient=0, signal_pos=5000.0)
    """

    def __init__(self, train_type: TrainType = TrainType.LAMBDA_100):
        self.train_type = train_type
        self.lambda_value: int = train_type.value

    # ── Interpolation helpers ────────────────────────────────────────────────

    @staticmethod
    def _interpolate_speed(table_speeds: dict[int, dict[int, float]],
                           speed_kmh: float,
                           gradient: int) -> float:
        """Linearly interpolate braking distance between tabulated speeds."""
        speeds = sorted(table_speeds.keys())
        if speed_kmh <= speeds[0]:
            return PhysicsEngine._interpolate_gradient(table_speeds[speeds[0]], gradient)
        if speed_kmh >= speeds[-1]:
            return PhysicsEngine._interpolate_gradient(table_speeds[speeds[-1]], gradient)

        for i in range(len(speeds) - 1):
            v0, v1 = speeds[i], speeds[i + 1]
            if v0 <= speed_kmh <= v1:
                d0 = PhysicsEngine._interpolate_gradient(table_speeds[v0], gradient)
                d1 = PhysicsEngine._interpolate_gradient(table_speeds[v1], gradient)
                t = (speed_kmh - v0) / (v1 - v0)
                return d0 + t * (d1 - d0)
        return 0.0

    @staticmethod
    def _interpolate_gradient(grad_table: dict[int, float], gradient: float) -> float:
        """Linearly interpolate braking distance between tabulated gradients."""
        gradients = sorted(grad_table.keys())
        if gradient <= gradients[0]:
            return grad_table[gradients[0]]
        if gradient >= gradients[-1]:
            return grad_table[gradients[-1]]
        for i in range(len(gradients) - 1):
            g0, g1 = gradients[i], gradients[i + 1]
            if g0 <= gradient <= g1:
                d0, d1 = grad_table[g0], grad_table[g1]
                t = (gradient - g0) / (g1 - g0)
                return d0 + t * (d1 - d0)
        return 0.0

    # ── Public API ───────────────────────────────────────────────────────────

    def compute_braking(self,
                        speed_kmh: float,
                        gradient: float,
                        signal_pos_m: float) -> BrakingResult:
        """
        Compute full braking result for a given speed and gradient.

        Args:
            speed_kmh:    Current speed of the train in km/h.
            gradient:     Track gradient in ‰ (positive = uphill, negative = downhill).
            signal_pos_m: Track coordinate (metres) of the RED signal face.

        Returns:
            BrakingResult with distance, braking point position, and ASFA beacon position.
        """
        lam_table = BRAKING_TABLE.get(self.lambda_value)
        if lam_table is None:
            raise ValueError(f"No braking table for λ={self.lambda_value}")

        distance_m = self._interpolate_speed(lam_table, speed_kmh, gradient)

        # Braking must start at:  signal_pos - braking_distance
        braking_point_m = signal_pos_m - distance_m

        # ASFA beacon is placed 5 m before the signal face (NAG 0-8-5.0, p.10)
        asfa_beacon_pos_m = signal_pos_m - ASFA_BEACON_OFFSET_M

        return BrakingResult(
            distance_m=distance_m,
            braking_point_m=braking_point_m,
            gradient_permil=gradient,
            lambda_value=self.lambda_value,
            speed_kmh=speed_kmh,
            asfa_beacon_pos_m=asfa_beacon_pos_m,
        )

    def current_deceleration(self, speed_kmh: float, gradient: float) -> float:
        """
        Estimate instantaneous deceleration (m/s²) from the braking table.

        Uses v² = 2·a·d  →  a = v²/(2·d)
        """
        if speed_kmh < 1.0:
            return 0.0
        dummy_result = self.compute_braking(speed_kmh, gradient, signal_pos_m=0.0)
        v_ms = speed_kmh / 3.6
        if dummy_result.distance_m <= 0:
            return 1.0  # fallback
        decel = (v_ms ** 2) / (2.0 * dummy_result.distance_m)
        return max(decel, 0.05)   # floor to avoid zero

    def check_visibility(self,
                         track_type: str,
                         distance_to_signal_m: float) -> bool:
        """
        Returns True when the train is within the visibility distance of a signal.
        NAG 0-8-5.0, Section 6.1.
        """
        vis = VISIBILITY_DISTANCE_M.get(track_type, 400.0)
        return distance_to_signal_m <= vis


# ── ASFA Supervision (NAS 154) ───────────────────────────────────────────────

class ASFABeaconType(Enum):
    """NAS 154 beacon categories."""
    ADVANCE  = "advance"   # Preaviso – yellow signal ahead
    SIGNAL   = "signal"    # At the signal itself
    STOP     = "stop"      # Protects a stop/buffer


@dataclass
class ASFAEvent:
    """Fired when a train passes over an ASFA beacon."""
    beacon_type: ASFABeaconType
    signal_aspect: str   # "green", "yellow", "red"
    train_speed_kmh: float
    permitted_speed_kmh: float
    requires_brake: bool
    requires_emergency: bool


class ASFASupervisor:
    """
    NAS 154 ASFA Digital supervision logic.

    Rules implemented:
      - ADVANCE beacon + yellow aspect: if speed > permitted → emergency brake.
      - SIGNAL beacon + red aspect:     always emergency brake (missed stop).
      - STOP beacon (end of authority): emergency brake if speed > 0.
    """

    # Speed thresholds per NAS 154
    MAX_SPEED_AT_CAUTION_KMH: float = 160.0   # max speed allowed through a yellow
    EMERGENCY_SPEED_MARGIN_KMH: float = 5.0   # tolerance before triggering brakes

    def process_beacon(self,
                       beacon_type: ASFABeaconType,
                       signal_aspect: str,
                       train_speed_kmh: float,
                       line_speed_kmh: float = 160.0) -> ASFAEvent:
        """
        Process a beacon passage event.

        Args:
            beacon_type:       Type of ASFA beacon passed.
            signal_aspect:     Current aspect of the protecting signal.
            train_speed_kmh:   Speed of the train at the beacon.
            line_speed_kmh:    Maximum permitted line speed.

        Returns:
            ASFAEvent describing whether braking/emergency is required.
        """
        requires_brake = False
        requires_emergency = False

        if beacon_type == ASFABeaconType.ADVANCE:
            if signal_aspect in ("yellow", "red"):
                permitted = min(line_speed_kmh, self.MAX_SPEED_AT_CAUTION_KMH)
                if train_speed_kmh > permitted + self.EMERGENCY_SPEED_MARGIN_KMH:
                    requires_emergency = True
                elif train_speed_kmh > permitted:
                    requires_brake = True
            permitted_speed = self.MAX_SPEED_AT_CAUTION_KMH

        elif beacon_type == ASFABeaconType.SIGNAL:
            if signal_aspect == "red":
                requires_emergency = True
            permitted_speed = line_speed_kmh if signal_aspect == "green" else 0.0

        elif beacon_type == ASFABeaconType.STOP:
            if train_speed_kmh > self.EMERGENCY_SPEED_MARGIN_KMH:
                requires_emergency = True
            permitted_speed = 0.0

        else:
            permitted_speed = line_speed_kmh

        return ASFAEvent(
            beacon_type=beacon_type,
            signal_aspect=signal_aspect,
            train_speed_kmh=train_speed_kmh,
            permitted_speed_kmh=permitted_speed,
            requires_brake=requires_brake,
            requires_emergency=requires_emergency,
        )