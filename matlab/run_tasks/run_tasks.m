function results = run_tasks(tasks, opts)
    % RUN_TASKS Execute a list of zero-argument tasks.
    %
    %   RESULTS = RUN_TASKS(TASKS) executes each task handle in TASKS and returns
    %   their outputs in the same order. Each task must be a function handle that
    %   takes no input arguments and returns exactly one output.
    %
    % Name-Value options:
    %   "Mode" :
    %       Execution mode (default: "serial")
    %         "serial"   - Execute tasks sequentially in the client MATLAB.
    %         "for"      - Alias for "serial".
    %         "parfor"   - Execute tasks in parallel using a parfor loop.
    %                      Completion is only observable after the loop finishes.
    %         "parfeval" - Execute tasks asynchronously using parfeval.
    %                      Tasks are fetched as they complete; order is ignored.
    %         "debug"    - Execute tasks sequentially in the client MATLAB
    %                      with debugging enabled.
    %
    %                      In debug mode, "dbstop if error" is temporarily
    %                      enabled and all internal error catching is
    %                      disabled, so execution stops exactly at the error
    %                      location.
    %
    %                      Notes:
    %                        - Debug mode is strictly serial.
    %                        - Debug status must be empty in all non-debug
    %                          modes ("serial", "parfor", "parfeval").
    %                        - "dbstop if error" is enabled automatically on entry
    %                          and cleared automatically on exit.
    %
    %   "LimitWorkers" : (valid in "parfor" and "parfeval" modes)
    %       true  - Limit the number of workers based on task count and hardware. (default)
    %       false - Use the existing parallel pool as-is.
    %
    %   "LimitThreads" : (valid in "parfor" and "parfeval" modes)
    %       true  - Limit computational threads per worker to avoid oversubscription. (default)
    %       false - Leave thread settings unchanged.
    %
    %   "MaxWorkers" : (valid in "parfor" and "parfeval" modes)
    %       N     - Limit the number of workers to less or equal to N. (default: 20)
    %
    %   "StopOnFirstError" : (valid in all modes except "debug")
    %       true  - Abort execution immediately when the first task error occurs. (default)
    %       false - Attempt to execute all tasks, then rethrow the first error.
    %
    %   "Verbose" :
    %       true  - Print messages. (default)
    %       false - Suppress most messages.
    %
    % Environment variables:
    %   RUN_TASKS_MODE - Overrides the "Mode" parameter. Valid values are
    %                       "serial", "for", "parfor", "parfeval", "debug".
    %                       Takes precedence over the "Mode" name-value argument.
    %   RUN_TASKS_PROFILE - Set to "on", "1", or "true" to enable profiling
    %                       and auto-save an HTML report. A warning is
    %                       emitted when the variable takes effect. If
    %                       profiling is already active externally, this
    %                       variable is silently ignored.
    %
    % Error handling:
    %   - In "serial", "parfor", and "parfeval" modes, all task errors are caught
    %     and collected.
    %   - In "debug" mode, errors are NOT caught; execution stops immediately
    %     at the error site under "dbstop if error".
    %   - If multiple errors occur, detailed reports are written to a
    %     timestamped log file.
    %   - If any error occurred, the first error is rethrown.

    arguments
        tasks cell
        opts.Mode (1, 1) string {mustBeMember(opts.Mode, ["serial", "for", "parfor", "parfeval", "debug"])} = "serial"
        opts.LimitWorkers (1, 1) logical = true
        opts.LimitThreads (1, 1) logical = true
        opts.MaxWorkers (1, 1) double {mustBeInteger, mustBePositive} = 20
        opts.StopOnFirstError (1, 1) logical = true
        opts.Verbose (1, 1) logical = true
    end

    % Check for environment variable override
    envMode = getenv('RUN_TASKS_MODE');

    if ~isempty(envMode)
        envMode = lower(strtrim(envMode));
        validModes = ["serial", "for", "parfor", "parfeval", "debug"];

        if ~ismember(envMode, validModes)
            warning('run_tasks:invalid_env_mode', ...
                '[run_tasks] Environment variable RUN_TASKS_MODE="%s" is invalid. Valid values: %s. Using Mode="%s".', ...
                envMode, strjoin(validModes, ', '), opts.Mode);
        else

            if ~strcmpi(envMode, opts.Mode)
                warning('run_tasks:env_mode_override', ...
                    '[run_tasks] Environment variable RUN_TASKS_MODE="%s" overrides Mode="%s".', ...
                    envMode, opts.Mode);
            end

            opts.Mode = envMode;
        end

    end

    if opts.Mode == "for"
        opts.Mode = "serial";
    end

    % Check for environment variable override for Profile
    envProfile = getenv('RUN_TASKS_PROFILE');
    profileStarted = false;

    if ~isempty(envProfile)
        envProfile = lower(strtrim(envProfile));

        if ismember(envProfile, ["on", "1", "true"])
            ps = profile('status');

            if strcmp(ps.ProfilerStatus, 'off')
                profileStarted = true;
                warning('run_tasks:env_profile_override', ...
                    '[run_tasks] Environment variable RUN_TASKS_PROFILE="%s" enables profiling.', ...
                    envProfile);
            end

        elseif ~ismember(envProfile, ["off", "0", "false"])
            warning('run_tasks:invalid_env_profile', ...
                '[run_tasks] Environment variable RUN_TASKS_PROFILE="%s" is invalid. Valid values: on, off, 1, 0, true, false.', ...
                envProfile);
        end

    end

    origSize = size(tasks);
    tasksFlat = tasks(:);
    nTasks = numel(tasksFlat);
    resultsFlat = cell(nTasks, 1);
    errors = cell(nTasks, 1);
    errorCount = 0;

    StopOnFirstError = opts.StopOnFirstError;
    Verbose = opts.Verbose;
    isDebug = (opts.Mode == "debug");

    check_dbstatus(opts.Mode);

    if ~isDebug && nTasks == 1 && opts.Mode ~= "serial"
        warning('run_tasks:single_task_force_serial', '[run_tasks] Only one task detected. Switch to serial mode.');
        opts.Mode = "serial";
    end

    if ~isDebug && nTasks > 5 && opts.Mode == "serial"
        warning('run_tasks:serial_many_tasks', '[run_tasks] Running %d tasks in serial mode. Consider using parallel mode for performance.', nTasks);
    end

    if opts.Mode == "parfor" || opts.Mode == "parfeval"
        configure_parallel_pool_workers(nTasks, opts.LimitWorkers, opts.MaxWorkers, Verbose);
        cleanupThreads = configure_parallel_pool_threads(nTasks, opts.LimitThreads, opts.MaxWorkers, Verbose); %#ok<NASGU>
    else
        % display physical cores and maxNumCompThreads even in serial mode
        [nPhys, ~] = decide_worker_count(nTasks, opts.MaxWorkers);

        if Verbose
            fprintf('[run_tasks] Detected %d physical cores. (Client maxNumCompThreads: %d)\n', nPhys, maxNumCompThreads());
        end

    end

    if profileStarted
        profile('on');
        cleanupProfile = onCleanup(@() finalize_profile(opts.Verbose));
    end

    tStart = tic();
    fprintf('[run_tasks] Running %d tasks in %s mode.\n', nTasks, opts.Mode);

    switch opts.Mode
        case "serial"

            for idx = 1:nTasks

                try
                    resultsFlat{idx} = tasksFlat{idx}();

                    if Verbose
                        fprintf('[run_tasks] Task %d completed. (%d/%d)\n', idx, idx, nTasks);
                    end

                catch ME
                    errors{errorCount + 1} = ME;
                    errorCount = errorCount + 1;
                    fprintf('[run_tasks] Task %d failed: %s\n', idx, ME.message);

                    if StopOnFirstError
                        rethrow(ME);
                    end

                end

            end

        case "parfor"

            tmpErrors = cell(nTasks, 1);

            parfor idx = 1:nTasks

                try
                    resultsFlat{idx} = tasksFlat{idx}();
                catch ME
                    tmpErrors{idx} = ME;
                    fprintf('[run_tasks] Task %d failed: %s\n', idx, tmpErrors{idx}.message);

                    if StopOnFirstError
                        rethrow(ME);
                    end

                end

            end

            for idx = 1:nTasks

                if ~isempty(tmpErrors{idx})
                    errors{errorCount + 1} = tmpErrors{idx};
                    errorCount = errorCount + 1;
                end

            end

        case "parfeval"

            if Verbose
                fprintf("[run_tasks] Note: worker's stdout is not forwarded in parfeval mode.\n");
                fprintf("[run_tasks] WARNING: interactive interruption (GUI/Ctrl+C) is not supported in parfeval mode.\n");
            end

            futures(nTasks) = parallel.FevalFuture;

            for idx = 1:nTasks
                futures(idx) = parfeval(tasksFlat{idx}, 1);
            end

            nCompleted = 0;

            while nCompleted < nTasks

                try
                    [idx, val] = fetchNext(futures);
                    resultsFlat{idx} = val;

                    if Verbose
                        fprintf('[run_tasks] Task %d completed. (%d/%d)\n', idx, nCompleted + 1, nTasks);
                    end

                catch ME
                    errors{errorCount + 1} = ME;
                    errorCount = errorCount + 1;
                    fprintf('[run_tasks] Some task failed: %s\n', ME.message);

                    if StopOnFirstError
                        cancel(futures);
                        rethrow(ME);
                    end

                end

                nCompleted = nCompleted + 1;
            end

        case "debug"

            fprintf('[run_tasks] Debug mode: enable "dbstop if error". (auto cleanup)\n');
            dbstop('if', 'error');
            cleanupDebug = onCleanup(@() dbclear('if', 'error'));

            for idx = 1:nTasks

                resultsFlat{idx} = tasksFlat{idx}();

                if Verbose
                    fprintf('[run_tasks] Task %d completed. (%d/%d)\n', idx, idx, nTasks);
                end

            end

        otherwise
            error('run_tasks:unknown_mode', '[run_tasks] Unknown mode: %s', opts.Mode);
    end

    elapsed = toc(tStart);

    if errorCount == 0
        fprintf('[run_tasks] All %d tasks completed successfully. (Elapsed time: %s)\n', nTasks, format_elapsed_time(elapsed));
    else
        fprintf('[run_tasks] All %d tasks finished (%d failed). (Elapsed time: %s)\n', nTasks, errorCount, format_elapsed_time(elapsed));

        errors = errors(1:errorCount);

        if errorCount > 1
            log_errors(errors);
        end

        rethrow(errors{1});
    end

    results = reshape(resultsFlat, origSize);
