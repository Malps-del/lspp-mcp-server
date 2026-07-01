# Workflows

## Natural Language To Parameters

Map common phrases before calling tools:

- "mises", "von Mises", "von_mises stress" -> `variable="von_mises"`
- "有效塑性应变", "effective plastic strain" -> `variable="effective_plastic_strain"`
- "第 1 到 30 帧" -> `state_index` values `1..30`
- "等轴测", "isometric" -> `view="isometric"`
- "关闭坐标轴" -> `show_triad=False`
- "关闭图例" -> `show_legend=False`
- "云图显示层级 50" -> `range_level=50`
- "viridis", "plasma", "cividis", "turbo", "jet", "seismic", "灰度", "热力图", "蓝红" -> `color_style`
- "加载这个调色板文件" -> `color_palette_path`

Prefer explicit output folders and deterministic zero-padded names such as `von_mises_state_001.png`.

## Single Contour Image

Use `export_d3plot_contour` for one state. Set:

- `d3plot_path`: absolute path to `d3plot` or `d3part`
- `output_png`: output image path, even when the extension is not `.png`
- `variable`, `state_index`, `view`
- optional `part_ids`, `show_legend`, `show_triad`, `background`, `window_size`, `range_level`, `color_style`, `color_palette_path`, `image_format`, `overwrite`

The tool returns `output_png`, `output_image`, `image_format`, `generated_cfile`, `log_file`, `ok`, and `message`.

## Multi-State Contour Images

Preferred MCP behavior: use `export_d3plot_contour_frames` when all frames share the same display options. It opens LS-PrePost once, loads the d3plot/d3part once, then repeats `state` and `print` for each requested frame.

Use repeated `export_d3plot_contour` calls only when there are very few frames or each frame needs different options.

For `export_d3plot_contour_frames`, map requests as:

- "第 1 到 30 帧" -> `state_start=1`, `state_end=30`
- "第 1、5、10 帧" -> `state_indices=[1, 5, 10]`
- "0.002s、0.004s 的云图" -> `state_times=[0.002, 0.004]`
- "front 和 isometric 两个视角" -> `views=["front", "isometric"]`
- "图片在该目录下新建文件夹保存" -> create/pass `output_dir`
- "文件名按 ... 命名" -> `filename_template`

Do a one-frame or two-frame probe before large runs when using mesh/outline toggles, unusual formats, or untested display commands.

## Result Inspection And Metrics

Use `inspect_lsdyna_results` when the user asks what result files exist, whether a run is complete, or what post-processing can be done from a case directory.

Use `infer_d3plot_state_times` before time-based image export when the user gives physical times instead of state indices.

Use `extract_lsdyna_metrics` after a curve has been exported to CSV. Map "峰值", "峰值时间", "终值", "均值", "RMS", "冲量", or "积分" to the returned metrics.

Use `compare_lsdyna_cases` when the user asks for a multi-case summary table or parameter-vs-response comparison from repeated case folders.

## Keyword Deck Inspection

Use `inspect_keyword_deck` to summarize a `k` file without modifying it. It follows `*INCLUDE` cards when enabled and reports keyword counts, include files, database output cards, entity summaries, and blast/impact/ALE/FSI-related keyword families.

Use `inspect_keyword_fields` when the user asks what values are set inside keywords, which fields use `&parameter` references, or how `*PARAMETER` / `*PARAMETER_EXPRESSION_LOCAL` values flow through the deck. Treat `*PARAMETER` as a normal keyword schema, not as a separate special-purpose tool.

Use `check_keyword_deck` when the user asks whether a model is ready for post-processing or solving. It checks missing includes, common control cards, d3plot/d3part/glstat/matsum/nodout/database extent availability, and common blast/ALE/FSI consistency hints.

## Simple Keyword Mesh Generation

Use `create_lsdyna_plate_mesh` for requests such as "generate a rectangular shell plate", "make a fixed-edge plate mesh", or "create a target plate k file". Map length, width, thickness, and either `elem_size` or `nx`/`ny`. Use `fixed_edges=true` only when the user asks for fixed edges or clamped boundaries.

Use `create_lsdyna_block_mesh` for requests such as "generate a regular solid block", "make a water/air/domain block mesh", or "create a hexahedral block k file". Map length, width, height, and either `elem_size` or `nx`/`ny`/`nz`.

Use `create_lsdyna_cylinder_shell_mesh` for requests such as "generate a cylindrical shell", "make a tube shell mesh", or "create a shell cylinder k file". Map radius, height, thickness, and either `elem_size` or `n_circumference`/`nz`. Use `cap_bottom`/`cap_top` when the user asks for closed ends. Closed ends default to `cap_mesh="quad"` with a square core and transition rings; this requires `n_circumference` divisible by 8. Use `cap_mesh="tri"` only when the user accepts triangular cap elements. Use `fixed_bottom` or `fixed_top` only when the user asks for constrained rings.

