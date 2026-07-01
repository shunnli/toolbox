clear;
close all;

% Global log level

Logger.set_global_level("debug");

% Logger 1: console output

logger1 = Logger(Level = "debug", Format = "level");

logger1.debug("Processing item %d of %d...", 5, 100);
logger1.info("User %s has logged in", "Alice");
logger1.warning("Disk space low: %0.2fG (%.2g%%) remaining", 4.75, 5.0);
logger1.error("Failed to open file: %s", "data.csv");

logger1.info("Test %.2f%%", pi);
logger1.info("Test %%");

% Logger 2: file output

logger2 = Logger(Level = "info", Format = "timestamp_and_level");
logger2.open_file("tmp.log", Mode = "truncate");

logger2.info("hello");
logger2.debug("hello"); % filtered out (INFO > DEBUG)

logger2.close_file();

% Change global log level

Logger.set_global_level("info");

logger3 = Logger().set_format("timestamp_and_level").set_level("debug");

logger3.debug("this will NOT be logged");
logger3.info("this will be logged");

logger3.set_global_level("debug");

logger3.debug("this will be logged now");

% Change format

logger3.set_format("none");
logger3.debug("this will be logged without timestamp and level");
