classdef WallTimeTrigger < handle
    % WALLTIMETRIGGER - Trigger when wall time exceeds a given interval.
    %
    % Call update() to sample the current wall time.
    % Then call check(dt) to test whether dt seconds have elapsed
    % since the last trigger.
    %
    % WallTimeTrigger Properties:
    %   lastTriggerTime    - Wall time at last trigger (seconds)
    %   currentTime        - Latest sampled wall time (seconds)
    %
    % WallTimeTrigger Methods:
    %   update()           - Update current wall time
    %   check(dt)          - Returns true if elapsed time >= dt seconds
    %   reset()            - Resets internal timer and trigger state
    %   elapsed()          - Returns total elapsed wall time
    %
    % EXAMPLE:
    % wtgr = WallTimeTrigger();
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
    %     if wtgr.update().check(60) % 60s
    %         fprintf('Wall Time %.2f, triggered\n', wtgr.currentTime);
    %     end
    % end

    properties (SetAccess = private)
        startTime % tic handle of start
        lastTriggerTime = 0 % time (s) since start of last trigger
        currentTime = 0 % current time (s) since start
    end

    methods

        function obj = WallTimeTrigger()
            % Construct a wall-time trigger

            obj.startTime = tic();
        end

        function obj = update(obj)
            % Update current wall time

            obj.currentTime = toc(obj.startTime);
        end

        function tf = check(obj, dt)
            % Returns true if elapsed time since last trigger time >= dt
            %
            %   dt is specified in seconds.

            arguments
                obj
                dt (1, 1) double {mustBePositive}
            end

            tf = (obj.currentTime - obj.lastTriggerTime) >= dt;

            if tf
                obj.lastTriggerTime = obj.currentTime;
            end

        end

        function reset(obj)
            % Reset trigger timer

            obj.startTime = tic();
            obj.lastTriggerTime = 0;
            obj.currentTime = 0;
        end

        function t = elapsed(obj)
            % Return total elapsed wall time in seconds

            t = obj.currentTime;
        end

    end

end
