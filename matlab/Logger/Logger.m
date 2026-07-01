classdef Logger < handle
    % LOGGER Lightweight logging utility for MATLAB (handle class)
    %
    % This class provides a simple, single-file logging facility with
    % configurable log levels, output formats, optional file output, and a
    % global log-level threshold shared across all Logger instances.
    %
    % Log Levels: DEBUG < INFO < WARNING < ERROR
    %
    % A log message with level L is emitted if and only if:
    %   L >= max(global_log_level, logger.level)
    %
    % where:
    %   - global_log_level is the global threshold shared by all Logger objects
    %   - logger.level is the per-instance minimum log level
    %
    % Properties:
    %   level   (int)    - Per-instance minimum log level
    %                      DEBUG_NUM = 1, INFO_NUM = 2, WARNING_NUM = 3, ERROR_NUM = 4 (default: INFO)
    %   fileID  (int)    - File identifier for log output (-1 means stdout/stderr)
    %   format  (string) - Log message format
    %
    % Constructor
    %   logger = Logger()
    %   logger = Logger(Level=..., Format=...)
    %
    %   Key-Value Parameters (case-insensitive):
    %       Level  - "debug" | "info" | "warning" | "error"  (default: "info")
    %       Format - "none" | "level" | "timestamp" | "timestamp_and_level" (default: "level")
    %
    % Instance Methods (configuration)
    %   set_level(Level)
    %
    %   set_format(Format)
    %
    %   open_file(FileName)
    %   open_file(FileName, Mode=...)
    %       Open a log file for output.
    %       Mode: "append" (default) or "truncate".
    %
    %   close_file()
    %       Close the currently opened log file, if any.
    %
    % Instance Methods (logging):
    %   debug(fmt, ...)
    %   info(fmt, ...)
    %   warning(fmt, ...)
    %   error(fmt, ...)
    %
    % Each method logs a formatted message at the corresponding log level,
    % subject to the global and per-instance log-level thresholds.
    %
    % Messages with level WARNING or ERROR are written to stderr when no log
    % file is open; lower levels are written to stdout.
    %
    % Static Methods (global log level):
    %   get_global_level()
    %       Get the current global log level.
    %
    %   set_global_level(Level)
    %       Set the global log level.
    %       Level is case-insensitive and defaults to "debug" when omitted.
    %
    % Example:
    %   Logger.set_global_level("info");
    %   logger = Logger(Level="debug", Format="timestamp_and_level");
    %   logger.open_file("app.log", Mode="truncate");
    %
    %   logger.debug("This is a debug message");
    %   logger.info("User %s logged in", "Alice");
    %   logger.warning("Disk space low: %0.2fG (%.2g%%) remaining", 4.75, 5.0);
    %   logger.error("Failed to open file: %s", "data.csv");
    %
    %   logger.close_file();

    properties (Constant)
        DEBUG_NUM = 1;
        INFO_NUM = 2;
        WARNING_NUM = 3;
        ERROR_NUM = 4;
    end

    properties (SetAccess = private)
        level % Minimum log level
        fileID = -1; % File handle (-1 = no file)
        format % Log message format
    end

    methods

        function obj = Logger(opts)
            % Logger constructor
            %
            % Key-Value Parameters: (case-insensitive)
            %   Level  - Minimum log level: "debug" < "info" < "warning" < "error". (default: "INFO")
            %   Format - Log format: "none", "level", "timestamp", "timestamp_and_level". (default: "level")
            %
            % EXAMPLE:
            %   logger1 = Logger();
            %   logger2 = Logger(Level = "debug", Format = "none");

            arguments
                opts.Level (1, 1) string {mustBeLogLevel(opts.Level)} = "info"

                opts.Format (1, 1) string {mustBeLogFormat(opts.Format)} = "level"
            end

            obj.level = levelStr2int(opts.Level);
            obj.format = lower(opts.Format);
        end

        function obj = set_level(obj, Level)
            % Set the log level.
            %
            % Supported levels (case-insensitive):
            %   "debug" < "info" < "warning" < "error"
            %
            % EXAMPLE:
            %   obj.set_level("debug");
            %   obj.set_level("INFO");

            arguments
                obj
                Level (1, 1) string {mustBeLogLevel(Level)}
            end

            obj.level = levelStr2int(Level);
        end

        function obj = set_format(obj, format)
            % Set the log format.
            %
            % Supported formats (case-insensitive):
            %   "none", "level", "timestamp", "timestamp_and_level"
            %
            % EXAMPLE:
            %   obj.set_format("timestamp_and_level");

            arguments
                obj
                format (1, 1) string {mustBeLogFormat(format)}
            end

            obj.format = lower(format);
        end

        function obj = open_file(obj, fileName, opts)
            % Open a log file. (default: append)
            %
            % EXAMPLE:
            %   obj.open_file("log.txt")
            %   obj.open_file("log.txt", Mode="truncate")

            arguments
                obj
                fileName (1, 1) string
                opts.Mode (1, 1) string {mustBeFileOpenMode(opts.Mode)} = "append"
            end

            mode = lower(opts.Mode);

            obj.close_file();

            switch mode
                case "append", fopenMode = 'a';
                case "truncate", fopenMode = 'w';
            end

            [fid, msg] = fopen(fileName, fopenMode);

            if fid == -1
                error("Logger:FileError", "Failed to open file '%s': %s", fileName, msg);
            end

            obj.fileID = fid;

            fprintf(obj.fileID, "[%s] LOG FILE INITIALIZED (level=%s, global_level=%s)\n", timestamp(), int2levelStr(obj.level), int2levelStr(Logger.get_global_level()));
        end

        function obj = close_file(obj)
            % Close the log file

            if obj.fileID == -1
                return;
            end

            fprintf(obj.fileID, "[%s] LOG FILE CLOSED\n", timestamp());
            fclose(obj.fileID);
            obj.fileID = -1;
        end

        function debug(obj, fmt, varargin)
            obj.log(Logger.DEBUG_NUM, fmt, varargin{:});
        end

        function info(obj, fmt, varargin)
            obj.log(Logger.INFO_NUM, fmt, varargin{:});

        end

        function warning(obj, fmt, varargin)
            obj.log(Logger.WARNING_NUM, fmt, varargin{:});

        end

        function error(obj, fmt, varargin)
            obj.log(Logger.ERROR_NUM, fmt, varargin{:});
        end

        function delete(obj)
            obj.close_file();
        end

    end

    methods (Static)

        function level = get_global_level()
            % Get global log level. (DEBUG = 1, INFO = 2, WARNING = 3, ERROR = 4)

            level = Logger.global_level_accessor();
        end

        function set_global_level(Level)
            % Set global log level.
            %
            % Supported levels (case-insensitive):
            %   "debug" < "info" < "warning" < "error"
            %
            % EXAMPLE:
            %   Logger.set_global_level("INFO");
            %   Logger.set_global_level(); % reset to default (DEBUG)

            arguments
                Level (1, 1) string {mustBeLogLevel(Level)} = "debug"
            end

            Logger.global_level_accessor(levelStr2int(Level));
        end

    end

    methods (Access = private)

        function log(obj, level, fmt, varargin)
            % log only if level >= max(global_level, obj.level)
            if level < max(Logger.get_global_level(), obj.level)
                return;
            end

            msg = sprintf(fmt, varargin{:});
            msg = strrep(msg, '%', '%%');

            switch obj.format
                case "none", logStr = sprintf("%s\n", msg);
                case "level", logStr = sprintf("[%s] %s\n", int2levelStr(level), msg);
                case "timestamp", logStr = sprintf("[%s] %s\n", timestamp(), msg);
                case "timestamp_and_level", logStr = sprintf("[%s] [%s] %s\n", timestamp(), int2levelStr(level), msg);
            end

            if obj.fileID ~= -1
                fprintf(obj.fileID, logStr);
            else

                if level >= Logger.WARNING_NUM
                    fprintf(2, logStr); % stderr
                else
                    fprintf(1, logStr); % stdout
                end

            end

        end

    end

    methods (Static, Access = private)

        function level = global_level_accessor(newLevel)
            persistent global_level

            if isempty(global_level)
                global_level = Logger.DEBUG_NUM;
            end

            if nargin > 0
                global_level = newLevel;
            end

            level = global_level;
        end

    end

