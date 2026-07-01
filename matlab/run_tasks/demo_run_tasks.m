clear;
close all;

fprintf('Demo: run_tasks in serial and parallel modes\n');
fprintf('Each task computes y = i^2 after a random delay.\n');

% Construct tasks
tasks = cell(1, 5);

for i = 1:5
    % Each task is a zero-argument function handle
    % run_tasks treats all tasks as black boxes
    tasks{i} = @() some_heavy_task(i);
end

fprintf('============================================================\n');
fprintf('Serial execution (Verbose = true, default)\n');
fprintf('============================================================\n');

results_serial = run_tasks(tasks, Mode = "serial");

fprintf('============================================================\n');
fprintf('Serial execution (Verbose = false)\n');
fprintf('Note: task-side fprintf is still executed\n');
fprintf('============================================================\n');

results_serial_quiet = run_tasks(tasks, Mode = "serial", Verbose = false);

fprintf('============================================================\n');
fprintf('Parallel execution using parfor\n');
fprintf('Worker outputs may appear unordered\n');
fprintf('============================================================\n');

results_parfor = run_tasks(tasks, Mode = "parfor");

fprintf('============================================================\n');
fprintf('Parallel execution using parfeval\n');
fprintf('Note: task-side stdout is invisible\n');
fprintf('============================================================\n');

results_parfeval = run_tasks(tasks, Mode = "parfeval");

fprintf('============================================================\n');
fprintf('parfeval without thread/worker limits\n');
fprintf('============================================================\n');

results_parfeval2 = run_tasks(tasks, Mode = "parfeval", LimitThreads = false, LimitWorkers = false);

fprintf('============================================================\n');
fprintf('parfeval with MaxWorkers = 2\n');
fprintf('============================================================\n');

results_parfeval3 = run_tasks(tasks, Mode = "parfeval", MaxWorkers = 2);

% Construct tasks WITH DataQueue (worker -> client messaging)

fprintf('============================================================\n');
fprintf('Parallel execution with parallel.pool.DataQueue (non-intrusive)\n');
fprintf('Workers send messages to the client via DataQueue\n');
fprintf('run_tasks is completely unaware of DataQueue\n');
fprintf('============================================================\n');

% Create DataQueue on the client
dq = parallel.pool.DataQueue;

% Register a callback executed on the client
afterEach(dq, @(msg) fprintf('%s\n', msg));

tasks_with_dq = cell(1, 5);

for i = 1:5
    % DataQueue is captured by the task closure
    % run_tasks does NOT know dq exists
    tasks_with_dq{i} = @() some_heavy_task_with_dq(i, dq);
end

results_with_dq_parfeval = run_tasks(tasks_with_dq, Mode = "parfeval");

%% Task definitions

function y = some_heavy_task(i) 
    pause(1 + rand());

    y = i ^ 2;

    % Direct output from worker
    fprintf('[task %d] y = %d.\n', i, y);
end

function y = some_heavy_task_with_dq(i, dq)
    % Send a message to the client 
    send(dq, sprintf('[task %d] started', i));

    pause(1 + rand());

    y = i ^ 2;

    % Send a message to the client  
    send(dq, sprintf('[task %d] finished, y = %d', i, y));
end
