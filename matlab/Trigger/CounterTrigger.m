classdef CounterTrigger < handle
    % COUNTERTRIGGER - A simple trigger utility class for loop control.
    %
    % CounterTrigger Properties:
    %   counter     - internal call counter. (Default: 0)
    %
    % CounterTrigger Methods:
    %   update()    - increments the internal counter.
    %   reset()     - resets the internal counter.
    %   first(N)    - returns true for the first N calls.
    %   every(N)    - returns true every N calls.
    %
    % EXAMPLE:
    % tgr = CounterTrigger();
    %
    % for i = 1:100
    %
    %     % update
    %
    %     if tgr.update().every(8)
    %         fprintf('Iteration %d: triggered (every 8)\n', i);
    %     end
    %     if tgr.update().first(10)
    %         fprintf('Iteration %d: triggered (first 10)\n', i);
    %     end
    % end

    properties (SetAccess = private)
        counter = 0 % Internal call counter
    end

    methods

        function obj = update(obj)
            % Increment the internal counter.

            obj.counter = obj.counter + 1;
        end

        function tf = first(obj, N)
            % Returns true for the first N calls, then false

            tf = (obj.counter <= N);
        end

        function tf = every(obj, N)
            % Returns true every N calls.

            tf = (mod(obj.counter, N) == 0);
        end

        function obj = reset(obj)
            % Resets the internal counter to zero.

            obj.counter = 0;
        end

    end

end
