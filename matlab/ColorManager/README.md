# ColorManager + PlotStyleManager

## ColorManager

Manages color palettes and name-to-color bindings for scientific plots.

### Construction

```matlab
cm = ColorManager()                          % auto-locate colors.csv / colors.txt
cm = ColorManager(Path='path/colors.csv')    % database mode: explicit file path
cm = ColorManager(RGB=rgb)                   % manual mode: Nx3 RGB matrix
cm = ColorManager(Hex=["#FF0000","#00FF00"])  % manual mode: hex string array
```

**Database mode** — loads palettes from a CSV file. Use `list()` / `select()` to browse and pick.

**Manual mode** — colors provided directly. No CSV file is loaded. `Path`, `RGB`, `Hex` are mutually exclusive; provide at most one.

```matlab
% Manual mode examples
cm = ColorManager(RGB=[0.12 0.47 0.71; 0.85 0.65 0.16; 0.28 0.63 0.64]);
cm = ColorManager(Hex=["#1F77B4", "#DAA628", "#47A1A2", "#E07F86"]);
```

### API

| Method                      | Description                                         |
| --------------------------- | --------------------------------------------------- |
| `list()`                    | List all palettes                                   |
| `list(nColors)`             | List palettes with >= nColors (sorted by count)     |
| `select(nColors, rank)`     | Select the rank-th palette. Returns `obj`           |
| `preview()`                 | Preview current palette (swatches + sample curves)  |
| `preview(nColors, rank)`    | Preview the rank-th palette matching nColors        |
| `browse()`                  | Browse all palettes with navigation controls        |
| `browse(nColors)`           | Browse palettes with >= nColors                     |
| `assign('name', idx)`       | Bind a name to a color index. Returns `obj`         |
| `get_name('name')`          | Get color by assigned name                          |
| `get_idx(idx)`              | Get color by index                                  |

Options: `ColorManager(Strict=true)` makes invalid operations throw errors instead of warnings. `ColorManager(Quiet=true)` suppresses load/select messages.

### Manual mode behavior

| Method         | Behavior                                              |
| -------------- | ----------------------------------------------------- |
| `select()`     | Ignored (prints a one-line message, silent in quiet mode) |
| `get_idx(idx)` | Cycles automatically when `idx > n`: `mod(idx-1, n)+1` |
| `list()` / `preview()` / `browse()` | Work on the single provided palette    |

### Color database format

Each line in `colors.csv` (or `.txt`) is comma-separated hex colors:

```csv
#1F77B4,#DAA628,#47A1A2
#E07F86,#8FA2CD,#F8BC7E,#CC976B
#B22222,#000080
```

Place the file alongside `ColorManager.m`, or pass a path via `ColorManager(Path=...)`.

---

## PlotStyleManager

Manages marker, line style, line width, and other plot appearance properties.

```matlab
psm = PlotStyleManager();
psm.assign('Proposed', Marker='o', LineStyle='-',  LineWidth=2,   MarkerFaceColor='auto');
psm.assign('Baseline', Marker='s', LineStyle='--', LineWidth=2,   MarkerFaceColor='auto');

s = psm.get_style('Proposed');   % returns name-value cell array
plot(x, y, s{:});                 % expand into plot()
```

### API

| Method                            | Description                                                          |
| --------------------------------- | -------------------------------------------------------------------- |
| `PlotStyleManager()`              | Construct                                                            |
| `assign('name', Marker='o', ...)` | Bind style properties to a name. Returns `obj`                       |
| `get_style('name')`               | Return NV cell array; use as `plot(..., psm.get_style(n){:})`        |

### Style options for `assign`

| Option            | Example                      |
| ----------------- | ---------------------------- |
| `Marker`          | `'o'`, `'s'`, `'^'`, `'d'`   |
| `MarkerSize`      | `8`, `10`                    |
| `MarkerEdgeColor` | `'k'`, `'r'`, `'none'`       |
| `MarkerFaceColor` | `'r'`, `'auto'`, `'none'`    |
| `LineStyle`       | `'-'`, `'--'`, `':'`, `'-.'` |
| `LineWidth`       | `1.5`, `2`                   |

---

## Combined usage

```matlab
% Colors (manual mode — no CSV needed)
cm = ColorManager(RGB=[0.12 0.47 0.71; 0.85 0.65 0.16; 0.28 0.63 0.64; 0.88 0.31 0.36]);
cm.assign('Proposed', 1).assign('Baseline', 2).assign('Oracle', 3).assign('Ablation', 4);

% Styles
psm = PlotStyleManager();
psm.assign('Proposed',  Marker='o', LineStyle='-',  LineWidth=2,   MarkerFaceColor='auto');
psm.assign('Baseline',  Marker='s', LineStyle='--', LineWidth=2,   MarkerFaceColor='auto');
psm.assign('Oracle',    Marker='^', LineStyle=':',  LineWidth=1.5);
psm.assign('Ablation',  Marker='d', LineStyle='-.', LineWidth=2.5, MarkerSize=10);

% Plot
x = linspace(0, 2*pi, 24)';
figure; hold on;
for n = ["Proposed", "Baseline", "Oracle", "Ablation"]
    s = psm.get_style(n);
    plot(x, sin(x), s{:}, Color=cm.get_name(n), DisplayName=n);
end
legend;
```
