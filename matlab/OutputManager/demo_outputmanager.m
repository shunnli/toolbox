clear;
close all;

root = fileparts(mfilename('fullpath'));
om = OutputManager(fullfile(root, "./outputs"), "matlab-test");

disp("Output base: " + om.base_dir);
disp("Output: " + om.cur_dir);

% Save numerical data
x = linspace(0, 2 * pi, 200);
y = sin(x);

data_file = om.get_file_path('data/sin_wave.mat');
save(data_file, "x", "y");
disp("Save data to: " + data_file);

% Write a log file
log_file = om.get_file_path('logs/log.txt');
fid = fopen(log_file, "w");
fprintf(fid, "Demo started at: %s\n", datetime("now"));
fprintf(fid, "Generated sine-wave data with %d points.\n", numel(x));
fclose(fid);
disp("Write log to: " + log_file);

% Save a figure
figure();
plot(x, y, 'LineWidth', 1.5);
grid('on');
title("Sine Wave Demo");

fig_file = om.get_file_path('figures/figure.png');
exportgraphics(gcf, fig_file, 'Resolution', 600)
disp("Save figure to: " + fig_file);

disp("Demo completed!");
