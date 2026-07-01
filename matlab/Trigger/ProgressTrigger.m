classdef ProgressTrigger < handle
    % PROGRESSTRIGGER - Trigger when progress crosses percentage thresholds.
    %
    % Call update(p) to provide current progress in [0, 1].
    % Then call stage(N) to check whether progress has crossed a 1/N boundary.
    %
    % ProgressTrigger Properties:
    %   lastProgress    - Last recorded progress value
    %
    % ProgressTrigger Methods:
    %   update(p)       - Update current progress
    %   stage(N)        - Returns true if [last, current] crosses a 1/N threshold
    %   reset()         - Resets the internal progress tracker
    %
    % EXAMPLE:
    % pgtgr = ProgressTrigger();
    % tnow = 0;
    % tend = 2.0;
    %
    % while tnow < tend
    %     dt = get_dt();
    %     dt = min([dt, tend - tnow]);
    %
    %     % update
    %
    %     tnow = tnow + dt;
    %     if pgtgr.update(tnow / tend).stage(5)
    %         fprintf('Time %.2f, (%.2f%%), triggered (progress)\n', tnow, tnow / tend * 100);
    %     end
    % end

    properties (SetAccess = private)
        lastProgress = 0 % Previous progress value
        currentProgress = 0 % Latest updated progress
    end

    methods

        function obj = update(obj, p)
            % Update the progress value.
            % p must be in [0, 1].

            arguments
                obj
                p (1, 1) double {mustBeGreaterThanOrEqual(p, 0), mustBeLessThanOrEqual(p, 1)}
            end

            obj.lastProgress = obj.currentProgress;
            obj.currentProgress = p;
        end

        function tf = stage(obj, N)
            % Returns true if any new 1/N stage has been crossed.

            arguments
                obj
                N (1, 1) {mustBePositive, mustBeInteger}
            end

            oldStage = floor(obj.lastProgress * N);
            newStage = floor(obj.currentProgress * N);

            tf = (newStage > oldStage);
        end

        function reset(obj)
            % Reset internal progress tracker to 0.
            obj.lastProgress = 0;
            obj.currentProgress = 0;
        end

    end

end
