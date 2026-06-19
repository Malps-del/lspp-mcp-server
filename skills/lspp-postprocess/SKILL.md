---
name: lspp-postprocess
description: Plan and execute LS-PrePost/LS-DYNA preprocessing, solving, and post-processing with the lspp MCP server. Use when Codex needs to generate simple keyword meshes, precheck or preview k files, export d3plot or d3part contour images, extract node histories, extract ASCII or binout curves, batch states or cases, choose an efficient LS-PrePost cfile strategy, configure or validate LSPP_MCP_CONFIG, handle allowed_roots/workspace paths, select image formats/views/states/variables, tune legend/range/display options, or troubleshoot LS-PrePost MCP outputs.
---

# LS-PrePost Pre/Postprocess

## Core Workflow

1. Translate the user request into source file, output path, variable, state range, view, display options, and required format.
2. Confirm the requested source and output paths are inside `allowed_roots`; when unsure, inspect `config.yaml` or ask only for missing local facts.
3. Choose the execution strategy:
   - Single contour image: use `export_d3plot_contour`.
   - Node history: use `extract_d3plot_node_history`.
   - ASCII curve: use `extract_ascii_curve`.
   - Binout curve: use `extract_binout_curve`.
   - Many cases with the same task list: use `batch_postprocess_cases`.
   - Many states/times/views from the same d3plot/d3part: use `export_d3plot_contour_frames` when all frames share the same display settings.
   - Result directory inspection and metrics: use `inspect_lsdyna_results`, `extract_lsdyna_metrics`, and `compare_lsdyna_cases`.
   - Simple one-field sweeps from a `k` file: use `generate_lsdyna_keyword_field_sweep` when the target is a concrete keyword field, and use `generate_lsdyna_parameter_sweep` only as a convenience when the model uses `*PARAMETER`.
   - Parameterized LS-DYNA case generation from an existing Batch Case Generator JSON config: validate with `validate_case_generator_integration`, inspect with `inspect_lsdyna_case_config`, then preview/export with `generate_lsdyna_cases`.
   - LS-DYNA solver execution: validate with `validate_lsdyna_solver`, dry-run or launch with `run_lsdyna_solver`, and inspect `d3hsp`/`messag`/`status.out` with `diagnose_lsdyna_logs`. Use `show_console=true` when the user wants a visible LS-DYNA console for live progress and manual solver commands.
   - Keyword deck inspection: use `inspect_keyword_deck` for read-only summaries, `inspect_keyword_fields` for structured keyword fields and `&parameter` references, and `check_keyword_deck` for preprocessing/database-output checks.
   - Simple keyword mesh generation: use `create_lsdyna_plate_mesh` for rectangular shell plates, `create_lsdyna_block_mesh` for regular hexahedral blocks, and `create_lsdyna_cylinder_shell_mesh` for regular cylindrical shell meshes. Follow with `precheck_lsdyna_keyword_model` and `preview_lsdyna_keyword_model` when the user wants a QA report or LS-PrePost preview image.
   - Regular cylindrical assemblies: use `create_lsdyna_cylindrical_assembly` for a closed cylindrical shell with neutral internal filling, regular attached blocks, and concentrated mass points. Use `check_lsdyna_cylindrical_assembly` to inspect mesh integrity, shell closure, and mass statistics.
   - S-ALE fluid domains: use `create_lsdyna_sale_fluid_domain` for regular 3D or axisymmetric structured ALE fluid domains, and `check_lsdyna_sale_fluid_domain` to inspect structured mesh, control points, multi-material groups, boundary faces, and volume-fraction filling.
   - ALE volume filling: use `create_initial_volume_fraction_geometry` to generate a standalone fill block, `append_initial_volume_fraction_geometry` to add it to a deck, and `inspect_initial_volume_fraction_geometry` to read existing `*INITIAL_VOLUME_FRACTION_GEOMETRY` setup.
4. Run a small validation first when the request includes fragile display behavior, unfamiliar variables, unusual output formats, or toggle-like LS-PrePost commands.
5. Always report output folder, naming convention, count of generated files, whether files are nonempty, and where `.lspp_mcp` logs/cfiles were written.

## Strategy Rules

