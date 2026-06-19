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

Use `color_style` for contour palette requests. Built-in style names are returned by `list_contour_color_styles`. Common choices include:

- Perceptually uniform: `viridis`, `plasma`, `inferno`, `magma`, `cividis`
- Sequential: `greys`, `purples`, `blues`, `greens`, `oranges`, `reds`, `ylorbr`, `ylorrd`, `orrd`, `purd`, `rdpu`, `bupu`, `gnbu`, `pubu`, `ylgnbu`, `pubugn`, `bugn`, `ylgn`
- Sequential 2: `binary`, `gist_yarg`, `gist_gray`, `gray`, `bone`, `pink`, `spring`, `summer`, `autumn`, `winter`, `cool`, `wistia`, `hot`, `afmhot`, `gist_heat`, `copper`
- Diverging: `piyg`, `prgn`, `brbg`, `puor`, `rdgy`, `rdbu`, `rdylbu`, `rdylgn`, `spectral`, `coolwarm`, `bwr`, `seismic`
- Qualitative: `pastel1`, `pastel2`, `paired`, `accent`, `dark2`, `set1`, `set2`, `set3`, `tab10`, `tab20`, `tab20b`, `tab20c`
- Miscellaneous: `flag`, `prism`, `ocean`, `gist_earth`, `terrain`, `gist_stern`, `gnuplot`, `gnuplot2`, `cmrmap`, `cubehelix`, `brg`, `gist_rainbow`, `rainbow`, `jet`, `turbo`, `nipy_spectral`, `gist_ncar`

The older aliases `viridis_like`, `cividis_like`, `blue_red`, `thermal`, and `grayscale` remain supported.

Color styles are applied through LS-PrePost palette commands, not image post-processing:

```text
range pal load "path/to/palette.txt"
range pal update
```

For one-off custom files, pass `color_palette_path`. For reusable custom styles, register the file in `config.yaml`:

```yaml
color_palettes:
  lab_style: "D:/palettes/lab_style.txt"
```

Built-in palettes are generated to the output `.lspp_mcp/palettes/` folder with one extra row beyond the current `range_level`. Row numbering starts at 0: for `range_level=50`, write rows `0..50`. Row 0 is the low-value end and row `range_level` is the high-value end; LS-PrePost displays the highest row at the top of the colorbar. Built-in files use normalized RGB channels from 0 to 1. When using built-in color styles, prefer setting `range_level` explicitly for reproducible color bands.

Mesh/outline commands can be toggle-like. Probe before batching and record the exact commands in generated cfiles.

## Result Metrics

Use `inspect_lsdyna_results` before broad post-processing requests. It identifies result files, solver logs, completion state, and available post-processing actions.

Use `extract_lsdyna_metrics` on CSV curves when the user asks for peak values, time at peak, final values, mean/RMS, or impulse/integral. Use `compare_lsdyna_cases` when the same metric should be extracted across many case folders.

## Keyword Deck Checks

Current keyword inspection recognizes common LS-DYNA preprocessing families:

- Control/database cards such as `*CONTROL_TERMINATION`, `*CONTROL_TIMESTEP`, `*DATABASE_BINARY_D3PLOT`, `*DATABASE_BINARY_D3PART`, `*DATABASE_GLSTAT`, `*DATABASE_MATSUM`, `*DATABASE_NODOUT`, `*DATABASE_EXTENT_BINARY`
- Blast/ALE/FSI cards such as `*MAT_HIGH_EXPLOSIVE_BURN`, `*EOS_JWL`, `*INITIAL_DETONATION`, `*INITIAL_VOLUME_FRACTION_GEOMETRY`, `*ALE_STRUCTURED_MESH`, `*CONSTRAINED_LAGRANGE_IN_SOLID`, `*DATABASE_FSI`, `*DATABASE_TRACER`
- Model organization cards such as `*INCLUDE`, `*PART`, `*SECTION_*`, `*MAT_*`, `*EOS_*`, `*SET_*`, `*CONTACT_*`, `*LOAD_*`, `*BOUNDARY_*`

