clear;
close all;

config = struct();
config.ep = 0.1;
config.scale = 2.0;

mesh = struct();
mesh.dx = 0.1;
mesh.dy = 0.05;

example = struct();
example.mesh = mesh;

expr1 = '0.2*ep*dx';
value1 = evaluate_struct_expression(expr1, config, mesh);
fprintf('direct fields: %s -> %.16g\n', expr1, value1);

expr2 = '0.2 ep dx';
value2 = evaluate_struct_expression(expr2, config, mesh);
fprintf('direct fields: %s -> %.16g\n', expr2, value2);

expr3 = '0.2*ep*dx^2 + scale*dy';
value3 = evaluate_struct_expression(expr3, config, mesh);
fprintf('direct fields: %s -> %.16g\n', expr3, value3);

try
    evaluate_struct_expression('0.2*ep*dx', config, example);
catch ME
    fprintf('nonrecursive nested lookup -> %s\n', ME.identifier);
end

value = evaluate_struct_expression('0.2*ep*dx', config, example, Recursive= true);
fprintf('recursive nested lookup: %s -> %.16g\n', expr1, value);

try
    duplicate = struct(dx = 0.2);
    evaluate_struct_expression('dx', mesh, duplicate);
catch ME
    fprintf('name conflict -> %s\n', ME.identifier);
end
