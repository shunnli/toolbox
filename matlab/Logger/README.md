# Logger

A simple logging class for MATLAB.

`Logger` is a single-file handle class for scripts and numerical experiments
that need lightweight status output without introducing a larger logging
framework.

## Features

- Four log levels: `debug`, `info`, `warning`, `error`
- Per-instance log level
- Global log-level threshold shared by all logger instances
- Configurable message format
- Optional file output in append or truncate mode
- Automatic file close on object deletion
- Warnings and errors go to `stderr` when no log file is open

## Quick start

```matlab
Logger.set_global_level("info");
logger = Logger(Level="debug", Format="timestamp_and_level");
logger.open_file("app.log", Mode="truncate");

logger.debug("This is a debug message");
logger.info("User %s logged in", "Alice");
logger.warning("Disk space low: %0.2fG (%.2g%%) remaining", 4.75, 5.0);
logger.error("Failed to open file: %s", "data.csv");
logger.close_file();
```

## Construction

```matlab
logger = Logger();
logger = Logger(Level="debug", Format="timestamp_and_level");
```

| Option   | Default   | Description                 |
| -------- | --------- | --------------------------- |
| `Level`  | `"info"`  | Per-instance minimum level. |
| `Format` | `"level"` | Message format.             |

Supported levels:

```text
debug < info < warning < error
```

A message is emitted only when its level is greater than or equal to both the
global threshold and the instance threshold.

## Formats

| Format                  | Example                                    |
| ----------------------- | ------------------------------------------ |
| `"none"`                | `message`                                  |
| `"level"`               | `[info] message`                           |
| `"timestamp"`           | `[2026-07-01 12:00:00.000] message`        |
| `"timestamp_and_level"` | `[2026-07-01 12:00:00.000] [info] message` |

## API

| Method                                        | Description                                                              |
| --------------------------------------------- | ------------------------------------------------------------------------ |
| `Logger.set_global_level(Level)`              | Set the shared global threshold. Omitted `Level` resets it to `"debug"`. |
| `Logger.get_global_level()`                   | Return the numeric global level.                                         |
| `logger.set_level(Level)`                     | Update the instance threshold.                                           |
| `logger.set_format(Format)`                   | Update message formatting.                                               |
| `logger.open_file(FileName)`                  | Append logs to a file.                                                   |
| `logger.open_file(FileName, Mode="truncate")` | Open a file and discard old contents.                                    |
| `logger.close_file()`                         | Close the active log file, if any.                                       |
| `logger.debug(fmt, ...)`                      | Log a debug message using `sprintf` formatting.                          |
| `logger.info(fmt, ...)`                       | Log an info message using `sprintf` formatting.                          |
| `logger.warning(fmt, ...)`                    | Log a warning message using `sprintf` formatting.                        |
| `logger.error(fmt, ...)`                      | Log an error message using `sprintf` formatting.                         |

## File output

Opening a file redirects all levels to that file. Calling `open_file` again
closes the previous file first.

```matlab
logger.open_file("run.log");                  % append
logger.open_file("run.log", Mode="truncate"); % overwrite
logger.close_file();
```

## Notes

- This class logs messages; `logger.error(...)` does not throw a MATLAB
  exception.
- Message formatting uses `sprintf`, so percent signs in literal messages should
  be escaped as `%%`.
- `Logger` is a handle class. Passing it to functions shares the same logger
  object.
