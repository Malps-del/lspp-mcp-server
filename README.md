# lspp-mcp-server

`lspp-mcp-server` 是一个基于 Python 的 LS-PrePost MCP server。它把经过白名单验证的 LS-PrePost command file 模板封装成稳定、有限、可复核的 MCP tools，用于 LS-DYNA 后处理自动化。

它不允许 AI 传入任意 raw cfile，也不直接操控 LS-PrePost GUI。所有工具只会渲染项目内的模板，执行生成的 `.cfile`，并把 `.cfile`、运行日志、返回码和输出检查结果保存在输出目录旁的 `.lspp_mcp/` 目录中。

## 典型使用流程

通常你会按这个顺序使用本项目：

1. 从 GitHub 克隆 `lspp-mcp-server` 到本机。
2. 在项目目录里创建 Python 虚拟环境并安装 MCP server。
3. 手动复制 `config.example.yaml` 为 `config.yaml`，填写本机 LS-PrePost 路径和允许访问的仿真目录。
4. 手动把这个 MCP server 加入 Codex 的 `config.toml`。
5. 重启 Codex 或新开 Codex 会话。
6. 用自然语言让 Codex 调用 LS-PrePost 完成后处理。

## 在新电脑上部署

下面以 Windows 为例。项目可以放在任意目录，后文用 `<MCP项目目录>` 表示你实际克隆本仓库的位置。

例如你可以放在：

```text
D:\tools\lspp-mcp
E:\apps\lspp-mcp
C:\Users\<你的用户名>\Projects\lspp-mcp
```

只要后面 `config.toml` 里的 `command`、`cwd`、`LSPP_MCP_CONFIG` 都改成同一个实际目录即可。

### 1. 手动安装前置软件

新电脑需要先手动安装：

- Git
- Python 3.10 或更高版本
- LS-PrePost
- Codex

### 2. 克隆仓库

用 Git 克隆仓库：

```powershell
$McpDir = "D:\tools\lspp-mcp"  # 可换成你想放置本项目的任意目录
git clone https://github.com/Malps-del/lspp-mcp-server.git $McpDir
Set-Location $McpDir
```

### 3. 创建虚拟环境并安装

在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

安装完成后运行测试：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

看到 `OK` 就说明 Python 包和基础逻辑可用。

### 4. 手动创建本机 config.yaml

这个步骤必须手动做，因为每台电脑的 LS-PrePost 安装路径和仿真文件目录都不同。

```powershell
Copy-Item config.example.yaml config.yaml
```

然后编辑 `<MCP项目目录>\config.yaml`。以下几项可能需要根据实际情况修改：

```yaml
lsprepost_exe: "D:/Program Files/Ansys/LS-PrePost-2025R1(4.12)/lsprepost4.12.exe"
workspace_root: "D:/lsdyna-projects"
allowed_roots:
  - "D:/lsdyna-projects"
timeout_seconds: 300
case_generator_python: ""
case_generator_src: ""
```

含义：

- `lsprepost_exe`：本机 LS-PrePost 可执行文件路径。
- `workspace_root`：相对路径的默认起点。例如传入 `case01/d3part` 时，会按 `workspace_root/case01/d3part` 解析。
- `allowed_roots`：安全白名单目录。MCP 只允许读写这些目录下面的文件。
- `timeout_seconds`：单次 LS-PrePost 调用的超时时间。
- `case_generator_python`：可选。已有 LS-DYNA Batch Case Generator 项目的 Python 解释器路径，通常是该项目 `.venv` 里的 `python.exe`。
- `case_generator_src`：可选。已有 LS-DYNA Batch Case Generator 项目的 `src` 目录。

如果你的仿真项目分散在多个目录，可以写多个白名单目录：

```yaml
workspace_root: "D:/lsdyna-projects"
allowed_roots:
  - "D:/lsdyna-projects"
  - "E:/shared-results"
```

### 5. 手动配置 Codex MCP

Codex 通过 `config.toml` 加载 MCP server。Windows 上通常是：

```text
C:\Users\<你的用户名>\.codex\config.toml
```

在这个文件里新增：

```toml
[mcp_servers.lspp]
command = "<MCP项目目录>/.venv/Scripts/python.exe"
args = ["-m", "lspp_mcp.server"]
cwd = "<MCP项目目录>"
startup_timeout_sec = 20
tool_timeout_sec = 600
default_tools_approval_mode = "prompt"

[mcp_servers.lspp.env]
LSPP_MCP_CONFIG = "<MCP项目目录>/config.yaml"
```

将上述文本复制到 `config.toml` 前，请把 `<MCP项目目录>` 替换成你的实际绝对路径，并建议使用 `/` 写路径。例如项目放在 `D:\tools\lspp-mcp` 时：

