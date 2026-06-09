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

Current public MCP behavior: repeated `export_d3plot_contour` calls open LS-PrePost once per image.

Use repeated tool calls when there are only a few frames, when simplicity matters, or when each frame has different options.

Use one generated cfile when exporting many frames with the same settings:

1. Open the d3plot/d3part once.
2. Set fringe, part display, legend, triad, title, background, and range settings once.
3. For each state, write `state N`, view command, and `print <format> "<path>" opaque enlisted "OGL1x1"`.
4. Run with `run_lsprepost` in image mode.
5. Check every output exists and is nonempty; write a `summary.json`.

Do a one-frame or two-frame probe before large runs when using mesh/outline toggles, unusual formats, or untested display commands.

## Curves

Use `extract_d3plot_node_history` for d3plot node history curves when the result is not in ASCII/binout or the user asks for history from d3plot.

Use `extract_ascii_curve` for `nodout`, `matsum`, `glstat`, `rcforc`, and similar ASCII outputs.

Use `extract_binout_curve` for `binout` or `binout0000`. Remember that `entity_index` in binout plotting is LS-PrePost's entity index, not always LS-DYNA part ID, node ID, or interface ID.

## Many Cases

Use `batch_postprocess_cases` when multiple case directories share a task configuration. Resolve relative task paths against each case directory. Check `summary.json` and `summary.csv` after the batch.