Treat these tools as read-only diagnostics. If a deck uses separate files that are not connected through `*INCLUDE`, pass the additional files through `extra_k_paths` or ask the user which file is the true solver entrypoint.

`inspect_keyword_fields` adds structured field parsing for selected keyword schemas and comment-labeled rows. It currently handles `*PARAMETER`, `*PARAMETER_EXPRESSION_LOCAL`, common `*CONTROL_*`, `*DATABASE_*`, ALE setup, tracer, boundary, and initial-condition cards used by the blast/ALE examples. It marks `&parameter` references in field values and returns a derived `parameter_summary`.

## Simple Preprocessing Meshes

`create_lsdyna_plate_mesh` writes a rectangular shell plate keyword deck with `*NODE`, `*ELEMENT_SHELL`, `*PART`, `*SECTION_SHELL`, `*MAT_ELASTIC`, common control/database cards, and optional fixed-edge node set/SPC constraints. The caller must provide length, width, thickness, and either `elem_size` or `nx`/`ny`.

`create_lsdyna_block_mesh` writes a regular hexahedral solid block keyword deck with `*NODE`, `*ELEMENT_SOLID`, `*PART`, `*SECTION_SOLID`, `*MAT_ELASTIC`, and common control/database cards. The caller must provide length, width, height, and either `elem_size` or `nx`/`ny`/`nz`.

`create_lsdyna_cylinder_shell_mesh` writes a regular cylindrical shell keyword deck with `*NODE`, `*ELEMENT_SHELL`, `*PART`, `*SECTION_SHELL`, `*MAT_ELASTIC`, and common control/database cards. The caller must provide radius, height, thickness, and either `elem_size` or `n_circumference`/`nz`. Optional `cap_bottom` and `cap_top` close the cylinder. By default `cap_mesh="quad"` creates all-quad caps with a square core and circular-to-square transition rings, so `n_circumference` must be divisible by 8. `cap_radial_layers` controls the number of transition bands and `cap_core_fraction` controls the square-core half side relative to radius. `cap_mesh="tri"` keeps the older center-node triangular caps. Optional `fixed_bottom` and `fixed_top` create ring node sets and SPC constraints.

These generators return mesh counts and run `precheck_lsdyna_keyword_model`. Treat the generated material as a placeholder unless the user explicitly provides real material parameters.

`precheck_lsdyna_keyword_model` reports node count, shell/solid element counts, part element counts, model bounds, duplicate node/element ids, missing node references, unused nodes, degenerate elements, and the existing keyword deck checks.

`preview_lsdyna_keyword_model` opens a `k` file through LS-PrePost and exports a model screenshot. Supported preview formats follow the same stable set used by contour images: `png`, `jpg`, `bmp`, `gif`, and `wrl`.

## Regular Cylindrical Assemblies

`create_lsdyna_cylindrical_assembly` writes a regular cylindrical assembly keyword deck. It supports a closed or open cylindrical shell, optional neutral `*INITIAL_VOLUME_FRACTION_GEOMETRY` internal filling, regular solid attached block arrays, and regular `*ELEMENT_MASS` point arrays.

For attached blocks, each specification should provide `count_circumference`, `count_height`, `radial_thickness`, `circumferential_width`, and `height`. Optional fields include `radial_gap`, `start_angle_deg`, `z_margin`, `part_id`, `section_id`, `material_id`, and placeholder elastic material values.

For mass points, each specification should provide `count_circumference`, `count_height`, and `mass`. Optional fields include `radial_offset`, `start_angle_deg`, and `z_margin`.

`check_lsdyna_cylindrical_assembly` reports mesh counts, shell boundary/nonmanifold edges, concentrated mass statistics, duplicate ids, missing node references, degenerate elements, and keyword-deck checks. Use it after generation and before preview or solving.

## S-ALE Fluid Domains

