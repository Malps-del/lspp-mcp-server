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

Use `inspect_keyword_fields` when the user asks what values are set inside keywords, which fields use `&parameter` references, or how `*PARAMETER` / `*PARAMETER_EXPRESSION_LOCAL` values flow through the deck. Treat `*PARAMETER` as a normal keyword schema, not as a separate special-purpose tool.

Use `check_keyword_deck` when the user asks whether a model is ready for post-processing or solving. It checks missing includes, common control cards, d3plot/d3part/glstat/matsum/nodout/database extent availability, and common blast/ALE/FSI consistency hints.

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

Use `extract_binout_curve` for `binout` or `binout0000`. Remember that `entity_index` in binout plotting is LS-PrePost's entity index, not always LS-DYNA part ID, node ID, or interface ID.

## Many Cases

Use `batch_postprocess_cases` when multiple case directories share a task configuration. Resolve relative task paths against each case directory. Check `summary.json` and `summary.csv` after the batch.
