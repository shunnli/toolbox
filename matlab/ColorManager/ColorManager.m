classdef ColorManager < handle
    %COLORMANAGER Scientific plotting color manager for MATLAB.
    %
    %   cm = ColorManager()                    % auto-locate colors.csv / colors.txt
    %   cm = ColorManager(Path='file')         % specify database path
    %   cm = ColorManager(RGB=rgb)             % manual mode: Nx3 RGB matrix
    %   cm = ColorManager(Hex=["#FF0000",...]) % manual mode: hex string array
    %   cm = ColorManager(Strict=true)         % strict mode: errors on misuse
    %
    %   cm.list()                    % list all palettes
    %   cm.list(nColors)            % list palettes with >= nColors
    %   cm.select(nColors, rank)    % select the rank-th palette matching nColors
    %   cm.preview()                % preview current palette
    %   cm.preview(nColors, rank)   % preview the rank-th palette matching nColors
    %   cm.browse()                 % browse all palettes with navigation controls
    %   cm.browse(nColors)          % browse palettes with >= nColors colors
    %   cm.assign('name', idx)      % bind name to color index
    %   c = cm.get_name('name')     % get color by assigned name
    %   c = cm.get_idx(idx)         % get color by index
    %
    %   By default strict mode is off: invalid operations emit warnings
    %   and fall back to safe defaults so plotting always succeeds.
    %   Fallback colors come from MATLAB's default axes color order.
    %   select() and assign() return obj for chaining.
    %
    %   In manual mode (colors passed directly): select() is ignored,
    %   get_idx() cycles when index exceeds the number of colors,
    %   and no CSV file is ever loaded.
    %
    %   Example (database):
    %     cm = ColorManager();
    %     cm.list(4);
    %     cm.select(4, 3).assign('proposed', 1).assign('baseline', 2);
    %     figure; hold on;
    %     plot(x1, y1, Color=cm.get_name('proposed'), LineWidth=2);
    %     plot(x2, y2, Color=cm.get_name('baseline'), LineWidth=2);
    %     legend('proposed', 'baseline');
    %
    %   Example (manual mode, no CSV needed):
    %     cm = ColorManager(Hex=["#1F77B4","#DAA628","#47A1A2","#E07F86"]);
    %     cm.assign('proposed', 1).assign('baseline', 2);
    %     cm = ColorManager(RGB=[0.12 0.47 0.71; 0.85 0.65 0.16; 0.28 0.63 0.64]);

    properties
        strict (1, 1) logical = false % strict mode: errors instead of warnings
        quiet (1, 1) logical = false % quiet mode: suppress load/select messages
    end

    properties (SetAccess = private)
        palettes % all palettes (cell array of Nx3 RGB)
        nPalettes % total number of palettes
        currentIdx % index of selected palette
        currentColors % current palette (Nx3 RGB)
        assignments % containers.Map: name -> color index
    end

    methods

        function obj = ColorManager(opts)
            % Constructor.
            %   ColorManager()               auto-locate colors.csv / colors.txt
            %   ColorManager(Path=...)        database mode with file path
            %   ColorManager(RGB=...)         manual mode: Nx3 RGB matrix
            %   ColorManager(Hex=...)         manual mode: hex string array
            arguments
                opts.Path (1, 1) string = ""
                opts.RGB (:, 3) double = zeros(0, 3)
                opts.Hex (1, :) string = ""
                opts.Strict (1, 1) logical = false
                opts.Quiet (1, 1) logical = false
            end

            % Mutual exclusion: at most one of Path, RGB, Hex
            nSources = (strlength(opts.Path) > 0) ...
                + (size(opts.RGB, 1) > 0) ...
                + ~(isscalar(opts.Hex) && strlength(opts.Hex) == 0);

            if nSources > 1
                error('ColorManager:mutualExclusive', ...
                'Path, RGB, and Hex are mutually exclusive. Provide at most one.');
            end

            obj.strict = opts.Strict;
            obj.quiet = opts.Quiet;
            obj.assignments = containers.Map();
            obj.currentIdx = 0;

            if size(opts.RGB, 1) > 0
                obj.initManual_(opts.RGB);
            elseif ~(isscalar(opts.Hex) && strlength(opts.Hex) == 0)
                obj.initManual_(obj.parseHex_(opts.Hex));
            elseif strlength(opts.Path) > 0
                obj.loadDatabase_(opts.Path);
            else
                obj.loadDatabase_("");
            end

        end

        function list(obj, nColors)
            % List palettes. Optionally filter to those with >= nColors colors.
            arguments
                obj
                nColors (1, 1) double {mustBeNonnegative, mustBeInteger} = 0
            end

            if nColors == 0
                indices = 1:obj.nPalettes;
            else
                indices = obj.filterByNColors_(nColors);
            end

            if nColors > 0
                fprintf('Palettes with >= %d colors (%d total):\n', nColors, numel(indices));
                fprintf('%-5s  %-6s  %-7s  %s\n', 'Rank', 'Idx', 'NColors', 'Hex sample');
            else
                fprintf('%-6s  %-7s  %s\n', 'Index', 'NColors', 'Hex sample');
            end

            fprintf('%s\n', repmat('-', 1, 78));

            for r = 1:numel(indices)
                i = indices(r);
                c = obj.palettes{i};
                n = size(c, 1);
                hexes = obj.rgb2hex_(c(1:min(5, n), :));

                if nColors > 0
                    fprintf('%-5d  %-6d  %-7d  %s\n', r, i, n, strjoin(hexes, ' '));
                else
                    fprintf('%-6d  %-7d  %s\n', i, n, strjoin(hexes, ' '));
                end

            end

        end

        function obj = select(obj, nColors, rank)
            % Select the rank-th palette among those with >= nColors colors.
            % Returns obj for chaining. In manual mode this is ignored.
            arguments
                obj
                nColors (1, 1) double {mustBePositive, mustBeInteger}
                rank (1, 1) double {mustBePositive, mustBeInteger}
            end

            if obj.isManual_

                if ~obj.quiet
                    fprintf('[ColorManager] Manual mode: select() ignored, using %d provided colors.\n', ...
                        size(obj.currentColors, 1));
                end

                return;
            end

            indices = obj.filterByNColors_(nColors);

            if isempty(indices)
                obj.raise_('ColorManager:noMatch', ...
                    'No palettes with >= %d colors. Falling back to palette #1.', ...
                    'No palettes with >= %d colors.', nColors);

                if obj.nPalettes == 0
                    error('ColorManager:noMatch', 'No palettes loaded.');
                end

                idx = 1;
                rank = 1;
            elseif rank > numel(indices)
                obj.raise_('ColorManager:rankOutOfRange', ...
                    'rank=%d out of range, clamped to %d.', ...
                    'rank=%d out of range: %d palettes have >= %d colors.', ...
                    rank, numel(indices), numel(indices), nColors);
                idx = indices(end);
                rank = numel(indices);
            else
                idx = indices(rank);
            end

            obj.applySelection_(idx, rank, numel(indices), nColors);
        end

        function preview(obj, nColors, rank)
            % Visual preview of a palette. No args previews the current selection.
            arguments
                obj
                nColors (1, 1) double {mustBeNonnegative, mustBeInteger} = 0
                rank (1, 1) double {mustBeNonnegative, mustBeInteger} = 0
            end

            if nColors == 0
                obj.ensureSelected_();
                idx = obj.currentIdx;
            else
                indices = obj.filterByNColors_(nColors);

                if isempty(indices)
                    obj.raise_('ColorManager:noMatch', ...
                        'No palettes with >= %d colors. Falling back to palette #1.', ...
                        'No palettes with >= %d colors.', nColors);

                    if obj.nPalettes == 0
                        error('ColorManager:noMatch', 'No palettes loaded.');
                    end

                    idx = 1;
                elseif rank > numel(indices)
                    obj.raise_('ColorManager:rankOutOfRange', ...
                        'rank=%d out of range, clamped to %d.', ...
                        'rank=%d out of range: %d palettes have >= %d colors.', ...
                        rank, numel(indices), numel(indices), nColors);
                    idx = indices(end);
                else
                    idx = indices(rank);
                end

            end

            c = obj.palettes{idx};
            n = size(c, 1);

            if nargin >= 3 && rank > 0
                titleStr = sprintf('select(%d,%d)  (global idx: %d)', nColors, rank, idx);
            else
                titleStr = sprintf('select(%d,%d)  (global idx: %d)', ...
                    obj.selectNColors_, obj.selectRank_, idx);
            end

            % Build index-to-name reverse lookup
            idxToName = cell(1, n);
            names = obj.assignments.keys();

            for k = 1:numel(names)
                ci = obj.assignments(names{k});

                if ci <= n
                    idxToName{ci} = names{k};
                end

            end

            % Build legend labels
            legendLabels = cell(1, n);

            for i = 1:n

                if isempty(idxToName{i})
                    legendLabels{i} = sprintf('color %d', i);
                else
                    legendLabels{i} = idxToName{i};
                end

            end

            fig = figure('Name', 'ColorManager preview', ...
                'NumberTitle', 'off', 'Color', 'w', 'MenuBar', 'none');
            set(fig, 'defaultTextInterpreter', 'none', ...
                'defaultAxesTickLabelInterpreter', 'none', ...
                'defaultLegendInterpreter', 'none');

            % --- Swatches ---
            subplot(2, 1, 1); hold on;

            for i = 1:n
                rectangle('Position', [i - 1, 0, 1, 1], ...
                    'FaceColor', c(i, :), 'EdgeColor', [0.85 0.85 0.85]);
                hex = obj.rgb2hex_(c(i, :));
                text(i - 0.5, -0.13, hex{1}, ...
                    'HorizontalAlignment', 'center', 'FontSize', 8, Interpreter = "none");

                if isempty(idxToName{i})
                    text(i - 0.5, -0.36, sprintf('(%d)', i), ...
                        'HorizontalAlignment', 'center', 'FontSize', 7, ...
                        'Color', [0.4 0.4 0.4], Interpreter = "none");
                else
                    text(i - 0.5, -0.36, sprintf('(%d) %s', i, idxToName{i}), ...
                        'HorizontalAlignment', 'center', 'FontSize', 7, ...
                        'Color', [0.2 0.2 0.2], 'FontWeight', 'bold', Interpreter = "none");
                end

            end

            xlim([0, n]); ylim([-0.58, 1]);
            axis off;
            title(titleStr, 'FontSize', 12, Interpreter = "none");

            % --- Sample curves ---
            subplot(2, 1, 2); hold on; box on;
            x = linspace(0, 4 * pi, 24)';

            for i = 1:n
                y = sin(x + (i - 1) * pi / n);
                plot(x, y, 'Color', c(i, :), 'LineWidth', 1.8, ...
                    'DisplayName', legendLabels{i});
            end

            xlabel('x', Interpreter = "none"); ylabel('y', Interpreter = "none");
            title('Sample curves', Interpreter = "none");
            legend('Location', 'best', Interpreter = "none");
        end

        function browse(obj, nColors)
            % BROWSE Interactively browse palettes with a side-panel list.
            %
            %   cm.browse()        browse all palettes
            %   cm.browse(nColors) browse palettes with >= nColors colors
            %
            %   Left panel: scrollable list with color-preview strips.
            %   Right panel: detailed swatches and sample curves.
            %   Up/Down arrow keys, mouse wheel, click to select.

            arguments
                obj
                nColors (1, 1) double {mustBeNonnegative, mustBeInteger} = 0
            end

            if nColors == 0
                indices = 1:obj.nPalettes;
            else
                indices = obj.filterByNColors_(nColors);

                if isempty(indices)
                    error('ColorManager:noMatch', ...
                        'No palettes with >= %d colors.', nColors);
                end

            end

            nTotal = numel(indices);

            % Precompute select() rank for every palette
            selRank = zeros(1, nTotal);

            for i = 1:nTotal
                gi = indices(i);
                nc = size(obj.palettes{gi}, 1);
                ranked = obj.filterByNColors_(nc);
                selRank(i) = find(ranked == gi, 1);
            end

            % ---- Layout constants ----
            FIG_W = 1300;
            FIG_H = 720;
            ROW_H = 32; % row height in data units
            MAX_SW = 10; % max color swatches per list row
            SW_W = 15; % swatch width in data units
            SW_GAP = 1; % gap between swatches

            % ---- Figure ----
            fig = figure('Name', 'ColorManager - Browse Palettes', ...
                'NumberTitle', 'off', 'Color', 'w', 'MenuBar', 'none', ...
                'Units', 'pixels', 'Position', [40, 40, FIG_W, FIG_H], ...
                'KeyPressFcn', @keyCB, ...
                'WindowScrollWheelFcn', @wheelCB, ...
                'CloseRequestFcn', @(~, ~) delete(gcbf));
            set(fig, 'defaultTextInterpreter', 'none', ...
                'defaultAxesTickLabelInterpreter', 'none', ...
                'defaultLegendInterpreter', 'none');
            set(fig, 'SizeChangedFcn', @(~, ~) onResize());

            % ---- Left panel (palette list) ----
            listPanel = uipanel('Parent', fig, 'Units', 'normalized', ...
                'Position', [0, 0, 0.28, 1.0], ...
                'BorderType', 'line', 'BackgroundColor', 'w', ...
                'HighlightColor', [0.8 0.8 0.8]);

            infoStr = sprintf('%d palettes', nTotal);

            if nColors > 0
                infoStr = sprintf('%s  (>= %d colors)', infoStr, nColors);
            end

            uicontrol('Parent', listPanel, 'Style', 'text', ...
                'Units', 'normalized', ...
                'Position', [0.02, 0.955, 0.92, 0.035], ...
                'String', infoStr, 'FontWeight', 'bold', 'FontSize', 9, ...
                'BackgroundColor', 'w', 'HorizontalAlignment', 'left');

            listAx = axes('Parent', listPanel, 'Units', 'normalized', ...
                'Position', [0.02, 0.01, 0.92, 0.935], ...
                'Box', 'off', 'XTick', [], 'YTick', [], ...
                'ButtonDownFcn', @clickList);
            hold(listAx, 'on');

            scroll = uicontrol('Parent', listPanel, 'Style', 'slider', ...
                'Units', 'normalized', ...
                'Position', [0.945, 0.01, 0.035, 0.935], ...
                'Callback', @(~, ~) scrollList());

            % ---- Draw palette list entries ----
            % Get pixel size of listAx for data coordinate system
            set(listAx, 'Units', 'pixels');
            axPos = get(listAx, 'Position');
            set(listAx, 'Units', 'normalized');
            listAxW = axPos(3);
            listAxH = axPos(4);

            totalH = nTotal * ROW_H;
            visibleH = listAxH;
            maxScroll = max(0, totalH - visibleH);

            if maxScroll > 0
                set(scroll, 'Min', 0, 'Max', 1, 'Value', 1, 'Visible', 'on', ...
                    'SliderStep', [min(1, visibleH / totalH), ...
                       min(1, 5 * visibleH / totalH)]);
            else
                set(scroll, 'Visible', 'off');
            end

            textX = 4;
            swatchX = 210;

            for i = 1:nTotal
                gi = indices(i);
                nc = size(obj.palettes{gi}, 1);
                c = obj.palettes{gi};
                yTop = totalH - (i - 1) * ROW_H;
                yBot = yTop - ROW_H;
                yMid = (yTop + yBot) / 2;

                if mod(i, 2) == 0
                    rectangle(listAx, 'Position', [0, yBot, 9999, ROW_H], ...
                        'FaceColor', [0.972 0.972 0.972], ...
                        'EdgeColor', 'none', 'HitTest', 'off');
                end

                text(listAx, textX, yMid, ...
                    sprintf('#%d  %d col  select(%d,%d)', gi, nc, nc, selRank(i)), ...
                    'FontSize', 9, 'VerticalAlignment', 'middle', ...
                    'Interpreter', 'none', 'HitTest', 'off');

                nShow = min(MAX_SW, nc);

                for j = 1:nShow
                    x0 = swatchX + (j - 1) * (SW_W + SW_GAP);
                    rectangle(listAx, 'Position', [x0, yMid - 8, SW_W, 16], ...
                        'FaceColor', c(j, :), 'EdgeColor', [0.55 0.55 0.55], ...
                        'HitTest', 'off');
                end

                if nc > MAX_SW
                    text(listAx, swatchX + nShow * (SW_W + SW_GAP) + 3, yMid, ...
                        sprintf('+%d', nc - MAX_SW), 'FontSize', 7, ...
                        'VerticalAlignment', 'middle', 'Color', [0.4 0.4 0.4], ...
                        'HitTest', 'off');
                end

            end

            xlim(listAx, [0, listAxW]);
            ylim(listAx, [0, max(totalH, visibleH)]);

            hlRect = rectangle(listAx, ...
                'Position', [0, totalH - ROW_H, 5, ROW_H], ...
                'FaceColor', [0.2 0.45 0.8], 'EdgeColor', 'none', ...
                'HitTest', 'off');

            % ---- Right panel (detail) ----
            ax1 = axes('Parent', fig, 'Units', 'normalized', ...
                'Position', [0.30, 0.53, 0.68, 0.43]);
            ax2 = axes('Parent', fig, 'Units', 'normalized', ...
                'Position', [0.30, 0.05, 0.68, 0.43]);

            % ---- State ----
            pos = 1;

            refreshDetail();
            scrollList();

            function scrollList()
                if maxScroll <= 0, return; end
                frac = get(scroll, 'Value');
                y0 = (1 - frac) * maxScroll;
                ylim(listAx, [y0, y0 + visibleH]);
            end

            function clickList(~, ~)
                pt = get(listAx, 'CurrentPoint');
                yClick = pt(1, 2);
                newPos = nTotal - floor(yClick / ROW_H);
                newPos = max(1, min(nTotal, newPos));

                if newPos ~= pos
                    pos = newPos;
                    refreshDetail();
                    refreshHighlight();
                end

            end

            function wheelCB(~, evt)
                if maxScroll <= 0, return; end
                frac = get(scroll, 'Value');
                frac = frac + evt.VerticalScrollCount * visibleH / totalH * 0.25;
                frac = max(0, min(1, frac));
                set(scroll, 'Value', frac);
                scrollList();
            end

            function onResize()
                set(listAx, 'Units', 'pixels');
                axPos = get(listAx, 'Position');
                set(listAx, 'Units', 'normalized');
                newW = axPos(3);
                newH = axPos(4);
                xlim(listAx, [0, newW]);
                visibleH = newH;
                maxScroll = max(0, totalH - visibleH);

                if maxScroll > 0
                    set(scroll, 'Min', 0, 'Max', 1, 'Visible', 'on', ...
                        'SliderStep', [min(1, visibleH / totalH), ...
                           min(1, 5 * visibleH / totalH)]);
                else
                    set(scroll, 'Visible', 'off');
                end

                scrollList();
            end

            function keyCB(~, evt)

                switch evt.Key
                    case {'uparrow', 'leftarrow'}

                        if pos > 1
                            pos = pos - 1;
                            refreshDetail();
                            refreshHighlight();
                            ensureVisible();
                        end

                    case {'downarrow', 'rightarrow'}

                        if pos < nTotal
                            pos = pos + 1;
                            refreshDetail();
                            refreshHighlight();
                            ensureVisible();
                        end

                end

            end

            function ensureVisible()
                if maxScroll <= 0, return; end
                yTop = totalH - (pos - 1) * ROW_H;
                yBot = yTop - ROW_H;
                yl = ylim(listAx);

                if yBot < yl(1)
                    set(scroll, 'Value', max(0, 1 - yBot / maxScroll));
                    scrollList();
                elseif yTop > yl(2)
                    set(scroll, 'Value', max(0, 1 - (yTop - visibleH) / maxScroll));
                    scrollList();
                end

            end

            function refreshHighlight()
                yTop = totalH - (pos - 1) * ROW_H;
                set(hlRect, 'Position', [0, yTop - ROW_H, 5, ROW_H]);
                uistack(hlRect, 'top');
            end

            function refreshDetail()
                idx = indices(pos);
                c = obj.palettes{idx};
                n = size(c, 1);

                cla(ax1);
                hold(ax1, 'on');

                for ii = 1:n
                    rectangle(ax1, 'Position', [ii - 1, 0, 1, 1], ...
                        'FaceColor', c(ii, :), 'EdgeColor', [0.85 0.85 0.85]);
                    hex = obj.rgb2hex_(c(ii, :));
                    text(ax1, ii - 0.5, -0.13, hex{1}, ...
                        'HorizontalAlignment', 'center', 'FontSize', 8, ...
                        'Interpreter', 'none');
                    text(ax1, ii - 0.5, -0.36, sprintf('(%d)', ii), ...
                        'HorizontalAlignment', 'center', 'FontSize', 7, ...
                        'Color', [0.4 0.4 0.4], Interpreter = "none");
                end

                xlim(ax1, [0, n]);
                ylim(ax1, [-0.58, 1]);
                axis(ax1, 'off');
                title(ax1, sprintf('#%d  %d colors  select(%d,%d)    -  %d / %d', ...
                    idx, n, n, selRank(pos), pos, nTotal), ...
                    'FontSize', 12, Interpreter = "none");

                cla(ax2);
                hold(ax2, 'on');
                box(ax2, 'on');
                x = linspace(0, 4 * pi, 128)';

                for jj = 1:n
                    y = sin(x + (jj - 1) * pi / n);
                    plot(ax2, x, y, 'Color', c(jj, :), 'LineWidth', 1.8, ...
                        'DisplayName', sprintf('color %d', jj));
                end

                xlabel(ax2, 'x', Interpreter = "none");
                ylabel(ax2, 'y', Interpreter = "none");
                title(ax2, sprintf('Sample curves (%d colors)', n), Interpreter = "none");
                legend(ax2, 'Location', 'best', Interpreter = "none");
            end

        end

        function c = get_idx(obj, idx)
            % Get color by index.
            arguments
                obj
                idx (1, 1) double {mustBePositive, mustBeInteger}
            end

            obj.ensureSelected_();
            n = size(obj.currentColors, 1);

            if idx > n

                if obj.isManual_
                    idx = mod(idx - 1, n) + 1;
                else
                    idx = n;
                    obj.raise_('ColorManager:badColorIndex', ...
                        'Color index out of range, clamped to %d.', ...
                        'Color index %d out of range [1, %d].', idx, idx, n);
                end

            end

            c = obj.currentColors(idx, :);
        end

        function c = get_name(obj, name)
            % Get color by assigned name.
            arguments
                obj
                name (1, 1) string
            end

            key = char(name);

            if ~obj.assignments.isKey(key)
                obj.raise_('ColorManager:unknownName', ...
                    '"%s" not assigned, using default color order.', ...
                    '"%s" has not been assigned. Use cm.assign(''%s'', idx) first.', key, key);
                c = obj.fallbackColor_();
            else
                idx = obj.assignments(key);
                obj.ensureSelected_();
                n = size(obj.currentColors, 1);

                if idx > n

                    if obj.isManual_
                        idx = mod(idx - 1, n) + 1;
                    else
                        idx = n;
                    end

                end

                c = obj.currentColors(idx, :);
            end

        end

        function obj = assign(obj, name, colorIdx)
            % Bind a name to a color index. Returns obj for chaining.
            arguments
                obj
                name (1, 1) string
                colorIdx (1, 1) double {mustBePositive, mustBeInteger}
            end

            obj.ensureSelected_();
            n = size(obj.currentColors, 1);

            if colorIdx < 1 || colorIdx > n
                colorIdx = max(1, min(colorIdx, n));
                obj.raise_('ColorManager:badColorIndex', ...
                    'Color index out of range, clamped to %d.', ...
                    'Color index %d out of range [1, %d].', colorIdx, colorIdx, n);
            end

            key = char(name);
            names = obj.assignments.keys();

            for i = 1:numel(names)

                if obj.assignments(names{i}) == colorIdx && ~strcmp(names{i}, key)
                    obj.raise_('ColorManager:duplicateBinding', ...
                        'Color index %d was bound to "%s", overwritten.', ...
                        'Color index %d is already bound to "%s".', colorIdx, names{i});
                    break;
                end

            end

            obj.assignments(key) = colorIdx;
        end

    end

    methods (Access = private)

        function loadDatabase_(obj, dbPath)

            if strlength(dbPath) == 0
                classDir = fileparts(mfilename('fullpath'));
                candidates = {
                              fullfile(classDir, 'colors.csv')
                              fullfile(classDir, 'colors.txt')
                              fullfile(pwd(), 'colors.csv')
                              fullfile(pwd(), 'colors.txt')
                              };
                found = false;

                for k = 1:numel(candidates)

                    if exist(candidates{k}, 'file') == 2
                        dbPath = candidates{k};
                        found = true;
                        break;
                    end

                end

                if ~found
                    error('ColorManager:dbNotFound', ...
                    'colors.csv or colors.txt not found. Specify path via ColorManager(path).');
                end

            elseif exist(dbPath, 'file') ~= 2
                error('ColorManager:dbNotFound', ...
                    'Database file not found: %s', dbPath);
            end

            obj.dbPath_ = char(dbPath);
            obj.palettes = {};
            fid = fopen(dbPath, 'r');
            cleaner = onCleanup(@() fclose(fid));

            while ~feof(fid)
                line = strtrim(fgetl(fid));

                if isempty(line) || ~contains(line, '#')
                    continue;
                end

                hexColors = strsplit(line, ',');
                rgb = zeros(0, 3);

                for k = 1:numel(hexColors)
                    h = strtrim(hexColors{k});

                    if isempty(h)
                        continue;
                    end

                    if h(1) ~= '#'
                        h = ['#', h];
                    end

                    if numel(h) ~= 7 || ~all(isstrprop(h(2:end), 'xdigit'))
                        continue;
                    end

                    rgb(end + 1, :) = [hex2dec(h(2:3)), hex2dec(h(4:5)), hex2dec(h(6:7))] / 255;
                end

                if ~isempty(rgb)
                    obj.palettes{end + 1} = rgb;
                end

            end

            obj.nPalettes = numel(obj.palettes);

            if ~obj.quiet
                fprintf('[ColorManager] Loaded %d palettes from %s\n', obj.nPalettes, obj.dbPath_);
            end

        end

        function initManual_(obj, rgb)
            % Initialize manual mode with given RGB matrix.
            if ~ismatrix(rgb) || size(rgb, 2) ~= 3
                error('ColorManager:invalidRGB', 'RGB must be an Nx3 numeric matrix.');
            end

            if any(rgb(:) > 1)
                rgb = rgb / 255;
            end

            rgb = max(0, min(1, rgb));

            if isempty(rgb)
                error('ColorManager:emptyColors', 'No valid colors provided.');
            end

            obj.isManual_ = true;
            obj.palettes = {rgb};
            obj.nPalettes = 1;
            obj.currentIdx = 1;
            obj.currentColors = rgb;
            obj.fallbackIdx_ = 0;
            obj.selectNColors_ = size(rgb, 1);
            obj.selectRank_ = 1;
            obj.selectTotal_ = 1;

            if ~obj.quiet
                fprintf('[ColorManager] Manual mode: %d colors provided.\n', size(rgb, 1));
            end

        end

        function rgb = parseHex_(~, hex)

            rgb = zeros(0, 3);

            for k = 1:numel(hex)
                h = char(strtrim(hex(k)));
                if isempty(h), continue; end
                if h(1) ~= '#', h = ['#', h]; end

                if numel(h) == 7 && all(isstrprop(h(2:end), 'xdigit'))
                    rgb(end + 1, :) = [hex2dec(h(2:3)), hex2dec(h(4:5)), hex2dec(h(6:7))] / 255;
                end

            end

            if isempty(rgb)
                error('ColorManager:emptyColors', 'No valid hex colors provided.');
            end

        end

        function ensureSelected_(obj)

            if obj.currentIdx == 0

                if obj.nPalettes == 0
                    error('ColorManager:noPalettes', 'No palettes loaded.');
                end

                obj.raise_('ColorManager:noSelection', ...
                    'No palette selected, auto-selected palette #1.', ...
                'No palette selected. Use cm.list(nColors) then cm.select(nColors, rank).');
                n = size(obj.palettes{1}, 1);
                obj.applySelection_(1, 1, obj.nPalettes, n);
            end

        end

        function applySelection_(obj, idx, rank, total, nColors)

            if nargin < 5
                nColors = size(obj.palettes{idx}, 1);
                rank = 1;
                total = 1;
            end

            obj.currentIdx = idx;
            obj.currentColors = obj.palettes{idx};
            obj.assignments = containers.Map();
            obj.fallbackIdx_ = 0;
            obj.selectNColors_ = nColors;
            obj.selectRank_ = rank;
            obj.selectTotal_ = total;

            if ~obj.quiet
                fprintf('[ColorManager] select(%d, %d) -> palette #%d, %d colors\n', ...
                    nColors, rank, idx, size(obj.currentColors, 1));
            end

        end

        function raise_(obj, errorId, warnMsg, strictMsg, varargin)
            % Raise error in strict mode, warning otherwise.
            if obj.strict
                error(errorId, strictMsg, varargin{:});
            else
                warning(errorId, warnMsg, varargin{:});
            end

        end

        function c = fallbackColor_(obj)
            % Return next color from MATLAB's default color order, cycling.
            defaultColors = get(groot, 'defaultAxesColorOrder');
            n = size(defaultColors, 1);
            idx = mod(obj.fallbackIdx_, n) + 1;
            obj.fallbackIdx_ = idx;
            c = defaultColors(idx, :);
        end

        function indices = filterByNColors_(obj, nColors)
            counts = cellfun(@(c) size(c, 1), obj.palettes);
            idx = 1:obj.nPalettes;
            filtered = idx(counts >= nColors);
            [~, sortOrd] = sort(counts(filtered));
            indices = filtered(sortOrd);
        end

        function rk = selectRankFor_(obj, idx, nColors)
            % Rank of palette idx among palettes with >= nColors colors.
            ranked = obj.filterByNColors_(nColors);
            rk = find(ranked == idx, 1);
        end

    end

    methods (Static, Access = private)

        function hexes = rgb2hex_(rgb)
            hexes = cell(size(rgb, 1), 1);

            for i = 1:size(rgb, 1)
                hexes{i} = sprintf('#%02X%02X%02X', ...
                    round(rgb(i, 1) * 255), round(rgb(i, 2) * 255), round(rgb(i, 3) * 255));
            end

        end

    end

    properties (Access = private)
        dbPath_ % database file path (internal)
        isManual_ (1, 1) logical = false % manual mode: colors provided directly
        fallbackIdx_ = 0 % counter for fallback color cycling
        selectNColors_ = 0 % nColors used in last select
        selectRank_ = 0 % rank used in last select
        selectTotal_ = 0 % total matching palettes in last select
    end

end