Use the MCP tool directly when the request is narrow, ordinary, or one-off. The `export_d3plot_contour` tool opens LS-PrePost, exports one state, and exits for each call.

For multi-frame contour exports, prefer `export_d3plot_contour_frames` when the user requests many frames, times, or views and all frames share the same model, variable, parts, legend, range, color style, and format. It opens the d3plot/d3part once, then repeats state/view/print commands for each output file.

For post-processing summaries, inspect the result directory first. Use `extract_lsdyna_metrics` for curve-level values such as peak, time at peak, final value, mean, RMS, and time integral. Use `compare_lsdyna_cases` when the user asks to compare metrics across generated cases.

For LS-DYNA preprocessing questions, keep keyword tools read-only. Use the parser/checker to identify cards, includes, materials, EOS, parts, sections, sets, database outputs, ALE/FSI/blast/contact/load families, and solver-readiness issues before suggesting edits.

For simple model creation, prefer deterministic keyword generation over free-form LS-PrePost GUI automation. Use `create_lsdyna_plate_mesh`, `create_lsdyna_block_mesh`, or `create_lsdyna_cylinder_shell_mesh` only for regular meshes where the requested dimensions, divisions, material placeholders, and output path are clear. Run `precheck_lsdyna_keyword_model` after generation; run `preview_lsdyna_keyword_model` when LS-PrePost visual confirmation is needed. For complex geometry meshing, ask for or record a representative LS-PrePost cfile workflow before adding a controlled template.

For regular cylindrical assemblies, keep generated content neutral and template-based: shell geometry, inert/placeholder material cards, neutral `*INITIAL_VOLUME_FRACTION_GEOMETRY` occupancy, attached solid blocks, and concentrated mass points. Do not infer energetic material models, detonation cards, or weapon-effect calculations.

For S-ALE fluid domains, generate only the structured domain, boundary setup, placeholder materials, multi-material groups, and neutral initial filling requested by the user. Treat material models as placeholders unless the user provides exact material/EOS IDs and properties. Do not infer energetic materials, detonation controls, or weapon-effect calculations.

For ALE volume filling, keep the scope to geometry-based initial material occupancy. Do not infer high-energy materials, detonation controls, or damage behavior. Map cylinder/cone, box, sphere, plane, part, and segment containers to `*INITIAL_VOLUME_FRACTION_GEOMETRY` fields and preserve the user's AMMG IDs.

For parameterized case generation, do not reimplement the external desktop project's logic. For simple single-field sweeps, use `generate_lsdyna_keyword_field_sweep`; it can target arbitrary keyword fields by file line or keyword/line/field location and still calls the external project's parser/replacer/exporter. Use `generate_lsdyna_parameter_sweep` only as a convenience when the model uses `*PARAMETER`. For complex sampling, multiple parameters, constraints, or Excel inputs, use the saved JSON config and `generate_lsdyna_cases` so the external generator remains the source of truth.

For solver execution, prefer `dry_run=true` first when the command, working directory, CPU count, memory, or extra LS-DYNA arguments are uncertain. Never invent solver executable paths; use `lsdyna_exe` from config or ask the user to configure it. Use the default background mode for unattended batches; use `show_console=true` for single runs where the user wants to watch progress or type native LS-DYNA commands such as `sw1`, `sw2`, or `stop` into the solver console. Diagnose logs after every run before moving to post-processing.

Treat toggle commands carefully. Commands such as mesh-line toggles can persist across LS-PrePost sessions or flip state per frame. Probe one or two frames before batching, and avoid leaving unstable toggle logic in the MCP server unless the command is deterministic.

Do not use raw cfile as a general MCP input. If a custom cfile is needed for efficiency, generate it locally from known-safe commands, run LS-PrePost through the existing runner or a controlled script, and keep the generated cfile/log with the output.

## References

Read only the reference needed for the task:

- `references/workflows.md`: multi-frame exports, curve extraction, batching, and when to use one cfile.
- `references/options.md`: variables, image formats, views, output naming, preprocessing mesh options, and display options.
- `references/troubleshooting.md`: path/config errors, empty outputs, format failures, mesh toggles, timeouts, and validation checks.