```toml
[mcp_servers.lspp]
command = "D:/tools/lspp-mcp/.venv/Scripts/python.exe"
args = ["-m", "lspp_mcp.server"]
cwd = "D:/tools/lspp-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 600
default_tools_approval_mode = "prompt"

[mcp_servers.lspp.env]
LSPP_MCP_CONFIG = "D:/tools/lspp-mcp/config.yaml"
```

其中：

- `command`：运行 MCP server 的 Python 解释器，通常是项目虚拟环境里的 `python.exe`。
- `cwd`：MCP 项目根目录，也就是包含 `pyproject.toml`、`src`、`README.md` 的目录。
- `LSPP_MCP_CONFIG`：本机 `config.yaml` 的绝对路径。

配置后，重启 Codex 或新开一个 Codex 会话。

### 6. 验证 MCP 是否加载

在 Codex CLI/TUI 中可以输入：

```text
/mcp
```

确认能看到 `lspp`。

在 Codex 桌面窗口中，可以用两种方式验证：

1. 打开 Codex 设置，进入 MCP 相关设置页，确认 `lspp` server 已启用且没有启动错误。
2. 新开一个 Codex 会话，直接输入下面的验证问题。

```text
列出当前可用的 MCP server，确认 lspp 是否已加载。
```

然后可以继续问：

```text
列出 lspp MCP 支持的 d3plot_fringe 变量。
```

或：

```text
用 lspp MCP 检查 LS-PrePost 路径和 workspace 是否可用。
```

## 不通过 Codex 直接启动

调试时也可以手动启动 MCP server：

```powershell
$env:LSPP_MCP_CONFIG="D:/tools/lspp-mcp/config.yaml"  # 改成你的实际 config.yaml 路径
.\.venv\Scripts\python.exe -m lspp_mcp.server
```

正常在 Codex 中使用时，不需要手动运行这条命令；Codex 会按 `config.toml` 自动启动 MCP server。

## 在 Codex 中怎么调用

配置完成后，你不需要手写 JSON。直接用自然语言说清楚输入文件、输出文件、变量、状态帧和视角即可。

例如：

```text
从 D:\lsdyna-projects\case01\d3part 导出第 5 帧 von_mises 云图，等轴测视图，
输出到 D:\lsdyna-projects\case01\post\von_mises_s005.png，云图显示层级设为 50。
```

Codex 会把它映射为 `export_d3plot_contour`，并自动设置输入文件、输出图片、变量名、状态帧、视角和云图层级等参数。

图片格式会根据输出文件扩展名自动选择。例如输出到 `.jpg` 会使用 JPG，输出到 `.wrl` 会使用 VRML/WRL。也可以明确说“输出为 jpg 格式”。当前在 LS-PrePost 4.12 cfile 自动化中已验证支持：

```text
png, jpg, bmp, gif, wrl
```

LS-PrePost 界面下拉框里还可能显示 `pdf`、`tif`、`pcx`、`ps`、`eps`、`tex`、`svg`、`pgf` 等格式，但这些格式在当前 4.12 环境下用同一套 cfile `print` 命令没有稳定生成非空文件，因此暂时不作为 MCP 支持格式。

再比如提取节点历史曲线：

```text
从 D:\lsdyna-projects\case01\d3plot 提取节点 524 的 resultant_displacement 历史曲线，
保存到 D:\lsdyna-projects\case01\post\node524_resultant_disp.csv。
```

提取 ASCII 曲线：

```text
从 D:\lsdyna-projects\case01\nodout 提取节点 524 的 y_displacement 曲线，
保存到 D:\lsdyna-projects\case01\post\node524_y_disp.csv。
```

提取 binout 曲线：

```text
从 D:\lsdyna-projects\case01\binout 提取 glstat 的 kinetic_energy 曲线，
保存到 D:\lsdyna-projects\case01\post\binout_glstat_ke.csv。
```

如果新会话中 Codex 没有自动选择这个 MCP，可以在句子前面加：

```text
用 lspp MCP ...
```

## 案例：导出第 1 到 10 帧 von Mises 云图

假设工况目录是：

```text
D:\lsdyna-projects\case01
```

其中有：

```text
D:\lsdyna-projects\case01\d3part
```

目标是从 `d3part` 导出第 `1` 到 `10` 帧的 von Mises 应力云图，等轴测视图，并在该目录下新建文件夹保存图片。

可以直接对 Codex 说：

```text
从 D:\lsdyna-projects\case01 的 d3part 中提取第 1 到 10 帧的 mises 应力云图，
等轴测视图，图片在该目录下新建一个文件夹保存。
```

推荐更明确一点：