end

function log_errors(errors)
    ts = datetime("now", "Format", "yyyyMMdd-HHmmss");
    logfile = fullfile(pwd(), ['run_tasks_errors_', char(ts), '.log']);

    fid = fopen(logfile, 'w');

    for k = 1:numel(errors)
        ME = errors{k};
        fprintf(fid, '[run_tasks] Error %d:\n', k);
        fprintf(fid, '%s\n\n', ME.getReport('extended', 'hyperlinks', 'off'));
    end

    fclose(fid);

    fprintf('[run_tasks] %d error(s) occurred. Details written to: %s\n', numel(errors), logfile);

end

function configure_parallel_pool_workers(nTasks, LimitWorkers, MaxWorkers, Verbose)

    pool = gcp('nocreate');

    if LimitWorkers
        [nPhys, nWorkers] = decide_worker_count(nTasks, MaxWorkers);

        if Verbose
            fprintf('[run_tasks] Detected %d physical cores, using %d workers for %d tasks.\n', nPhys, nWorkers, nTasks);
        end

        if isempty(pool)

            if Verbose
                fprintf('[run_tasks] Starting parpool with %d workers.\n', nWorkers);
            end

            parpool('local', nWorkers);
        elseif pool.NumWorkers ~= nWorkers

            if Verbose
                fprintf('[run_tasks] Rebuilding parpool with %d -> %d workers.\n', pool.NumWorkers, nWorkers);
            end

            delete(pool);
            parpool('local', nWorkers);
        else

            if Verbose
                fprintf('[run_tasks] Reusing existing parpool with %d workers.\n', pool.NumWorkers);
            end

        end

    else
        % Do not limit workers
        if isempty(pool)

            if Verbose
                fprintf('[run_tasks] Starting parpool with default profile settings.\n');
            end

            parpool('local');
        else

            if Verbose
                fprintf('[run_tasks] Reusing existing parpool with %d workers.\n', pool.NumWorkers);
            end

        end

    end

