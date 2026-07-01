#!/usr/bin/env python3
"""
Generate real-time log files for testing monitor.py.

Exercises every status transition:
  active → idle → missing  (file stops, then gets deleted)
  active → idle → active   (file pauses, then resumes)
  missing → active          (file appears late)

Creates 3 persistent files that loop, plus dynamic files that appear,
go idle, get deleted, and reappear on a timeline.
"""

import os
import random
import threading
import time
from datetime import datetime

TIMESTAMP_FORMATS = {
    "type1": "%Y-%m-%d %H:%M:%S.%f",
    "type2": "%Y/%m/%d %H:%M:%S.%f",
    "type3": "%H:%M:%S.%f",
}


def _entry(pct: float, fmt: str, msg: str | None = None) -> str:
    ts = datetime.now().strftime(fmt)[:-3]
    progress = pct * 100
    if msg:
        return f"[{ts}] {progress:.2f}% {msg}"
    return f"[{ts}] {progress:.2f}%"


class LogWriter(threading.Thread):
    """Thread that writes a log file in a loop, with pause/stop control."""

    def __init__(
        self,
        path: str,
        fmt_key: str,
        total_steps: int,
        dt_mean: float,
        dt_var: float,
        error_rate: float = 0.03,
    ):
        super().__init__(daemon=True)
        self.path = path
        self._fmt = TIMESTAMP_FORMATS[fmt_key]
        self._steps = total_steps
        self._dt_mean = dt_mean
        self._dt_var = dt_var
        self._error_rate = error_rate
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._pause.set()  # start unpaused

    def stop(self) -> None:
        self._stop.set()
        self._pause.set()  # unblock if paused

    def pause(self) -> None:
        self._pause.clear()

    def resume(self) -> None:
        self._pause.set()

    @property
    def paused(self) -> bool:
        return not self._pause.is_set()

    def run(self) -> None:
        loop = 0
        while not self._stop.is_set():
            loop += 1
            self._pause.wait()  # block if paused
            if self._stop.is_set():
                break
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(f"<<<BEGIN>>>  loop={loop}\n")
                f.flush()
                for i in range(self._steps):
                    if self._stop.is_set():
                        break
                    self._pause.wait()
                    if self._stop.is_set():
                        break
                    pct = (i + 1) / self._steps
                    r = random.random()
                    if r < self._error_rate:
                        msg = " an error occurred."
                    elif r < self._error_rate * 2:
                        msg = " a warning occurred."
                    elif r < self._error_rate * 2.5:
                        msg = " an NaN occurred."
                    else:
                        msg = None
                    f.write(_entry(pct, self._fmt, msg) + "\n")
                    f.flush()
                    dt = max(random.gauss(self._dt_mean, self._dt_var), 0.01)
                    time.sleep(dt)
                f.write("<<<END>>>\n")
                f.flush()
            # short gap between loops so file doesn't stay at END for zero time
            if not self._stop.is_set():
                time.sleep(0.5)


# ---------------------------------------------------------------------------
# Scheduled dynamic events
# ---------------------------------------------------------------------------


