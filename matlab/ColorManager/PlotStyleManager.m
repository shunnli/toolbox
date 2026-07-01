classdef PlotStyleManager < handle
    %PLOTSTYLEMANAGER Plot style manager (marker, line style, etc.) for MATLAB.
    %
    %   psm = PlotStyleManager()
    %
    %   psm.assign('name', Marker='o', MarkerSize=8, LineStyle='--', LineWidth=2)
    %   psm.get_style('name')  % returns NV cell array for plot()
    %
    %   Example:
    %     psm = PlotStyleManager();
    %     psm.assign('Ours', Marker='o', LineStyle='-', LineWidth=2);
    %     psm.assign('Baseline', Marker='s', LineStyle='--', LineWidth=1.5);
    %
    %     plot(x1, y1, psm.get_style('Ours'){:});
    %     plot(x2, y2, psm.get_style('Baseline'){:});

    properties (SetAccess = private)
        markers
        markerSizes
        markerEdgeColors
        markerFaceColors
        lineStyles
        lineWidths
    end

    methods

        function obj = PlotStyleManager()
            obj.markers = containers.Map();
            obj.markerSizes = containers.Map();
            obj.markerEdgeColors = containers.Map();
            obj.markerFaceColors = containers.Map();
            obj.lineStyles = containers.Map();
            obj.lineWidths = containers.Map();
        end

        function obj = assign(obj, name, opts)

            arguments
                obj
                name (1, 1) string
                opts.Marker (1, 1) string = ""
                opts.MarkerSize (1, 1) double {mustBeNonnegative} = 0
                opts.MarkerEdgeColor (1, 1) string = ""
                opts.MarkerFaceColor (1, 1) string = ""
                opts.LineStyle (1, 1) string = ""
                opts.LineWidth (1, 1) double {mustBeNonnegative} = 0
            end

            key = char(name);
            if strlength(opts.Marker) > 0, obj.markers(key) = char(opts.Marker); end
            if opts.MarkerSize > 0, obj.markerSizes(key) = opts.MarkerSize; end
            if strlength(opts.MarkerEdgeColor) > 0, obj.markerEdgeColors(key) = char(opts.MarkerEdgeColor); end
            if strlength(opts.MarkerFaceColor) > 0, obj.markerFaceColors(key) = char(opts.MarkerFaceColor); end
            if strlength(opts.LineStyle) > 0, obj.lineStyles(key) = char(opts.LineStyle); end
            if opts.LineWidth > 0, obj.lineWidths(key) = opts.LineWidth; end
        end

        function s = get_style(obj, name)
            % Return name-value cell array for use with plot(..., s{:}).
            arguments
                obj
                name (1, 1) string
            end

            key = char(name);
            s = {};

            if obj.markers.isKey(key)
                s = [s, {'Marker'}, obj.markers(key)];
            end

            if obj.markerSizes.isKey(key)
                s = [s, {'MarkerSize'}, obj.markerSizes(key)];
            end

            if obj.markerEdgeColors.isKey(key)
                s = [s, {'MarkerEdgeColor'}, obj.markerEdgeColors(key)];
            end

            if obj.markerFaceColors.isKey(key)
                s = [s, {'MarkerFaceColor'}, obj.markerFaceColors(key)];
            end

            if obj.lineStyles.isKey(key)
                s = [s, {'LineStyle'}, obj.lineStyles(key)];
            end

            if obj.lineWidths.isKey(key)
                s = [s, {'LineWidth'}, obj.lineWidths(key)];
            end

        end

    end

end
