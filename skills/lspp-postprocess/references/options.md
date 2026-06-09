# Options

## Paths And Config

`workspace_root` is the base for relative paths. `allowed_roots` is the safety whitelist for all readable/writable input and output paths.

If the user requests a path outside `allowed_roots`, update `config.yaml` only when they explicitly want this MCP to access that folder. Do not bypass the whitelist.

## Contour Variables

Common `d3plot_fringe` variables include:

- `von_mises`
- `effective_plastic_strain`
- `pressure`
- `x_displacement`, `y_displacement`, `z_displacement`, `resultant_displacement`
- `x_velocity`, `y_velocity`, `z_velocity`, `resultant_velocity`
- `x_acceleration`, `y_acceleration`, `z_acceleration`, `resultant_acceleration`
- `x_coordinate`, `y_coordinate`, `z_coordinate`

When a requested variable is unknown, call `list_supported_variables("d3plot_fringe")` or inspect `config.yaml`.

## Image Formats

The current MCP validates image export formats by output extension or optional `image_format`.

Verified formats in LS-PrePost 4.12 cfile automation:

- `png`
- `jpg` (`jpeg` aliases to `jpg`)
- `bmp`
- `gif`
- `wrl` (`vrml` and `vrml2` alias to `wrl`; the cfile uses `print vrml`)

Formats shown in the LS-PrePost GUI such as `pdf`, `tif`, `pcx`, `ps`, `eps`, `tex`, `svg`, and `pgf` were not stable with the same automated `print` command in the tested LS-PrePost 4.12 environment. Do not promise them unless newly verified.

## Views

Supported MCP view names:

- `front`
- `back`
- `top`
- `bottom`
- `left`
- `right`
- `isometric`

`isometric` renders as the LS-PrePost command `isometric x`.

## Display Options

Use `range_level` for requests such as "云图显示层级 50"; this emits:

```text
range level 50
range pal update
```

Use `show_legend` and `show_triad` for legend and coordinate-axis visibility.

Use `background="white"` or `background="black"`.

Mesh/outline commands can be toggle-like. Probe before batching and record the exact commands in generated cfiles.
