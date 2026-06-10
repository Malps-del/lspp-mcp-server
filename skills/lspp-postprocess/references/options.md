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

## Keyword Deck Checks

Current keyword inspection recognizes common LS-DYNA preprocessing families:

- Control/database cards such as `*CONTROL_TERMINATION`, `*CONTROL_TIMESTEP`, `*DATABASE_BINARY_D3PLOT`, `*DATABASE_BINARY_D3PART`, `*DATABASE_GLSTAT`, `*DATABASE_MATSUM`, `*DATABASE_NODOUT`, `*DATABASE_EXTENT_BINARY`
- Blast/ALE/FSI cards such as `*MAT_HIGH_EXPLOSIVE_BURN`, `*EOS_JWL`, `*INITIAL_DETONATION`, `*INITIAL_VOLUME_FRACTION_GEOMETRY`, `*ALE_STRUCTURED_MESH`, `*CONSTRAINED_LAGRANGE_IN_SOLID`, `*DATABASE_FSI`, `*DATABASE_TRACER`
- Model organization cards such as `*INCLUDE`, `*PART`, `*SECTION_*`, `*MAT_*`, `*EOS_*`, `*SET_*`, `*CONTACT_*`, `*LOAD_*`, `*BOUNDARY_*`

Treat these tools as read-only diagnostics. If a deck uses separate files that are not connected through `*INCLUDE`, pass the additional files through `extra_k_paths` or ask the user which file is the true solver entrypoint.

## Batch Case Generator Adapter

The MCP can reuse a separate LS-DYNA Batch Case Generator project through config values:

- `case_generator_python`: Python executable for the external project's virtual environment.
- `case_generator_src`: `src` directory for the external project.

The JSON config path, `k_file_path`, Excel input, output directory, and support files must still be inside MCP `allowed_roots`. Use `overwrite=true` only when the user expects an existing output directory to be reused; the adapter does not delete existing content.

## Solver Config And Logs

`lsdyna_exe` is the configured LS-DYNA solver executable. Keep it blank until the user has a known local solver path.

Solver execution remains bounded by `allowed_roots`: the input `k` file, work directory, and diagnostic log files must be inside the whitelist.

`diagnose_lsdyna_logs` looks for common files:

- `d3hsp`
- `messag`, `messag.*`, `message`, `message.*`
- `status.out`, `status`, `status.*`

Treat log diagnosis as a heuristic summary. Always surface detected errors or warnings and the latest time/cycle, but do not claim a model is physically valid just because the solver terminated normally.