end

function cleanupThreads = configure_parallel_pool_threads(nTasks, LimitThreads, MaxWorkers, Verbose)

    [nPhys, nWorkers] = decide_worker_count(nTasks, MaxWorkers);

    % run on workers
    spmd
        tmpThreads = maxNumCompThreads;
    end

    threads = [tmpThreads{:}];

    if numel(unique(threads)) > 1
        warning('run_tasks:thread_inconsistent_workers', '[run_tasks] Inconsistent maxNumCompThreads across workers: %s', mat2str(threads));
    end

    oldThreads = threads(1);

    % run on workers
    cleanupThreads = onCleanup(@() restore_worker_threads(oldThreads));

    if LimitThreads
        threadsPerWorker = max(1, floor(nPhys / nWorkers));

        if threadsPerWorker ~= oldThreads

            if Verbose
                fprintf('[run_tasks] Set worker maxNumCompThreads: %d -> %d.\n', oldThreads, threadsPerWorker);
            end

            % run on workers
            spmd
                maxNumCompThreads(threadsPerWorker);
            end

        else

            if Verbose
                fprintf('[run_tasks] Worker maxNumCompThreads unchanged: %d.\n', oldThreads);
            end

        end

    else

        if Verbose
            fprintf('[run_tasks] Worker maxNumCompThreads: %d.\n', oldThreads);
        end

    end

    if ~LimitThreads && nTasks < nPhys && nWorkers * 2 <= nPhys && all(threads == 1)
        warning('run_tasks:underutilized_cpu', ...
            ['[run_tasks] All %d workers are limited to maxNumCompThreads = 1, ' ...
             'while %d tasks are running on a machine with %d physical cores. ' ...
         'This configuration may underutilize available CPU resources.'], ...
            nWorkers, nTasks, nPhys);
    end

