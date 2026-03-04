"""
Dashboard - Real-time telemetry panel and manual override controls.

Features:
  - Per-train speed, state, position display.
  - Interlocking status panel.
  - Manual override buttons: Emergency Stop, Signal Failure, CDV Fault.
  - ASFA event log.
"""

from __future__ import annotations
import pygame
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from entities.train import Train
    from entities.signal import Signal
    from entities.track_segment import TrackSegment

# ── Dashboard Palette ────────────────────────────────────────────────────────
COLOR_PANEL      = ( 22,  28,  38)
COLOR_PANEL_BORDER = ( 50,  60,  80)
COLOR_HEADER     = ( 30, 100, 180)
COLOR_TEXT       = (210, 220, 240)
COLOR_TEXT_WARN  = (230, 160,  30)
COLOR_TEXT_ALERT = (220,  50,  50)
COLOR_TEXT_OK    = ( 50, 200,  90)
COLOR_BTN        = ( 45,  55,  75)
COLOR_BTN_HOVER  = ( 70,  90, 120)
COLOR_BTN_DANGER = (140,  30,  30)


class Button:
    """A clickable Pygame button with hover and active states."""

    def __init__(self, rect: pygame.Rect, label: str,
                 color: tuple[int, int, int] = COLOR_BTN,
                 callback: Callable = None):
        self.rect     = rect
        self.label    = label
        self.color    = color
        self.callback = callback
        self._hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.callback:
                    self.callback()
                return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        color = COLOR_BTN_HOVER if self._hovered else self.color
        pygame.draw.rect(surface, color, self.rect, border_radius=4)
        pygame.draw.rect(surface, COLOR_PANEL_BORDER, self.rect, 1, border_radius=4)
        label = font.render(self.label, True, COLOR_TEXT)
        lx = self.rect.x + (self.rect.width  - label.get_width())  // 2
        ly = self.rect.y + (self.rect.height - label.get_height()) // 2
        surface.blit(label, (lx, ly))


