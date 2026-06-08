# lspp-mcp-server

`lspp-mcp-server` 是一个基于 Python 的 LS-PrePost MCP server。它把经过白名单验证的 LS-PrePost command file 模板封装成稳定、有限、可复核的 MCP tools，用于 LS-DYNA 后处理自动化。

它不允许 AI 传入任意 raw cfile，也不直接操控 LS-PrePost GUI。所有工具只会渲染项目内的模板，执行生成的 `.cfile`，并把 `.cfile`、运行日志、返回码和输出检查结果保存在输出目录旁的 `.lspp_mcp/` 目录中。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

如果只想运行不依赖 LS-PrePost 的单元测试，可直接使用当前 Python：

```powershell
python -m unittest discover -s tests
```

## 配置

复制示例配置：

```powershell
Copy-Item config.example.yaml config.yaml
```

编辑 `config.yaml`：

```yaml
lsprepost_exe: "C:/Program Files/LSTC/LS-PrePost/lsprepost.exe"
workspace_root: "D:/lsdyna-post"
allowed_roots:
  - "D:/lsdyna-post"
timeout_seconds: 300
open_d3plot_command: "openc"
```

`workspace_root` 是默认工作目录。所有输入和输出必须位于 `workspace_root` 或 `allowed_roots` 内，防止 `..` 路径穿越和越权读写。

也可以通过环境变量指定配置文件：

```powershell
$env:LSPP_MCP_CONFIG="D:/lsdyna-post/config.yaml"
lspp-mcp-server
```

## 启动 MCP Server

安装依赖后运行：

```powershell
lspp-mcp-server
```

在 Codex 或其他 MCP client 中把该命令配置为本地 MCP server 即可。

## MCP Tools

### validate_lsprepost

检查 LS-PrePost 可执行文件和 workspace 是否可用。

输入：

```json
{
  "lsprepost_exe": "C:/Program Files/LSTC/LS-PrePost/lsprepost.exe",
  "workspace_root": "D:/lsdyna-post"
}
```

输出：

```json
{
  "ok": true,
  "message": "LS-PrePost executable and workspace are valid.",
  "detected_exe": "C:/Program Files/LSTC/LS-PrePost/lsprepost.exe",
  "workspace_root": "D:/lsdyna-post"
}
```

### list_supported_variables

列出配置中的变量映射。

```json
{ "category": "d3plot_fringe" }
```

支持 `d3plot_fringe`、`nodout`、`matsum`、`node_history`、`binout`。

### export_d3plot_contour

从 `d3plot` 或 `d3part` 导出云图 PNG。

```json
{
  "d3plot_path": "case01/d3plot",
  "output_png": "case01/post/von_mises_s10.png",
  "variable": "von_mises",
  "state_index": 10,
  "view": "isometric",
  "part_ids": [1, 2, 3],
  "show_legend": true,
  "show_triad": false,
  "background": "white",
  "window_size": "1600x1200",
  "use_nographics": false,
  "range_level": 50
}
```

`range_level` 是可选参数。传入 `50` 时，生成的 cfile 会包含：

```text
range level 50
range pal update
```

### extract_ascii_curve

从 `nodout`、`matsum`、`glstat`、`rcforc` 导出曲线 CSV。

```json
{
  "ascii_type": "nodout",
  "file_path": "case01/nodout",
  "variable": "x_displacement",
  "entity_id": 1001,
  "output_csv": "case01/post/node1001_x_disp.csv"
}
```

`glstat` 可以传入安全的 plot expression：

```json
{
  "ascii_type": "glstat",
  "file_path": "case01/glstat",
  "variable": "kinetic_energy",
  "output_csv": "case01/post/glstat_ke.csv"
}
```

### extract_d3plot_node_history

使用 `genselect + ntime` 从 d3plot 提取节点历史曲线。

```json
{
  "d3plot_path": "case01/d3plot",
  "node_id": 1001,
  "variable": "resultant_displacement",
  "output_csv": "case01/post/node1001_res_disp.csv"
}
```

### extract_binout_curve

从 `binout` 或 `binout0000` 提取 `glstat`、`matsum`、`trhist`、`dbfsi` 曲线。

```json
{
  "binout_path": "case01/binout",
  "block": "glstat",
  "variable": "kinetic_energy",
  "output_csv": "case01/post/binout_glstat_ke.csv",
  "mpp": false
}
```

对于 `matsum`、`trhist`、`dbfsi`，`entity_index` 是 LS-PrePost binaski 的实体序号，不一定等于 LS-DYNA part ID、node ID 或界面 ID。

### batch_postprocess_cases

对多个工况目录批量运行任务并写出 `summary.json`、`summary.csv`。如果文件已存在且 `overwrite=false`，会自动使用带时间戳的 summary 文件，避免覆盖。

```json
{
  "cases_root": "D:/lsdyna-post/cases",
  "task_config_path": "D:/lsdyna-post/batch_tasks.yaml"
}
```

`batch_tasks.yaml` 示例：

```yaml
cases:
  - case01
  - case02
tasks:
  - type: export_d3plot_contour
    d3plot_path: d3plot
    output_png: post/von_mises.png
    variable: von_mises
    state_index: 10
    view: isometric
  - type: extract_ascii_curve
    ascii_type: matsum
    file_path: matsum
    variable: internal_energy
    entity_id: 1
    output_csv: post/matsum_internal_energy.csv
```

## 扩展模板

新增模板时：

1. 把 `.cfile.j2` 放入 `src/lspp_mcp/cfile_templates/`。
2. 在 `src/lspp_mcp/templates.py` 的 `ALLOWED_TEMPLATES` 中加入模板文件名。
3. 在工具模块中只构造参数上下文，不把 LS-PrePost 命令散落到业务函数里。
4. 添加单元测试，检查渲染结果和禁止命令。

所有生成的 cfile 都会经过检查，禁止以 `system`、`shell`、`exec`、`cmd` 开头的命令行。

## 扩展变量映射

变量编号都在 YAML 中配置。修改 `config.yaml` 的 `variables` 段即可，例如：

```yaml
variables:
  d3plot_fringe:
    custom_result: 999
  binout:
    glstat:
      custom_energy:
        variable: custom_energy
        index1: 0
        index2: 1
        entity_index: 0
```

如果以后 LS-PrePost 版本或变量列表变化，可以继续在 `config.yaml` 中修改。

## 为什么不执行任意 raw cfile

LS-PrePost command file 可以包含危险或不可审计的操作。MCP 工具面向 AI 调用时，必须保持有限能力边界：只允许项目内白名单模板、只允许配置化变量、只允许受控路径、所有运行都保存日志和输出检查结果。

## 曲线提取与图片导出

曲线提取通常可以使用：

```text
lsprepost.exe c=generated.cfile -nographics
```

图片导出通常需要图形环境：

```text
lsprepost.exe c=generated.cfile w=1600x1200
```

Linux 环境下图片导出可能需要 `xvfb-run` 或类似虚拟 framebuffer。第一版 runner 已保留 `mode="image"` 与 `window_size` 参数；如需生产化 Linux 图形导出，可在 `runner.py` 中按部署环境包一层 xvfb 启动命令。