end

function [nPhys, nWorkers] = decide_worker_count(nTasks, MaxWorkers)
    % Physical core count
    nPhys = feature('numcores');

    if nPhys <= 8
        % typical laptop
        preferWorkers = 4;
    elseif nPhys <= 16
        preferWorkers = 6;
    else
        % server-class machine
        preferWorkers = 8;
    end

    nWorkers = min([preferWorkers, nPhys, nTasks, MaxWorkers]);

    if nWorkers > 1 && mod(nWorkers, 2) == 1
        nWorkers = nWorkers - 1;
    end

    nWorkers = max(1, nWorkers);
end

function restore_worker_threads(oldThreads)
    pool = gcp('nocreate');

    if isempty(pool)
        return;
    end

    spmd
        maxNumCompThreads(oldThreads);
    end

end

function s = format_elapsed_time(t)
    % t : elapsed time in seconds (double)
    % s : formatted string, e.g. "12.03 ms", "2.45 s", "1.32 min", "3.01 h"

    if t < 1
        s = sprintf('%.2f ms', t * 1e3);
    elseif t < 60
        s = sprintf('%.2f s', t);
    elseif t < 3600
        s = sprintf('%.2f min', t / 60);
    else
        s = sprintf('%.2f h', t / 3600);
    end

end

function finalize_profile(Verbose)
    ps = profile('status');

    if strcmp(ps.ProfilerStatus, 'on')
        ts = datetime("now", "Format", "yyyyMMdd-HHmmss");
        dirname = sprintf('profile_results_%s', char(ts));
        profsave(profile('info'), dirname);

        if Verbose
            fprintf('[run_tasks] Profile report saved to: %s/\n', dirname);
        end

        profile('off');
    end

end

function check_dbstatus(mode)

    if mode == "debug"
        fprintf('[run_tasks] Debug status:\n');
        dbstatus();
    else
        % assert no dbstatus
        s = dbstatus();

        if ~isempty(s)
            error('run_tasks:debug_not_in_debug_mode', ['[run_tasks] dbstatus is non-empty, but mode "%s" was requested.\n' ...
                      'Disable "dbstop if error" and all breakpoints or switch to Mode="debug".'], mode);
        end

    end

end