`create_lsdyna_sale_fluid_domain` writes a regular S-ALE fluid-domain keyword deck. It supports 3D rectangular domains and axisymmetric domains, structured mesh control points, S-ALE boundary faces, structured multi-material groups, optional placeholder material/EOS cards, and optional neutral `*INITIAL_VOLUME_FRACTION_GEOMETRY` fills.

For 3D domains, provide `x_range`, `y_range`, `z_range`, `nx`, `ny`, and `nz`. For axisymmetric domains, set `axisymmetric=true` and provide `x_range`, `y_range`, `nx`, and `ny`.

`materials` should list AMMG definitions with `ammg`, `mid`, optional `eosid`, optional `density`, optional `pref`, and optional `name`. The list must include `background_ammg`.

`fills` uses the same geometry mapping as `create_initial_volume_fraction_geometry`. Use it for neutral initial occupancy such as a box, cylinder, sphere, plane, part, or segment region.

`check_lsdyna_sale_fluid_domain` reports structured mesh count, control point count, multi-material-group type, boundary face availability, initial volume-fraction block count, and keyword-deck issues.

## ALE Volume Filling

`create_initial_volume_fraction_geometry` writes a standalone `*INITIAL_VOLUME_FRACTION_GEOMETRY` block. Required inputs are `fmsid`, `fmidtyp`, `bammg`, `ntrace`, and one or more `fills`. Each fill has `geometry`, `fillopt`, `fammg`, optional `velocity`, and geometry-specific fields.

Supported fill geometries are `part`, `segment`, `plane`, `cylinder`, `cone`, `box`, `sphere`, and `function`. For `cylinder`, provide `point0`, `point1`, and `radius`; for `box`, provide `min` and `max`; for `sphere`, provide `center` and `radius`.

`append_initial_volume_fraction_geometry` copies an existing keyword deck and inserts the generated fill block before `*END` by default.

`inspect_initial_volume_fraction_geometry` parses existing `*INITIAL_VOLUME_FRACTION_GEOMETRY` blocks, including decks without comment labels, and returns card 1 values plus each fill action's container type, fill option, AMMG, velocity, and geometry details.

## Batch Case Generator Adapter

The MCP can reuse a separate LS-DYNA Batch Case Generator project through config values:

- `case_generator_python`: Python executable for the external project's virtual environment.
- `case_generator_src`: `src` directory for the external project.

The JSON config path, `k_file_path`, Excel input, output directory, and support files must still be inside MCP `allowed_roots`. Use `overwrite=true` only when the user expects an existing output directory to be reused; the adapter does not delete existing content.

`generate_lsdyna_keyword_field_sweep` is the direct natural-language entry point for one keyword field. It accepts either explicit `values` or `start`/`end`/`step`, defaults to `output_mode="separate_folders"`, and copies direct `*INCLUDE` files unless `copy_include_files=false`. It can target a field by `file_line_number + field_number`, or by `keyword + keyword_instance + line_number_in_block + field_number/field_name`.

`generate_lsdyna_parameter_sweep` is a convenience wrapper for one `*PARAMETER` variable. Do not treat `*PARAMETER` as the only supported case-generation style. When the model does not use `*PARAMETER`, inspect the deck and call `generate_lsdyna_keyword_field_sweep` on the actual keyword field.

Neither simple sweep tool replaces the full JSON-config route when the study needs multiple selected fields, constraints, random/LHS sampling, Excel input, or custom generator state from the desktop app.

## Solver Config And Logs

`lsdyna_exe` is the configured LS-DYNA solver executable. Keep it blank until the user has a known local solver path.

Solver execution remains bounded by `allowed_roots`: the input `k` file, work directory, and diagnostic log files must be inside the whitelist.

`diagnose_lsdyna_logs` looks for common files:

- `d3hsp`
- `messag`, `messag.*`, `message`, `message.*`
- `status.out`, `status`, `status.*`

Treat log diagnosis as a heuristic summary. Always surface detected errors or warnings and the latest time/cycle, but do not claim a model is physically valid just because the solver terminated normally.
