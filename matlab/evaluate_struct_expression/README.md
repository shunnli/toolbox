# evaluate_struct_expression

Evaluate a scalar expression using fields from one or more scalar structs as symbolic variables.

## Overview

`evaluate_struct_expression` lets you write mathematical expressions that reference struct fields by their direct field names, avoiding the need to manually unpack fields or hardcode dotted access.

```matlab
config = struct('ep', 0.1);
mesh   = struct('dx', 0.1);

value = evaluate_struct_expression('0.2*ep*dx', config, mesh);
% value = 0.2 * config.ep * mesh.dx  =>  0.002
```

## Usage

```matlab
value = evaluate_struct_expression(expr, s1, s2, ...);
value = evaluate_struct_expression(expr, s1, s2, ..., Recursive=true);
```

Inputs after `expr` must be scalar structs. The expression may reference scalar
real numeric fields by field name. Callers write `dx`, not `mesh.dx`.

## Supported Expression Syntax

- Scalar numbers (e.g., `3.14`, `1e-6`)
- Field-name symbols matching struct fields (e.g., `ep`, `dx`)
- Operators: `+`, `-`, `*`, `/`, `^`
- Parentheses for grouping
- Whitespace as implicit multiplication (e.g., `"0.2 ep dx"` is equivalent to `"0.2*ep*dx"`)
- Built-in constant `pi`

The result must be a finite real scalar.

## Recursive Lookup

By default, only direct fields of the provided structs are considered. To recurse into nested scalar structs, use `Recursive = true`:

```matlab
config = struct('ep', 0.1);
example = struct('mesh', struct('dx', 0.1));

value = evaluate_struct_expression('0.2*ep*dx', config, example, Recursive=true);
```

With `Recursive=false`, only direct fields are considered. With
`Recursive=true`, nested scalar structs are searched recursively.

## Examples

Use multiple structs:

```matlab
params = struct(ep=0.05, c=2);
mesh = struct(dx=0.1, dt=0.025);

value = evaluate_struct_expression("c*dt/dx + ep", params, mesh);
```

Use whitespace as multiplication:

```matlab
value = evaluate_struct_expression("0.2 ep dx", params, mesh);
% Equivalent to 0.2*ep*dx
```

Use nested structs:

```matlab
cfg = struct(params=struct(ep=0.05), mesh=struct(dx=0.1));
value = evaluate_struct_expression("ep*dx", cfg, Recursive=true);
```

## Validation and Errors

The function rejects ambiguous or unsafe inputs:

- `expr` must be a string scalar or character vector
- at least one source struct is required
- each source must be a scalar struct
- referenced symbols must be valid MATLAB variable names
- referenced field values must be finite real numeric scalars
- duplicate symbol names across input structs raise a `NameConflict` error
- unknown symbols raise an `UnknownSymbol` error
- unsupported characters raise an `InvalidCharacter` error
- the final result must be a finite real scalar

Example conflict:

```matlab
a = struct(dx=0.1);
b = struct(dx=0.2);

value = evaluate_struct_expression("dx", a, b);
% Error: symbol dx is defined in both inputs
```

## Limitations

- Function calls such as `sin(x)` or `sqrt(x)` are not supported.
- Array-valued fields are ignored.
- Struct field names that are not valid MATLAB variable names cannot be used as
  symbols.
