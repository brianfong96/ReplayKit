"""
ReplayKit — Record and replay mouse & keyboard actions.

UI buttons: Record, Play, Repeat, Stop
Global hotkeys (work even when window is not focused):
  F1 = Toggle Record
  F2 = Play once
  F3 = Repeat (loop)
  F4 = Stop playback / recording
Speed slider adjusts playback speed (0.25x – 4x).
"""

import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from enum import Enum, auto
from typing import List

from pynput import mouse, keyboard
from pynput.mouse import Button as MButton
from pynput.keyboard import Key

__version__ = "1.0.0"
APP_NAME = "ReplayKit"

MOVE_THROTTLE_S = 0.015  # ~66 fps cap on mouse-move events
POLL_INTERVAL_MS = 200
SPEED_MIN = 0.25
SPEED_MAX = 4.0
SLEEP_GRANULARITY = 0.01

HOTKEYS = {Key.f1, Key.f2, Key.f3, Key.f4}


# ── Data types ───────────────────────────────────────────────────────────────

class ActionType(Enum):
    MOUSE_MOVE = auto()
    MOUSE_CLICK = auto()
    MOUSE_SCROLL = auto()
    KEY_PRESS = auto()
    KEY_RELEASE = auto()


@dataclass
class Action:
    kind: ActionType
    timestamp: float
    x: int = 0
    y: int = 0
    button: object = None
    pressed: bool = True
    dx: int = 0
    dy: int = 0
    key: object = None


# ── Recorder ─────────────────────────────────────────────────────────────────

class Recorder:
    """Captures mouse and keyboard events into a list of Actions."""

    def __init__(self) -> None:
        self.actions: List[Action] = []
        self._start_time: float = 0.0
        self._mouse_listener: mouse.Listener | None = None
        self._key_listener: keyboard.Listener | None = None
        self._recording = False
        self._last_move_time: float = 0.0

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        self.actions.clear()
        self._recording = True
        self._start_time = time.perf_counter()
        self._last_move_time = 0.0
        self._mouse_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._key_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._mouse_listener.start()
        self._key_listener.start()

    def stop(self) -> None:
        self._recording = False
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._key_listener:
            self._key_listener.stop()

    def strip_hotkeys(self) -> None:
        """Remove hotkey press/release events so they don't replay."""
        self.actions = [
            a for a in self.actions
            if not (a.kind in (ActionType.KEY_PRESS, ActionType.KEY_RELEASE)
                    and a.key in HOTKEYS)
        ]

    def _elapsed(self) -> float:
        return time.perf_counter() - self._start_time

    def _on_move(self, x: int, y: int) -> None:
        now = time.perf_counter()
        if now - self._last_move_time < MOVE_THROTTLE_S:
            return
        self._last_move_time = now
        self.actions.append(
            Action(ActionType.MOUSE_MOVE, self._elapsed(), x=int(x), y=int(y))
        )

    def _on_click(self, x: int, y: int, button: MButton, pressed: bool) -> None:
        self.actions.append(
            Action(ActionType.MOUSE_CLICK, self._elapsed(),
                   x=int(x), y=int(y), button=button, pressed=pressed)
        )

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self.actions.append(
            Action(ActionType.MOUSE_SCROLL, self._elapsed(),
                   x=int(x), y=int(y), dx=dx, dy=dy)
        )

    def _on_press(self, key: Key) -> None:
        self.actions.append(Action(ActionType.KEY_PRESS, self._elapsed(), key=key))

    def _on_release(self, key: Key) -> None:
        self.actions.append(Action(ActionType.KEY_RELEASE, self._elapsed(), key=key))


# ── Player ───────────────────────────────────────────────────────────────────

class Player:
    """Replays a list of Actions with optional looping."""

    def __init__(self) -> None:
        self._mouse_ctl = mouse.Controller()
        self._key_ctl = keyboard.Controller()
        self._playing = False

    @property
    def playing(self) -> bool:
        return self._playing

    def play(self, actions: List[Action], *, loop: bool = False,
             on_done=None) -> None:
        if not actions:
            return
        self._playing = True
        threading.Thread(
            target=self._run, args=(actions, loop, on_done), daemon=True
        ).start()

    def stop(self) -> None:
        self._playing = False

    def _run(self, actions: List[Action], loop: bool, on_done) -> None:
        try:
            while True:
                prev_ts = 0.0
                for act in actions:
                    if not self._playing:
                        return
                    delay = act.timestamp - prev_ts
                    if delay > 0:
                        end = time.perf_counter() + delay
                        while time.perf_counter() < end:
                            if not self._playing:
                                return
                            time.sleep(min(SLEEP_GRANULARITY,
                                           max(0, end - time.perf_counter())))
                    prev_ts = act.timestamp
                    self._execute(act)
                if not loop:
                    break
        finally:
            self._playing = False
            if on_done:
                on_done()

    def _execute(self, act: Action) -> None:
        if act.kind == ActionType.MOUSE_MOVE:
            self._mouse_ctl.position = (act.x, act.y)
        elif act.kind == ActionType.MOUSE_CLICK:
            self._mouse_ctl.position = (act.x, act.y)
            if act.pressed:
                self._mouse_ctl.press(act.button)
            else:
                self._mouse_ctl.release(act.button)
        elif act.kind == ActionType.MOUSE_SCROLL:
            self._mouse_ctl.position = (act.x, act.y)
            self._mouse_ctl.scroll(act.dx, act.dy)
        elif act.kind == ActionType.KEY_PRESS:
            self._key_ctl.press(act.key)
        elif act.kind == ActionType.KEY_RELEASE:
            self._key_ctl.release(act.key)