After generating a simple mesh, inspect the returned `precheck`. If the user asked for a persistent report, pass `precheck_json`. If the user asked to see the model, call `preview_lsdyna_keyword_model` to create a LS-PrePost screenshot.

Use `precheck_lsdyna_keyword_model` for existing `k` files when the user asks about mesh counts, missing node references, duplicate ids, degenerate elements, bounds, part element counts, or solver-readiness checks.

Do not use these simple generators for arbitrary CAD geometry, unstructured meshing, swept meshes, contact setup, ALE/FSI assembly, or production blast models unless a controlled template exists. For those cases, first gather the intended workflow and preferably a hand-recorded LS-PrePost cfile snippet.

## Regular Cylindrical Assembly Generation

Use `create_lsdyna_cylindrical_assembly` for requests such as "generate a closed cylindrical shell with neutral filling and regular attached blocks" or "make a cylindrical shell assembly with point masses". Map shell radius, height, thickness, and either `elem_size` or `n_circumference`/`nz`.

Use `attached_blocks` for regular solid block arrays on or near the shell surface. Map count around circumference, count along height, radial thickness, circumferential width, block height, radial gap, and optional starting angle or z margin.

Use `mass_points` only when the user wants simplified concentrated masses instead of meshed solid blocks. Map count around circumference, count along height, mass per point, radial offset, and optional starting angle or z margin.

Use `internal_fill` only for neutral geometric occupancy setup. It can auto-create a cylindrical `*INITIAL_VOLUME_FRACTION_GEOMETRY` fill when given `fmsid`, `bammg`, `fammg`, and optional fill radius.

For similar S-ALE cylindrical assemblies with regular discrete attached blocks, preserve the two validated modeling choices from the runnable reference case:

- Prefer `*ALE_STRUCTURED_FSI` for coupling S-ALE domains to the Lagrangian block/shell structure. Do not default to `*CONSTRAINED_LAGRANGE_IN_SOLID` for these templates unless the user explicitly needs a CLIS workflow.
- Model regular attached mass blocks with `*MAT_RIGID_DISCRETE_TITLE` when the intent is discrete rigid lumped blocks rather than deformable solids or ordinary rigid parts.

After generating an assembly, inspect the returned `check`. If visual confirmation is needed, call `preview_lsdyna_keyword_model`.

## S-ALE Fluid Domain Generation

Use `create_lsdyna_sale_fluid_domain` for requests such as "generate an S-ALE fluid domain", "make a structured ALE air/water domain", or "create an axisymmetric S-ALE domain". Map domain extents to `x_range`, `y_range`, and, for 3D domains, `z_range`. Map grid divisions to `nx`, `ny`, and `nz`.

Use `axisymmetric=true` when the user asks for an axisymmetric S-ALE domain. In that case, do not pass `z_range`; the generated mesh uses two structured control-point directions and `*ALE_STRUCTURED_MULTI-MATERIAL_GROUP_AXISYM`.

Use `materials` to preserve user-specified AMMG, material ID, EOS ID, density, reference pressure, and names. If the user does not provide real material data, keep the generated cards as placeholders and say so.

Use `fills` for neutral initial occupancy setup. The fill geometry options are the same as `create_initial_volume_fraction_geometry`.

After generating the domain, inspect the returned `check`. If the model is intended to interact with Lagrangian structure, the current tool does not automatically create FSI coupling; ask for or generate that as a separate controlled step. For structured S-ALE coupling templates, prefer `*ALE_STRUCTURED_FSI` as the default FSI keyword family.

## ALE Volume Filling

Use `inspect_initial_volume_fraction_geometry` when the user asks how an existing ALE deck fills materials, or when you need to identify background ALE mesh ID, background AMMG, container types, and fill AMMG IDs.

Use `create_initial_volume_fraction_geometry` to write a standalone include file containing only `*INITIAL_VOLUME_FRACTION_GEOMETRY`. Use `append_initial_volume_fraction_geometry` when the user asks to add the fill setup to an existing `k` file.

Map neutral fill requests as:

- cylindrical region -> `geometry="cylinder"`, `point0`, `point1`, `radius`
- conical region -> `geometry="cone"`, `point0`, `point1`, `radii=[r1, r2]`
- box region -> `geometry="box"`, `min`, `max`, optional `lcsid`
- sphere region -> `geometry="sphere"`, `center`, `radius`
- side of a plane -> `geometry="plane"`, `point`, `normal`
- shell/segment container -> `geometry="part"` or `geometry="segment"`

Keep this feature limited to initial volume fraction geometry setup. Do not generate explosive material models, detonation cards, or weapon-effect calculations.

## Parameterized Case Generation

Use `generate_lsdyna_keyword_field_sweep` when the user asks for a straightforward one-field sweep from a `k` file. The target can be any concrete keyword field, not only `*PARAMETER`. Prefer this route for direct edits to cards such as `*CONTROL_TERMINATION`, `*DATABASE_*`, `*INITIAL_DETONATION`, `*MAT_*`, `*EOS_*`, `*BOUNDARY_*`, or other explicit keyword values.

