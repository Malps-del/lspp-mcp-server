---
name: lspp-postprocess
description: Plan and execute LS-PrePost/LS-DYNA post-processing with the lspp MCP server. Use when Codex needs to export d3plot or d3part contour images, extract node histories, extract ASCII or binout curves, batch states or cases, choose an efficient LS-PrePost cfile strategy, configure or validate LSPP_MCP_CONFIG, handle allowed_roots/workspace paths, select image formats/views/states/variables, tune legend/range/display options, or troubleshoot LS-PrePost MCP outputs.
---

# LS-PrePost Postprocess

## Core Workflow

1. Translate the user request into source file, output path, variable, state range, view, display options, and required format.
2. Confirm the requested source and output paths are inside `allowed_roots`; when unsure, inspect `config.yaml` or ask only for missing local facts.
3. Choose the execution strategy:
   - Single contour image: use `export_d3plot_contour`.
   - Node history: use `extract_d3plot_node_history`.
   - ASCII curve: use `extract_ascii_curve`.
   - Binout curve: use `extract_binout_curve`.
   - Many cases with the same task list: use `batch_postprocess_cases`.
   - Many states from the same d3plot/d3part: decide whether repeated single-frame MCP calls are acceptable or whether one generated cfile with repeated `state`/`print` is more efficient.
4. Run a small validation first when the request includes fragile display behavior, unfamiliar variables, unusual output formats, or toggle-like LS-PrePost commands.
5. Always report output folder, naming convention, count of generated files, whether files are nonempty, and where `.lspp_mcp` logs/cfiles were written.

## Strategy Rules

Use the MCP tool directly when the request is narrow, ordinary, or one-off. The current `export_d3plot_contour` tool opens LS-PrePost, exports one state, and exits for each call.

For multi-frame contour exports, prefer a single LS-PrePost cfile when the user requests many frames, speed matters, or all frames share the same model, variable, view, parts, legend, range, and format. In that cfile, open the d3plot/d3part once, then repeat `state N` and `print ...` for each output file.

Treat toggle commands carefully. Commands such as mesh-line toggles can persist across LS-PrePost sessions or flip state per frame. Probe one or two frames before batching, and avoid leaving unstable toggle logic in the MCP server unless the command is deterministic.

Do not use raw cfile as a general MCP input. If a custom cfile is needed for efficiency, generate it locally from known-safe commands, run LS-PrePost through the existing runner or a controlled script, and keep the generated cfile/log with the output.

## References

Read only the reference needed for the task:

- `references/workflows.md`: multi-frame exports, curve extraction, batching, and when to use one cfile.
- `references/options.md`: variables, image formats, views, output naming, and display options.
- `references/troubleshooting.md`: path/config errors, empty outputs, format failures, mesh toggles, timeouts, and validation checks.
