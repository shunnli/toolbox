# ProgressTrigger + CounterTrigger + WallTimeTrigger

Small handle classes for deciding when to print progress, save intermediate
results, update plots, or run periodic diagnostics inside long loops.

All trigger classes support chained use such as `trigger.update().every(10)`.

## ProgressTrigger

Triggers actions when progress crosses a percentage threshold (`N` stages).

Example:
```matlab
pgtgr = ProgressTrigger();
tnow = 0;
tend = 2.0;

while tnow < tend
    dt = get_dt();
    dt = min([dt, tend - tnow]);

    % update

    tnow = tnow + dt;
    if pgtgr.update(tnow / tend).stage(5)
        fprintf('Time %.2f, (%.2f%%), triggered (progress)\n', tnow, tnow / tend * 100);
    end
end
```

**API**

| Method / property           | Description                                                                         |
| --------------------------- | ----------------------------------------------------------------------------------- |
| `pgtgr = ProgressTrigger()` | Construct a trigger with progress set to zero.                                      |
| `pgtgr.update(p)`           | Update progress, where `p` must be in `[0, 1]`. Returns the trigger.                |
| `pgtgr.stage(N)`            | Return `true` when progress crossed a new `1/N` boundary since the previous update. |
| `pgtgr.reset()`             | Reset previous and current progress to zero.                                        |
| `pgtgr.lastProgress`        | Previous progress value.                                                            |
| `pgtgr.currentProgress`     | Latest progress value.                                                              |

`stage(5)` triggers when progress crosses 20%, 40%, 60%, 80%, or 100%.

## CounterTrigger

Triggers actions every `N` calls or during the first `N` calls, based on a counter.

Example:
```matlab
tgr = CounterTrigger();

for i = 1:100

    % update

    if tgr.update().every(8)
        fprintf('Iteration %d: triggered (every 8)\n', i);
    end
    if tgr.update().first(10)
        fprintf('Iteration %d: triggered (first 10)\n', i);
    end
end
```

**API**

| Method / property        | Description                                        |
| ------------------------ | -------------------------------------------------- |
| `tgr = CounterTrigger()` | Construct a trigger with counter set to zero.      |
| `tgr.update()`           | Increment the counter by one. Returns the trigger. |
| `tgr.every(N)`           | Return `true` when `counter` is divisible by `N`.  |
| `tgr.first(N)`           | Return `true` while `counter <= N`.                |
| `tgr.reset()`            | Reset counter to zero.                             |
| `tgr.counter`            | Current counter value.                             |

Call `update()` once per loop iteration if you want `every` and `first` to refer
to the same iteration count.

## WallTimeTrigger

Triggers actions when a specified amount of wall-clock time has passed since the last trigger.

Example:
```matlab
wtgr = WallTimeTrigger();
tnow = 0;
tend = 2.0;

while tnow < tend
    dt = get_dt();
    dt = min([dt, tend - tnow]);

    % update

    tnow = tnow + dt;
    if wtgr.update().check(60) % 60s
        fprintf('Wall Time %.2f, triggered\n', wtgr.currentTime);
    end
end
```

**API**

| Method / property          | Description                                                                                                      |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `wtgr = WallTimeTrigger()` | Construct a trigger and start its internal timer.                                                                |
| `wtgr.update()`            | Sample current elapsed wall time. Returns the trigger.                                                           |
| `wtgr.check(dt)`           | Return `true` when at least `dt` seconds elapsed since the last trigger. Resets the last trigger time when true. |
| `wtgr.elapsed()`           | Return the latest sampled elapsed time in seconds.                                                               |
| `wtgr.reset()`             | Restart the timer and clear trigger state.                                                                       |
| `wtgr.currentTime`         | Latest sampled elapsed time in seconds.                                                                          |
| `wtgr.lastTriggerTime`     | Elapsed time at the previous successful trigger.                                                                 |

## Typical usage

```matlab
progress = ProgressTrigger();
counter = CounterTrigger();
walltime = WallTimeTrigger();

for k = 1:nSteps
    % expensive update

    if counter.update().every(50)
        fprintf("iteration %d\n", k);
    end

    if progress.update(k / nSteps).stage(10)
        fprintf("progress %.0f%%\n", 100 * k / nSteps);
    end

    if walltime.update().check(60)
        save_checkpoint();
    end
end
```

## Notes

- These classes decide whether a condition has been crossed; they do not run the
  action themselves.
- `WallTimeTrigger.elapsed()` returns the last sampled value. Call `update()`
  first if you need a fresh wall-clock reading.