end

function levelStr = int2levelStr(level)

    switch level
        case Logger.DEBUG_NUM, levelStr = "debug";
        case Logger.INFO_NUM, levelStr = "info";
        case Logger.WARNING_NUM, levelStr = "warning";
        case Logger.ERROR_NUM, levelStr = "error";
        otherwise , levelStr = "unknown";
    end

end

function level = levelStr2int(levelStr)

    switch lower(levelStr)
        case "debug", level = Logger.DEBUG_NUM;
        case "info", level = Logger.INFO_NUM;
        case "warning", level = Logger.WARNING_NUM;
        case "error", level = Logger.ERROR_NUM;
        otherwise , error("levelStr2int:InvalidLevel", "Level must be one of: debug, info, warning, error.");
    end

end

function mustBeLogLevel(x)
    levels = ["debug", "info", "warning", "error"];

    if ~ismember(lower(x), levels)
        error("mustBeLogLevel:InvalidLevel", "Level must be one of: %s.", strjoin(levels, ", "));
    end

end

function mustBeLogFormat(x)
    formats = ["none", "level", "timestamp", "timestamp_and_level"];

    if ~ismember(lower(x), formats)
        error("mustBeLogFormat:InvalidFormat", ...
            "Format must be one of: %s.", strjoin(formats, ", "));
    end

end

function mustBeFileOpenMode(x)
    modes = ["append", "truncate"];

    if ~ismember(lower(x), modes)
        error("mustBeFileOpenMode:InvalidOpenMode", "Mode must be one of: %s.", strjoin(modes, ", "));
    end

end

function ts = timestamp()
    % Example: 2025-01-02 08:00:00.000
    ts = datetime("now", "Format", "yyyy-MM-dd HH:mm:ss.SSS");
end