For complex natural-language targets, first use `inspect_keyword_fields` or `inspect_keyword_deck` to identify the keyword, instance, line, field number/name, and current value. Then call `generate_lsdyna_keyword_field_sweep` with either `file_line_number + field_number` or `keyword + keyword_instance + line_number_in_block + field_number/field_name`.

Use `generate_lsdyna_parameter_sweep` only as a convenience when the target is explicitly defined in a `*PARAMETER` card. Map phrases such as "modify expDp from 2.1 to 2.9 every 0.1" to `parameter_name="expDp"`, `start=2.1`, `end=2.9`, and `step=0.1`.

Use `preview_only=true` when output naming or parameter detection is uncertain. For repeated output, use a fresh `output_dir` or set `overwrite=true` only when the user expects existing files to be reused.

When the user wants MCP/Codex to generate LS-DYNA parameterized cases from the existing desktop Batch Case Generator project:

1. Use `validate_case_generator_integration` first if the current session has not already confirmed the adapter works.
2. Use `inspect_lsdyna_case_config` on the JSON config saved by the desktop app to summarize selected parameters, constraints, sampling method, and output settings.
3. Use `generate_lsdyna_cases` with `preview_only=true` for a dry run when output paths, constraints, or naming templates are uncertain.
4. Use `generate_lsdyna_cases` with `preview_only=false` to export cases. Pass overrides such as `sample_count`, `random_seed`, `output_dir`, `method`, `folder_template`, and `file_template` only when the user asks to change the saved config behavior.

Use the saved JSON config route for multi-parameter studies, constraints, random sampling, LHS, Excel-driven cases, or any setup that was authored in the desktop GUI.

Do not duplicate the case generator logic inside the MCP. The adapters intentionally call the external project's `ConfigService`, `KFileParser`, `CaseGeneratorService`, `ConstraintService`, `KFileReplacer`, and `ExportService`.

## Solver Execution

Use `validate_lsdyna_solver` before the first solve in a session or after config changes. It checks `lsdyna_exe` and the work directory.

Use `run_lsdyna_solver` to launch a solve from a `k` file. Recommended mapping:

- "先看命令" or uncertain arguments -> `dry_run=true`
- "用 16 核" -> `ncpu=16`
- "memory 200m" -> `memory="200m"`
- "显示终端", "实时看进度", or "需要输入 sw1/sw2/stop" -> `show_console=true`
- Extra LS-DYNA key/value options -> `additional_args=["key=value"]` only when they are explicit and safe
- If no work directory is specified, use the `k` file parent directory

The default background mode captures output and waits for completion or timeout. `show_console=true` opens a Windows console for the solver and is the right choice when the user wants LS-DYNA's native interactive commands.

After `run_lsdyna_solver`, inspect the returned `diagnostics`. If `completion_state` is not `normal_termination`, report the most important findings before doing post-processing.

Use `diagnose_lsdyna_logs` when the user only wants to inspect an existing run directory or when a solve was launched outside MCP. It reads `d3hsp`, `messag`, and `status.out` when present.

## Curves

Use `extract_d3plot_node_history` for d3plot node history curves when the result is not in ASCII/binout or the user asks for history from d3plot.

Use `extract_ascii_curve` for `nodout`, `matsum`, `glstat`, `rcforc`, and similar ASCII outputs.

Use `inspect_binout_contents` before extracting from unfamiliar binout files. It uses the lasso backend and reports top-level blocks, variable names, shapes, dtypes, and time ranges.

Use `extract_binout_curve` for `binout`, `binout0000`, or `binout*`. Prefer `backend="lasso"` or `backend="auto"` for large MPP binout shards; the lasso backend reads files directly and does not start LS-PrePost. Use `backend="lsprepost"` only for legacy binaski workflows, small files, or cases where the GUI/binaski path is known to work.

When the user passes `binout0000` and sibling `binout*` files exist, the lasso backend should read the whole shard set through a glob. Keep all matched files inside `allowed_roots`.

For lasso extraction, use variable paths such as `glstat/kinetic_energy`, `matsum/internal_energy`, `nodout/y_displacement`, `dbfsi/pres`, `dbfsi/fx`, `dbfsi/fy`, `dbfsi/fz`, `trhist/sx`, `trhist/sy`, and `trhist/sz`. For 2D variables, pass zero-based `entity_index` to export one entity as `time,value`; omit it to export all entities with `ids` or `legend_ids` as column labels.

Use `extract_binout_metrics` for direct binout metrics such as peak, time at peak, min, final value, and positive impulse. For `trhist`, use `variable="p_proxy"` or `pressure_proxy=true` to compute `p_proxy = -(sx + sy + sz) / 3` and underwater-pressure summaries such as peak pressure, arrival time, shock impulse, and post-shock/bubble impulse.

## Many Cases

Use `batch_postprocess_cases` when multiple case directories share a task configuration. Resolve relative task paths against each case directory. Check `summary.json` and `summary.csv` after the batch.