class DynamicScheduler:
    """Manages dynamic file lifecycles: create, pause, resume, delete."""

    def __init__(self, base_dir: str = "."):
        self._base = base_dir
        self._writers: dict[str, LogWriter] = {}
        self._events: list[tuple[float, str, str, dict]] = []
        # (fire_time, action, path, kwargs)
        self._t0 = time.time()

    def _at(self, offset: float) -> float:
        return self._t0 + offset

    def schedule(self, offset: float, action: str, path: str, **kw) -> None:
        self._events.append((self._at(offset), action, path, kw))
        self._events.sort(key=lambda e: e[0])

    def _abspath(self, p: str) -> str:
        return os.path.join(self._base, p)

    def _create(self, path: str, **kw) -> None:
        abs_path = self._abspath(path)
        if path in self._writers:
            return
        w = LogWriter(abs_path, **kw)
        self._writers[path] = w
        w.start()
        print(f"  [scheduler] CREATED  {abs_path}")

    def _pause(self, path: str) -> None:
        w = self._writers.get(path)
        if w and not w.paused:
            w.pause()
            print(f"  [scheduler] PAUSED   {self._abspath(path)}  → will go idle")

    def _resume(self, path: str) -> None:
        w = self._writers.get(path)
        if w and w.paused:
            w.resume()
            print(f"  [scheduler] RESUMED  {self._abspath(path)}  → back to active")

    def _delete(self, path: str) -> None:
        abs_path = self._abspath(path)
        w = self._writers.pop(path, None)
        if w:
            w.stop()
            w.join(timeout=5)
            # Windows may hold the handle briefly after join; retry
            for _ in range(10):
                try:
                    os.remove(abs_path)
                    print(f"  [scheduler] DELETED  {abs_path}")
                    return
                except PermissionError:
                    time.sleep(0.2)
                except FileNotFoundError:
                    return
            print(f"  [scheduler] WARNING: could not delete {abs_path}")

    def run(self, stop_event: threading.Event) -> None:
        idx = 0
        while not stop_event.is_set() and idx < len(self._events):
            fire_at, action, path, kw = self._events[idx]
            now = time.time()
            if now >= fire_at:
                {
                    "create": self._create,
                    "pause": self._pause,
                    "resume": self._resume,
                    "delete": self._delete,
                }[action](path, **kw)
                idx += 1
            else:
                time.sleep(0.5)

        # after all events, just wait for stop
        while not stop_event.is_set():
            time.sleep(1)

    def stop_all(self) -> None:
        for w in self._writers.values():
            w.stop()
        for w in self._writers.values():
            w.join(timeout=5)
        # clean up leftover files (only if thread has exited)
        for p in list(self._writers.keys()):
            try:
                os.remove(self._abspath(p))
            except (FileNotFoundError, PermissionError):
                pass


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("Monitor Demo — exercises all status transitions")
    print("=" * 60)
    print()
    print("Persistent files (loop forever):")
    print("  progress1.log  — fast  (0.5s between entries, 120 steps)")
    print("  progress2.log  — medium (1.0s between entries,  60 steps)")
    print("  progress3.log  — slow   (2.0s between entries,  30 steps)")
    print()
    print("Timeline (seconds from start):")
    print("  t=20   create dynamic_appear.log  (short-lived writer)")
    print("  t=40   pause  progress1.log      (goes idle)")
    print("  t=65   delete dynamic_appear.log  (goes missing)")
    print("  t=75   resume progress1.log      (back to active)")
    print("  t=90   create late_burst.log     (late arrival)")
    print("  t=110  delete late_burst.log     (goes missing)")
    print("  t=130  create final_arrival.log  (appears late, runs to end)")
    print()

    # Start persistent writers
    writers: dict[str, LogWriter] = {}
    for cfg in [
        ("progress1.log", "type1", 120, 0.5, 0.02, 0.03),
        ("progress2.log", "type2", 60, 1.0, 0.03, 0.03),
        ("progress3.log", "type3", 30, 2.0, 0.0, 0.03),
    ]:
        w = LogWriter(cfg[0], cfg[1], cfg[2], cfg[3], cfg[4], cfg[5])
        writers[cfg[0]] = w
        w.start()

    # Register persistent writers with scheduler for pause/resume control
    sched = DynamicScheduler(".")
    sched._writers = writers  # share writer registry

    # --- schedule dynamic events ---
    sched.schedule(20, "create", "dynamic_appear.log",
                   fmt_key="type1", total_steps=15, dt_mean=1.0, dt_var=0.1)
    sched.schedule(40, "pause", "progress1.log")
    sched.schedule(65, "delete", "dynamic_appear.log")
    sched.schedule(75, "resume", "progress1.log")
    sched.schedule(90, "create", "late_burst.log",
                   fmt_key="type2", total_steps=10, dt_mean=0.3, dt_var=0.05)
    sched.schedule(110, "delete", "late_burst.log")
    sched.schedule(130, "create", "final_arrival.log",
                   fmt_key="type3", total_steps=20, dt_mean=0.5, dt_var=0.02)

    stop_event = threading.Event()

    # Run scheduler in background
    sched_thread = threading.Thread(
        target=sched.run, args=(stop_event,), daemon=True
    )
    sched_thread.start()

    try:
        print("Press Ctrl+C to stop.\n")
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_event.set()

    sched.stop_all()
    print("All threads stopped.")


if __name__ == "__main__":
    main()
