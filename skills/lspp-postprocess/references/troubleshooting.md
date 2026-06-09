# Troubleshooting

## Validate First

Use `validate_lsprepost` or inspect `config.yaml` when LS-PrePost fails to start, a workspace path is unclear, or a new machine is being configured.

Check:

- `lsprepost_exe` exists
- `workspace_root` exists
- requested input/output paths are under `allowed_roots`
- `timeout_seconds` is long enough for the model size

## Missing Or Empty Output

Read the generated `.lspp_mcp/.../generated.cfile` and `run.json`.

Common causes:

- wrong state number
- unsupported variable mapping
- output already exists with `overwrite=False`
- output path outside `allowed_roots`
- LS-PrePost returned success but the requested print format has no handler
- display command toggled into an unintended state

Always check file existence and size, not only the LS-PrePost return code.

## Format Failures

If a format is not in `png`, `jpg`, `bmp`, `gif`, or `wrl`, expect rejection by the MCP. If the user wants a GUI-listed format anyway, run a small controlled test first and only expand the MCP whitelist after verifying a nonempty output.

For `wrl`, the output extension is `.wrl` but the cfile print keyword is `vrml`.

## Mesh And Outline

Mesh-line commands can behave as toggles and may persist across sessions. A command that closes mesh on one frame may reopen it on the next if repeated blindly.

Before exporting many states with mesh or outline changes:

1. Generate one or two probe frames.
2. Inspect the images or compare file sizes.
3. Use a strategy that avoids per-frame toggle flips.

## Batch Performance

Repeated single-frame MCP calls are robust but slower because each call opens LS-PrePost. For many frames from the same model, use one generated cfile or add a permanent MCP batch-frame tool.