class Dashboard:
    """
    Right-hand panel showing real-time telemetry and manual override controls.

    Args:
        surface:   The sub-surface or full screen to draw on.
        x_offset:  Left pixel boundary of the dashboard panel.
        trains:    Reference list of all train objects.
        signals:   Reference dict of all signal objects.
        segments:  Reference dict of all track segment objects.
    """

    PANEL_WIDTH  = 320
    ROW_HEIGHT   = 22
    MAX_LOG_LINES = 10

    def __init__(self,
                 surface:  pygame.Surface,
                 x_offset: int,
                 trains:   list["Train"],
                 signals:  dict[str, "Signal"],
                 segments: dict[str, "TrackSegment"]):
        self.surface  = surface
        self.x        = x_offset
        self.trains   = trains
        self.signals  = signals
        self.segments = segments
        self._log: list[str] = []

        pygame.font.init()
        self._font_sm = pygame.font.SysFont("monospace", 10)
        self._font_md = pygame.font.SysFont("monospace", 12)
        self._font_hd = pygame.font.SysFont("monospace", 13, bold=True)

        self._buttons: list[Button] = []
        self._init_buttons()

    def _init_buttons(self) -> None:
        bw, bh = 140, 24
        bx = self.x + 10

        # Emergency stop all trains
        self._buttons.append(Button(
            rect=pygame.Rect(bx, 520, bw, bh),
            label="⛔ EMERGENCY STOP",
            color=COLOR_BTN_DANGER,
            callback=self._cmd_emergency_all,
        ))
        # Fail first signal
        self._buttons.append(Button(
            rect=pygame.Rect(bx + 155, 520, bw, bh),
            label="⚡ SIGNAL FAULT",
            color=(80, 50, 20),
            callback=self._cmd_fail_signal,
        ))
        # CDV fault
        self._buttons.append(Button(
            rect=pygame.Rect(bx, 552, bw, bh),
            label="🔴 CDV FAULT",
            color=(60, 20, 50),
            callback=self._cmd_cdv_fault,
        ))
        # Restore all
        self._buttons.append(Button(
            rect=pygame.Rect(bx + 155, 552, bw, bh),
            label="✅ RESTORE ALL",
            color=(20, 60, 30),
            callback=self._cmd_restore_all,
        ))

    def handle_event(self, event: pygame.event.Event) -> None:
        for btn in self._buttons:
            btn.handle_event(event)

    def log(self, msg: str) -> None:
        """Append a message to the event log."""
        self._log.append(msg)
        if len(self._log) > self.MAX_LOG_LINES:
            self._log.pop(0)

    def draw(self) -> None:
        """Render the full dashboard panel."""
        panel_rect = pygame.Rect(self.x, 45, self.PANEL_WIDTH,
                                 self.surface.get_height() - 50)
        pygame.draw.rect(self.surface, COLOR_PANEL, panel_rect, border_radius=6)
        pygame.draw.rect(self.surface, COLOR_PANEL_BORDER, panel_rect, 1, border_radius=6)

        y = 55
        # ── Header
        y = self._draw_section_header("TRAIN TELEMETRY", y)

        # ── Train rows
        for train in self.trains:
            telem = train.get_telemetry()
            y     = self._draw_train_row(telem, y)

        y += 10
        y = self._draw_section_header("SIGNALS", y)
        y = self._draw_signal_table(y)

        y += 10
        y = self._draw_section_header("EVENT LOG", y)
        y = self._draw_log(y)

        # ── Buttons
        for btn in self._buttons:
            btn.draw(self.surface, self._font_sm)

    # ── Section helpers ───────────────────────────────────────────────────────

    def _draw_section_header(self, title: str, y: int) -> int:
        rect = pygame.Rect(self.x + 5, y, self.PANEL_WIDTH - 10, 18)
        pygame.draw.rect(self.surface, COLOR_HEADER, rect, border_radius=3)
        label = self._font_hd.render(title, True, (240, 240, 255))
        self.surface.blit(label, (self.x + 10, y + 2))
        return y + 22

    def _draw_train_row(self, telem: dict, y: int) -> int:
        state_colors = {
            "running":         COLOR_TEXT_OK,
            "braking":         COLOR_TEXT_WARN,
            "stopped":         COLOR_TEXT,
            "emergency_brake": COLOR_TEXT_ALERT,
            "waiting":         COLOR_TEXT_WARN,
        }
        state_col = state_colors.get(telem["state"], COLOR_TEXT)

        name_lbl  = self._font_md.render(
            f"  {telem['name'][:14]:<14}", True, COLOR_TEXT)
        speed_lbl = self._font_md.render(
            f"{telem['speed_kmh']:>6.1f} km/h", True, COLOR_TEXT_OK
            if telem["speed_kmh"] > 0 else COLOR_TEXT,
        )
        state_lbl = self._font_sm.render(
            f"  [{telem['state'].upper():<16}]", True, state_col)
        seg_lbl   = self._font_sm.render(
            f"  CDV: {telem['segment']}", True, (130, 140, 160))

        self.surface.blit(name_lbl,  (self.x + 5, y))
        self.surface.blit(speed_lbl, (self.x + 170, y))
        self.surface.blit(state_lbl, (self.x + 5, y + 13))
        self.surface.blit(seg_lbl,   (self.x + 165, y + 13))

        pygame.draw.line(self.surface, COLOR_PANEL_BORDER,
                         (self.x + 5, y + 28), (self.x + self.PANEL_WIDTH - 10, y + 28))
        return y + 32

    def _draw_signal_table(self, y: int) -> int:
        for sig_id, sig in list(self.signals.items())[:8]:
            col = {
                "red":    COLOR_TEXT_ALERT,
                "yellow": COLOR_TEXT_WARN,
                "green":  COLOR_TEXT_OK,
                "off":    COLOR_TEXT,
            }.get(sig.aspect, COLOR_TEXT)
            fail_tag = " [AVERÍA]" if sig.is_failed else ""
            lbl = self._font_sm.render(
                f"  {sig_id:<6} ● {sig.aspect.upper():<8}{fail_tag}", True, col)
            self.surface.blit(lbl, (self.x + 5, y))
            y += 14
        return y

    def _draw_log(self, y: int) -> int:
        for line in self._log[-self.MAX_LOG_LINES:]:
            lbl = self._font_sm.render(f"  {line[:38]}", True, COLOR_TEXT_WARN)
            self.surface.blit(lbl, (self.x + 5, y))
            y += 13
        return y

    # ── Button callbacks ──────────────────────────────────────────────────────

    def _cmd_emergency_all(self) -> None:
        for train in self.trains:
            train.trigger_manual_emergency()
        self.log("OPERATOR: Emergency stop ALL trains")

    def _cmd_fail_signal(self) -> None:
        if self.signals:
            sig = next(iter(self.signals.values()))
            sig.trigger_failure()
            self.log(f"OPERATOR: Avería triggered on {sig.signal_id}")

    def _cmd_cdv_fault(self) -> None:
        if self.segments:
            seg = next(iter(self.segments.values()))
            seg.trigger_fault()
            self.log(f"OPERATOR: CDV fault on {seg.segment_id}")

    def _cmd_restore_all(self) -> None:
        for sig in self.signals.values():
            sig.restore()
        for seg in self.segments.values():
            seg.restore_fault()
        self.log("OPERATOR: All faults restored")