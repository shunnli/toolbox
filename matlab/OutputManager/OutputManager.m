classdef OutputManager

    properties (SetAccess = private)
        base_dir % Base output directory
        cur_dir % Current output directory
        ts_raw % Timestamp
    end

    methods

        function obj = OutputManager(output_path, label_name, opts)
            % Constructor for OutputManager
            %
            %   obj = OutputManager()
            %       Creates an output directory under "outputs" with current timestamp
            %
            %   obj = OutputManager(output_path)
            %       Creates output directory under specified base path
            %
            %   obj = OutputManager(output_path, label_name)
            %       Appends label_name before timestamp in directory name
            %
            %   obj = OutputManager(ExistingDir=output_dir)
            %       Reuses an existing output directory directly. This is
            %       intended for lightweight postprocessing reruns.
            %
            % Parameters
            %   output_path: string scalar (default: "outputs")
            %   label_name : string scalar (default: "")
            %
            % Environment variables: (higher priority)
            %   OUTPUT_MANAGER_OUTPUT_PATH: Overrides output_path if set
            %   OUTPUT_MANAGER_LABEL_NAME: Overrides label_name if set
            %
            % ExistingDir mode ignores OUTPUT_MANAGER_OUTPUT_PATH and
            % OUTPUT_MANAGER_LABEL_NAME.

            arguments
                output_path (1, 1) string = "outputs"
                label_name (1, 1) string = ""
                opts.ExistingDir (1, 1) string = ""
            end

            if strlength(opts.ExistingDir) > 0

                if output_path ~= "outputs" || strlength(label_name) > 0
                    error('OutputManager:existingDirExclusive', ...
                    'ExistingDir cannot be combined with output_path or label_name.');
                end

                [base_dir, cur_dir] = OutputManager.resolve_existing_directory(opts.ExistingDir);

                obj.base_dir = strrep(base_dir, '\', '/');
                obj.cur_dir = strrep(cur_dir, '\', '/');
                obj.ts_raw = datetime("now", "Format", "yyyyMMdd-HHmmss");

                fprintf('[OutputManager] Using existing output directory: %s\n', obj.cur_dir);
                return;
            end

            env_output_path = getenv('OUTPUT_MANAGER_OUTPUT_PATH');

            if ~isempty(env_output_path)

                if ~strcmp(env_output_path, output_path)
                    warning('OutputManager:env_override', ...
                        'Environment variable OUTPUT_MANAGER_OUTPUT_PATH="%s" overrides output_path="%s".', env_output_path, output_path);
                end

                output_path = env_output_path;
            end

            env_label_name = getenv('OUTPUT_MANAGER_LABEL_NAME');

            if ~isempty(env_label_name)

                if ~strcmp(env_label_name, label_name)
                    warning('OutputManager:env_override_label', ...
                        'Environment variable OUTPUT_MANAGER_LABEL_NAME="%s" overrides label_name="%s".', env_label_name, label_name);
                end

                label_name = env_label_name;
            end

            label_name = OutputManager.validate_label_name(label_name);

            base_dir = char(output_path);

            if ~exist(base_dir, 'dir')

                try
                    mkdir(base_dir);
                catch ME
                    warning("OutputManager:baseDirFail", ...
                        "Failed to create base directory '%s'. Falling back to pwd().\nReason: %s", ...
                        base_dir, ME.message);
                    base_dir = pwd();
                end

            end

            ts_raw = datetime("now", "Format", "yyyyMMdd-HHmmss");
            obj.ts_raw = ts_raw;

            if strlength(label_name) == 0
                ts = char(ts_raw);
            else
                ts = sprintf('%s-%s', label_name, char(ts_raw));
            end

            cur_dir = fullfile(base_dir, ts);

            try
                mkdir(cur_dir);
            catch ME
                warning("OutputManager:curDirFail", ...
                    "Failed to create output directory '%s'. Falling back to pwd()/timestamp.\nReason: %s", ...
                    cur_dir, ME.message);
                cur_dir = fullfile(pwd(), ts);

                try
                    mkdir(cur_dir);
                catch ME2
                    warning("OutputManager:curDirFail2", ...
                        "Failed to create fallback directory '%s'. Using pwd() instead.\nReason: %s", ...
                        cur_dir, ME2.message);
                    cur_dir = pwd();
                end

            end

            base_dir = OutputManager.to_absolute_path(base_dir);
            cur_dir = OutputManager.to_absolute_path(cur_dir);

            obj.base_dir = strrep(base_dir, '\', '/');
            obj.cur_dir = strrep(cur_dir, '\', '/');

            if strlength(label_name) > 0
                fprintf('[OutputManager] Label: %s\n', label_name);
            end

            fprintf('[OutputManager] Output directory: %s\n', obj.cur_dir);
        end

        function p = get_file_path(obj, filename, make_sure_exist)
            % Return full path under current output directory
            %
            %   p = obj.get_file_path(filename)
            %       Returns path and ensures parent directories exist
            %
            %   p = obj.get_file_path(filename, make_sure_exist)
            %       If make_sure_exist==false, parent directories are not created
            %
            % Parameters
            %   filename        : string scalar or char vector
            %   make_sure_exist : logical scalar (default: true)

            arguments
                obj
                filename (1, 1) string
                make_sure_exist (1, 1) logical = true
            end

            % Safety check
            if contains(filename, "..")
                warning("OutputManager:get_file_path", ...
                "filename contains '..'.");
            end

            % Construct full path
            p = fullfile(obj.cur_dir, filename);

            % Ensure parent dirs exist if requested
            if make_sure_exist
                parent_dir = fileparts(p);

                if ~isempty(parent_dir) && ~exist(parent_dir, 'dir')

                    try
                        mkdir(parent_dir);
                    catch ME
                        warning("OutputManager:parentDirFail", ...
                            "Failed to create parent directory '%s'. Using current directory instead.\nReason: %s", ...
                            parent_dir, ME.message);
                        [~, fname, fext] = fileparts(filename);
                        p = fullfile(obj.cur_dir, strcat(fname, fext));
                    end

                end

            end

            p = strrep(p, '\', '/');
        end

    end

    methods (Static, Access = private)

        function [base_dir, cur_dir] = resolve_existing_directory(output_dir)

            cur_dir = char(output_dir);

            if ~exist(cur_dir, 'dir')
                error('OutputManager:missingOutputDir', ...
                    'Output directory does not exist: %s', cur_dir);
            end

            cur_dir = OutputManager.to_absolute_path(cur_dir);
            base_dir = fileparts(cur_dir);
        end

        function label_name = validate_label_name(label_name)

            label_name = string(label_name);

            if strlength(label_name) == 0
                return;
            end

            if contains(label_name, "..") || contains(label_name, "/") || contains(label_name, "\")
                error('OutputManager:invalidLabelName', ...
                    'label_name must not contain path separators or ''..'': %s', label_name);
            end

        end

        function p = to_absolute_path(p)
            old = pwd();
            cleaner = onCleanup(@() cd(old)); % cd back to original directory

            try
                % Change directory to path and get absolute path
                cd(p);
                p = pwd();
            catch
                % if cd fails, keep original
                p = char(p);
            end

        end

    end

end
