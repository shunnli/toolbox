clear;
close all;

%% ===== ColorManager =====

% --- Database mode ---
fprintf('=== ColorManager — database mode ===\n');
cm = ColorManager();
cm.list(4);
cm.select(4, 2);
cm.assign('Algorithm A', 1);
cm.assign('Algorithm B', 2);
cm.assign('Baseline', 3);
cm.assign('Ours', 4);
cm.preview();

% --- Manual mode (RGB) ---
fprintf('\n=== ColorManager — manual mode (RGB matrix) ===\n');
rgb = [0.12 0.47 0.71;   % blue
       0.85 0.65 0.16;   % gold
       0.28 0.63 0.64;   % teal
       0.88 0.31 0.36];  % red
cmRGB = ColorManager(RGB=rgb);
cmRGB.assign('blue', 1).assign('gold', 2).assign('teal', 3).assign('red', 4);

% select() is ignored in manual mode
fprintf('Calling select(4, 2) in manual mode... ');
cmRGB.select(4, 2);
cmRGB.preview();

% get_idx() cycles when index exceeds number of colors
fprintf('Cycling test (4 colors, requesting idx 1..8):\n');
for i = 1:8
    c = cmRGB.get_idx(i);
    fprintf('  idx=%d -> [%.3f, %.3f, %.3f]\n', i, c(1), c(2), c(3));
end

% --- Manual mode (hex) ---
fprintf('\n=== ColorManager — manual mode (hex strings) ===\n');
cmHex = ColorManager(Hex=["#1F77B4", "#DAA628", "#47A1A2", "#E07F86"]);
cmHex.assign('A', 1).assign('B', 2).assign('C', 3).assign('D', 4);
cmHex.preview();

% --- Color cycling: many curves with few colors ---
fprintf('\n=== ColorManager — cycling demo (9 curves, 3 colors) ===\n');
figure('Name', 'ColorManager: cycling', 'Color', 'w'); hold on; box on;
cmCycle = ColorManager(RGB=[0.12 0.47 0.71; 0.88 0.31 0.36; 0.28 0.63 0.64]);
x = linspace(0, 2*pi, 64)';
for i = 1:9
    plot(x, sin(x + i*0.5), 'LineWidth', 1.5, ...
        Color=cmCycle.get_idx(i), DisplayName=sprintf('curve %d', i));
end
legend('Location', 'best');
title('Manual mode: 9 curves, 3 colors — auto-cycling');


%% ===== PlotStyleManager =====

fprintf('\n=== PlotStyleManager ===\n');
psm = PlotStyleManager();
psm.assign('solid',   Marker='o', LineStyle='-',  LineWidth=2,   MarkerFaceColor='auto');
psm.assign('dashed',  Marker='s', LineStyle='--', LineWidth=2,   MarkerFaceColor='auto');
psm.assign('dotted',  Marker='^', LineStyle=':',  LineWidth=1.5);
psm.assign('dashdot', Marker='d', LineStyle='-.', LineWidth=2.5, MarkerSize=10);

% Inspect stored styles
s = psm.get_style('solid');
fprintf('get_style(''solid'') returns: ');
disp(s);


%% ===== Combined: ColorManager + PlotStyleManager =====

fprintf('\n=== Combined usage ===\n');

% Use manual-mode colors (no CSV needed)
cm = ColorManager(RGB=[0.12 0.47 0.71; 0.85 0.65 0.16; 0.28 0.63 0.64; 0.88 0.31 0.36]);
cm.assign('Proposed', 1).assign('Baseline', 2).assign('Oracle', 3).assign('Ablation', 4);

psm.assign('Proposed',  Marker='o', LineStyle='-',  LineWidth=2,   MarkerFaceColor='auto');
psm.assign('Baseline',  Marker='s', LineStyle='--', LineWidth=2,   MarkerFaceColor='auto');
psm.assign('Oracle',    Marker='^', LineStyle=':',  LineWidth=1.5);
psm.assign('Ablation',  Marker='d', LineStyle='-.', LineWidth=2.5, MarkerSize=10);

x = linspace(0, 2*pi, 24)';
names = {'Proposed', 'Baseline', 'Oracle', 'Ablation'};

figure('Name', 'Combined: ColorManager + PlotStyleManager', 'Color', 'w');

subplot(1, 2, 1); hold on; box on;
for i = 1:numel(names)
    n = names{i};
    s = psm.get_style(n);
    plot(x, sin(x + (i-1)*pi/4), s{:}, Color=cm.get_name(n), DisplayName=n);
end
legend('Location', 'best'); title('get\_name + get\_style');

subplot(1, 2, 2); hold on; box on;
for i = 1:numel(names)
    n = names{i};
    s = psm.get_style(n);
    plot(x, cos(x + (i-1)*pi/4), s{:}, Color=cm.get_idx(i), DisplayName=n);
end
legend('Location', 'best'); title('get\_idx + get\_style');

sgtitle('ColorManager + PlotStyleManager', 'FontSize', 14);

fprintf('\nDemo complete.\n');