# ── UI ───────────────────────────────────────────────────────────────────────

class ReplayKitApp:
    """Main application window."""

    def __init__(self) -> None:
        self.recorder = Recorder()
        self.player = Player()

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self._build_ui()

        self._hotkey_listener = keyboard.Listener(on_press=self._on_global_key)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    # ── UI construction ──

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.grid()

        ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=4, pady=(0, 8)
        )

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var,
                  font=("Segoe UI", 10)).grid(
            row=1, column=0, columnspan=4, pady=(0, 8)
        )

        btn_kw = {"width": 10}

        self.btn_record = ttk.Button(
            frame, text="⏺ Record F1",
            command=self._toggle_record, **btn_kw)
        self.btn_record.grid(row=2, column=0, padx=4, pady=4)

        self.btn_play = ttk.Button(
            frame, text="▶ Play F2",
            command=self._play_once, state="disabled", **btn_kw)
        self.btn_play.grid(row=2, column=1, padx=4, pady=4)

        self.btn_repeat = ttk.Button(
            frame, text="🔁 Repeat F3",
            command=self._play_loop, state="disabled", **btn_kw)
        self.btn_repeat.grid(row=2, column=2, padx=4, pady=4)

        self.btn_stop = ttk.Button(
            frame, text="⏹ Stop F4",
            command=self._stop_all, state="disabled", **btn_kw)
        self.btn_stop.grid(row=2, column=3, padx=4, pady=4)

        self.action_count_var = tk.StringVar(value="Actions: 0")
        ttk.Label(frame, textvariable=self.action_count_var,
                  font=("Segoe UI", 9)).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        ttk.Label(frame, text="F1/F2/F3/F4",
                  font=("Segoe UI", 9, "italic")).grid(
            row=3, column=2, columnspan=2, sticky="e", pady=(4, 0)
        )

        speed_frame = ttk.Frame(frame)
        speed_frame.grid(row=4, column=0, columnspan=4, pady=(8, 0), sticky="ew")
        ttk.Label(speed_frame, text="Speed:", font=("Segoe UI", 9)).pack(side="left")
        self.speed_var = tk.DoubleVar(value=1.0)
        ttk.Scale(speed_frame, from_=SPEED_MIN, to=SPEED_MAX,
                  variable=self.speed_var,
                  orient="horizontal").pack(side="left", fill="x", expand=True, padx=(4, 4))
        self.speed_label = ttk.Label(speed_frame, text="1.0x",
                                     font=("Segoe UI", 9), width=5)
        self.speed_label.pack(side="left")
        self.speed_var.trace_add("write", self._update_speed_label)

    def _update_speed_label(self, *_) -> None:
        self.speed_label.config(text=f"{self.speed_var.get():.1f}x")

    # ── Recording ──

    def _toggle_record(self) -> None:
        if self.recorder.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self.recorder.start()
        self.status_var.set("🔴 Recording… (click Record or F1 to stop)")
        self.btn_record.config(text="⏹ Stop Rec")
        self.btn_play.config(state="disabled")
        self.btn_repeat.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self._poll_action_count()

    def _stop_recording(self) -> None:
        self.recorder.stop()
        self.recorder.strip_hotkeys()
        count = len(self.recorder.actions)
        self.action_count_var.set(f"Actions: {count}")
        self.status_var.set(f"Recorded {count} actions" if count else "Nothing recorded")
        self.btn_record.config(text="⏺ Record F1")
        state = "normal" if count else "disabled"
        self.btn_play.config(state=state)
        self.btn_repeat.config(state=state)

    def _poll_action_count(self) -> None:
        if self.recorder.recording:
            self.action_count_var.set(f"Actions: {len(self.recorder.actions)}")
            self.root.after(POLL_INTERVAL_MS, self._poll_action_count)

    # ── Playback ──

    def _play_once(self) -> None:
        self._start_playback(loop=False)

    def _play_loop(self) -> None:
        self._start_playback(loop=True)

    def _start_playback(self, loop: bool) -> None:
        if not self.recorder.actions:
            return
        speed = self.speed_var.get()
        scaled = [
            Action(a.kind, a.timestamp / speed,
                   x=a.x, y=a.y, button=a.button, pressed=a.pressed,
                   dx=a.dx, dy=a.dy, key=a.key)
            for a in self.recorder.actions
        ]
        self.status_var.set("▶ Playing…" if not loop else "🔁 Repeating…")
        self.btn_play.config(state="disabled")
        self.btn_repeat.config(state="disabled")
        self.btn_record.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.player.play(
            scaled, loop=loop,
            on_done=lambda: self.root.after(0, self._playback_finished),
        )

    def _stop_all(self) -> None:
        self.player.stop()
        if self.recorder.recording:
            self._stop_recording()
        self._playback_finished()

    def _playback_finished(self) -> None:
        self.status_var.set("Ready")
        has = len(self.recorder.actions) > 0
        self.btn_play.config(state="normal" if has else "disabled")
        self.btn_repeat.config(state="normal" if has else "disabled")
        self.btn_record.config(state="normal")
        self.btn_stop.config(state="disabled")

    # ── Global hotkeys ──

    def _on_global_key(self, key) -> None:
        if key == Key.f1:
            self.root.after(0, self._toggle_record)
        elif key == Key.f2:
            if not self.recorder.recording and not self.player.playing:
                self.root.after(0, self._play_once)
        elif key == Key.f3:
            if not self.recorder.recording and not self.player.playing:
                self.root.after(0, self._play_loop)
        elif key == Key.f4:
            if self.player.playing or self.recorder.recording:
                self.root.after(0, self._stop_all)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ReplayKitApp().run()


if __name__ == "__main__":
    main()
