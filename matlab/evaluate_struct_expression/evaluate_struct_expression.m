function value = evaluate_struct_expression(expr, varargin)
    %EVALUATE_STRUCT_EXPRESSION Evaluate a scalar expression from struct fields.
    %
    % value = evaluate_struct_expression(expr, s1, s2, ..., Recursive = false)
    %
    % The expression may reference scalar real struct members by their direct
    % field names. Symbols are matched by field name only; callers do not write
    % dotted access such as "config.epsilon" inside the expression.
    %
    % Example
    % -------
    %   config = struct(ep = 0.5);
    %   mesh = struct(dx = 0.1);
    %
    %   value = evaluate_struct_expression('0.2*ep*dx', config, mesh)
    %
    % returns
    %
    %   value = 0.2 * config.ep * mesh.dx
    %
    % A slightly richer example is
    %
    %   value = evaluate_struct_expression('0.2*ep*dx^2 + 2*dx*dx', ...
    %       config, mesh);
    %
    % By default only direct struct fields are considered. To recurse into
    % nested scalar structs, enable
    %
    %   value = evaluate_struct_expression('0.2*ep*dx', config, example, ...
    %       Recursive = true);
    %
    % Supported expression syntax
    % ---------------------------
    %   - scalar numbers
    %   - field-name symbols such as ep, dx, dy, dz
    %   - operators +, -, *, /, ^
    %   - parentheses
    %   - whitespace as implicit multiplication, for example "0.2 ep dx"
    %
    % The result must be a finite real scalar.
    %
    % If the same symbol name appears in more than one location across the
    % provided structs, evaluation fails with an explicit conflict error.
    % For example,
    %
    %   a = struct(dx = 0.1);
    %   b = struct(dx = 0.2);
    %   evaluate_struct_expression('dx', a, b)
    %
    % raises a NameConflict error because both a.dx and b.dx define the
    % symbol dx. Likewise, if the expression references a symbol that is not
    % provided by any input struct, evaluation fails with an UnknownSymbol
    % error.

    [sources, opts] = parse_inputs(varargin{:});

    if ~(ischar(expr) || (isstring(expr) && isscalar(expr)))
        error('evaluate_struct_expression:InvalidExpressionType', 'expr must be a character vector or string scalar.');
    end

    if isempty(sources)
        error('evaluate_struct_expression:MissingSources', 'At least one struct source is required.');
    end

    expr = normalize_expression(char(string(expr)));
    symbol_names = unique(regexp(expr, '[A-Za-z]\w*', 'match'));
    builtin_names = "pi";
    requested_names = setdiff(string(symbol_names), builtin_names);
    symbol_table = struct();
    symbol_paths = struct();

    for i = 1:numel(sources)
        source = sources{i};

        if ~isstruct(source) || ~isscalar(source)
            error('evaluate_struct_expression:InvalidSource', 'All expression sources must be scalar structs.');
        end

        source_name = sprintf('arg%d', i);
        [symbol_table, symbol_paths] = collect_symbols(source, source_name, requested_names, symbol_table, symbol_paths, opts.Recursive);
    end

    names = symbol_names;

    for i = 1:numel(names)
        name = names{i};

        if any(string(name) == builtin_names)
            continue;
        end

        if ~isfield(symbol_table, name)
            error('evaluate_struct_expression:UnknownSymbol', 'Expression references unknown symbol "%s".', name);
        end

    end

    for i = 1:numel(names)
        name = names{i};

        if any(string(name) == builtin_names)
            continue;
        end

        eval(sprintf('%s = symbol_table.%s;', name, name));
    end

    value = eval(expr);

    if ~(isnumeric(value) && isscalar(value) && isfinite(value) && isreal(value))
        error('evaluate_struct_expression:InvalidResult', 'Expression must resolve to a finite real scalar.');
    end

end

function [sources, opts] = parse_inputs(varargin)
    opts = struct(Recursive = false);
    sources = {};
    i = 1;

    while i <= numel(varargin)
        arg = varargin{i};

        if (ischar(arg) || (isstring(arg) && isscalar(arg))) && strcmpi(string(arg), "Recursive")
            if i == numel(varargin)
                error('evaluate_struct_expression:MissingOptionValue', ...
                    'Option Recursive requires a logical scalar value.');
            end

            value = varargin{i + 1};

            if ~(islogical(value) && isscalar(value))
                error('evaluate_struct_expression:InvalidRecursiveOption', ...
                    'Option Recursive must be a logical scalar.');
            end

            opts.Recursive = value;
            i = i + 2;
            continue;
        end

        sources{end + 1} = arg; %#ok<AGROW>
        i = i + 1;
    end
end

function expr = normalize_expression(expr)
    expr = strtrim(expr);
    expr = regexprep(expr, '\s*([+\-*/^()])\s*', '$1');
    expr = regexprep(expr, '\s+', '*');

    if isempty(expr)
        error('evaluate_struct_expression:EmptyExpression', 'Expression must not be empty.');
    end

    if ~isempty(regexp(expr, '[^A-Za-z0-9_+\-*/^().]', 'once'))
        error('evaluate_struct_expression:InvalidCharacter', 'Expression contains unsupported characters: %s', expr);
    end

end

function [symbol_table, symbol_paths] = collect_symbols(source, source_path, requested_names, symbol_table, symbol_paths, recursive)
    names = fieldnames(source);

    for i = 1:numel(names)
        name = names{i};
        value = source.(name);
        current_path = sprintf('%s.%s', source_path, name);

        if recursive && isstruct(value) && isscalar(value)
            [symbol_table, symbol_paths] = collect_symbols(value, current_path, requested_names, symbol_table, symbol_paths, recursive);
            continue;
        end

        if ~(is_scalar_real(value) && isvarname(name) && any(string(name) == requested_names))
            continue;
        end

        if isfield(symbol_table, name)
            error('evaluate_struct_expression:NameConflict', 'Symbol "%s" is defined in both %s and %s.', name, symbol_paths.(name), current_path);
        end

        symbol_table.(name) = value;
        symbol_paths.(name) = current_path;
    end

end

function tf = is_scalar_real(value)
    tf = isnumeric(value) && isscalar(value) && isfinite(value) && isreal(value);
end
