clear;
close all;

tgr = CounterTrigger();

disp('--- CounterTrigger.first ---');

for i = 1:30

    if tgr.update().first(5)
        fprintf('Iteration %d: triggered (CounterTrigger.first 5)\n', i);
    end

end

tgr.reset();

disp('--- CounterTrigger.every ---');

for i = 1:30

    if tgr.update().every(8)
        fprintf('Iteration %d: triggered (CounterTrigger.every 8)\n', i);
    end

end

disp('--- ProgressTrigger.stage ---');

pgtgr = ProgressTrigger();
tnow = 0;
tend = 2.0;

while tnow < tend
    dt = 0.1 + max(rand(1) * 0.02, 0);
    dt = min([dt, tend - tnow]);

    % update

    tnow = tnow + dt;

    if pgtgr.update(tnow / tend).stage(5)
        fprintf('Time %.2f, (%.2f%%), triggered (ProgressTrigger)\n', tnow, tnow / tend * 100);
    end

end

disp('--- WallTimeTrigger.check ---');

wtgr = WallTimeTrigger();
tnow = 0;
tend = 1;

while tnow < tend
    dt = 0.02;
    dt = min([dt, tend - tnow]);

    % update
    pause(0.3);

    tnow = tnow + dt;

    if wtgr.update().check(5) % 5s
        fprintf('Wall Time %.2f (s), triggered (WallTimeTrigger)\n', wtgr.currentTime);
    end

end
