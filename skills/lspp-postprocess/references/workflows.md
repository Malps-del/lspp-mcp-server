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

Prefer explicit output folders and deterministic zero-padded names such as `von_mises_state_001.png`.

## Single Contour Image

Use `export_d3plot_contour` for one state. Set:

- `d3plot_path`: absolute path to `d3plot` or `d3part`
- `output_png`: output image path, even when the extension is not `.png`
- `variable`, `state_index`, `view`
- optional `part_ids`, `show_legend`, `show_triad`, `background`, `window_size`, `range_level`, `image_format`, `overwrite`

The tool returns `output_png`, `output_image`, `image_format`, `generated_cfile`, `log_file`, `ok`, and `message`.

## Multi-State Contour Images

Preferred MCP behavior: use `export_d3plot_contour_frames` when all frames share the same display options. It opens LS-PrePost once, loads the d3plot/d3part once, then repeats `state` and `print` for each requested frame.

Use repeated `export_d3plot_contour` calls only when there are very few frames or each frame needs different options.

For `export_d3plot_contour_frames`, map requests as:

- "第 1 到 30 帧" -> `state_start=1`, `state_end=30`
- "第 1、5、10 帧" -> `state_indices=[1, 5, 10]`
- "图片在该目录下新建文件夹保存" -> create/pass `output_dir`
- "文件名按 ... 命名" -> `filename_template`

Do a one-frame or two-frame probe before large runs when using mesh/outline toggles, unusual formats, or untested display commands.

## Keyword Deck Inspection

Use `inspect_keyword_deck` to summarize a `k` file without modifying it. It follows `*INCLUDE` cards when enabled and reports keyword counts, include files, database output cards, entity summaries, and blast/impact/ALE/FSI-related keyword families.

Use `check_keyword_deck` when the user asks whether a model is ready for post-processing or solving. It checks missing includes, common control cards, d3plot/d3part/glstat/matsum/nodout/database extent availability, and common blast/ALE/FSI consistency hints.

## Parameterized Case Generation

When the user wants MCP/Codex to generate LS-DYNA parameterized cases from the existing desktop Batch Case Generator project:

1. Use `validate_case_generator_integration` first if the current session has not already confirmed the adapter works.
2. Use `inspect_lsdyna_case_config` on the JSON config saved by the desktop app to summarize selected parameters, constraints, sampling method, and output settings.
3. Use `generate_lsdyna_cases` with `preview_only=true` for a dry run when output paths, constraints, or naming templates are uncertain.
4. Use `generate_lsdyna_cases` with `preview_only=false` to export cases. Pass overrides such as `sample_count`, `random_seed`, `output_dir`, `method`, `folder_template`, and `file_template` only when the user asks to change the saved config behavior.

Do not duplicate the case generator logic inside the MCP. The adapter intentionally calls the external project's `ConfigService`, `KFileParser`, `CaseGeneratorService`, `ConstraintService`, and `ExportService`.

## Solver Execution

Use `validate_lsdyna_solver` before the first solve in a session or after config changes. It checks `lsdyna_exe` and the work directory.

Use `run_lsdyna_solver` to launch a solve from a `k` file. Recommended mapping:

- "先看命令" or uncertain arguments -> `dry_run=true`
- "用 16 核" -> `ncpu=16`
- "memory 200m" -> `memory="200m"`
- Extra LS-DYNA key/value options -> `additional_args=["key=value"]` only when they are explicit and safe
- If no work directory is specified, use the `k` file parent directory

After `run_lsdyna_solver`, inspect the returned `diagnostics`. If `completion_state` is not `normal_termination`, report the most important findings before doing post-processing.

Use `diagnose_lsdyna_logs` when the user only wants to inspect an existing run directory or when a solve was launched outside MCP. It reads `d3hsp`, `messag`, and `status.out` when present.

## Curves

Use `extract_d3plot_node_history` for d3plot node history curves when the result is not in ASCII/binout or the user asks for history from d3plot.

Use `extract_ascii_curve` for `nodout`, `matsum`, `glstat`, `rcforc`, and similar ASCII outputs.

Use `extract_binout_curve` for `binout` or `binout0000`. Remember that `entity_index` in binout plotting is LS-PrePost's entity index, not always LS-DYNA part ID, node ID, or interface ID.

## Many Cases

Use `batch_postprocess_cases` when multiple case directories share a task configuration. Resolve relative task paths against each case directory. Check `summary.json` and `summary.csv` after the batch.