```text
用 lspp MCP 从 D:\lsdyna-projects\case01\d3part 导出第 1 到 10 帧 von_mises 云图，
视角 isometric，输出到 D:\lsdyna-projects\case01\von_mises_isometric_frames_1_10，
文件名按 von_mises_state_001.png 到 von_mises_state_010.png 命名。
```

Codex 会优先调用 `export_d3plot_contour_frames`，在同一个 LS-PrePost 会话中打开一次 `d3plot` 或 `d3part`，然后连续切换 state 并截图：

```text
state_index = 1, 2, 3, ..., 10
variable = von_mises
view = isometric
```

输出目录示例：

```text
D:\lsdyna-projects\case01\von_mises_isometric_frames_1_10
```

输出文件示例：

```text
von_mises_state_001.png
von_mises_state_002.png
...
von_mises_state_010.png
```

这类多帧任务只会生成一次 `.lspp_mcp` 运行记录，里面包含：

```text
generated.cfile
run.json
```

这些文件用于复核实际执行的 LS-PrePost 命令、返回码和每一帧输出文件的检查结果。少量帧或每帧设置不同的特殊任务，仍然可以使用单帧 `export_d3plot_contour`。

## MCP Tools

### validate_lsprepost

检查 LS-PrePost 可执行文件是否存在、workspace 是否存在且可写。

### list_supported_variables

列出配置中支持的变量映射。支持 `d3plot_fringe`、`nodout`、`matsum`、`node_history`、`binout`。

### export_d3plot_contour

从 `d3plot` 或 `d3part` 导出指定变量、指定状态帧、指定视角的云图文件。支持 `png`、`jpg`、`bmp`、`gif`、`wrl` 输出格式，并支持 part 显示控制、图例/坐标轴显示控制、背景色、窗口尺寸和云图显示层级。

### export_d3plot_contour_frames

从同一个 `d3plot` 或 `d3part` 连续导出多帧云图。该工具只启动一次 LS-PrePost，在同一个 cfile 中依次执行 `state` 和 `print`，适合第 1 到 30 帧、第 1 到 100 帧这类连续截图任务。支持与单帧云图导出相同的变量、视角、输出格式、part 控制、图例/坐标轴、背景色和云图显示层级。

### extract_ascii_curve

从 `nodout`、`matsum`、`glstat`、`rcforc` 等 ASCII 结果文件导出曲线 CSV。适合提取节点位移/速度/加速度、part 能量、全局能量、接触力等曲线。

### extract_d3plot_node_history

使用 `genselect + ntime` 从 `d3plot` 提取指定节点的历史变量曲线，并保存为 CSV。

### extract_binout_curve

从 `binout` 或 `binout0000` 提取 `glstat`、`matsum`、`trhist`、`dbfsi` 等 block 下的变量曲线，并保存为 CSV。

对于 `matsum`、`trhist`、`dbfsi`，`entity_index` 是 LS-PrePost binaski 的实体序号，不一定等于 LS-DYNA part ID、node ID 或界面 ID。

### batch_postprocess_cases

对多个工况目录批量运行后处理任务，并写出 `summary.json`、`summary.csv`。适合把同一套云图导出或曲线提取流程应用到多个 case。

### validate_case_generator_integration

检查 MCP 是否能调用外部 LS-DYNA Batch Case Generator 项目。会验证 `case_generator_python`、`case_generator_src` 是否可用，并尝试导入其核心服务。

### inspect_lsdyna_case_config

读取 LS-DYNA Batch Case Generator 保存的 JSON 配置，汇总初始 `k` 文件、已选参数、约束、生成方式、输出设置和关键字概览。该工具只读，不会生成新工况。

### generate_lsdyna_cases

复用外部 LS-DYNA Batch Case Generator 的现有核心逻辑，从其 JSON 配置生成参数化工况。支持随机采样、LHS、Excel 输入、约束过滤、命名模板、输出索引表和附带资源复制。可以先用 `preview_only=true` 只预览工况和命名结果，再正式导出。

### inspect_keyword_deck

只读解析 LS-DYNA `k`/keyword 文件，汇总关键字数量、include 文件、材料、截面、part、set、数据库输出卡，以及爆炸冲击/ALE/FSI/接触/载荷等常见关键字族。该工具不会修改原始 `k` 文件。如果一个模型由多个没有互相 include 的 `k` 文件共同组成，可以通过 `extra_k_paths` 一起纳入解析。

### check_keyword_deck

在 `inspect_keyword_deck` 的基础上做前处理检查，例如 include 是否缺失、是否有 `*CONTROL_TERMINATION` 和 `*CONTROL_TIMESTEP`、是否配置 d3plot/d3part、glstat、matsum、extent binary 等常用输出，以及爆炸、ALE、FSI 模型中常见的后处理准备项是否缺失。需要同时检查多个独立 `k` 文件时，同样使用 `extra_k_paths`。

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
