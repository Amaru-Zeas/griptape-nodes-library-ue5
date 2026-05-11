# CorridorKey Library for Griptape Nodes

Easy CorridorKey integration for Griptape with automatic model download.

## Included Node

- **CorridorKey Inference (Auto Model)**
  - Input: one clip folder containing `Input` and `AlphaHint`
  - Output: `Output/FG`, `Output/Matte`, `Output/Comp`, `Output/Processed`
  - Uses CorridorKey's built-in checkpoint discovery and auto-download flow
  - Supports backend/device and keying controls from node parameters

## Required Clip Folder Layout

```text
YourClip/
  Input/        # image sequence (or Input.mp4 style file at clip root)
  AlphaHint/    # matching mask sequence (or AlphaHint.mp4 style file at clip root)
```

## Key Inputs

- `clip_root_path` (optional): clip folder path
- `input_path` + `alpha_hint_path` (recommended): direct refs for Griptape wiring
  - Supports local file path, sequence folder path, URL, and common artifact-style dict refs (`path`/`value`/`url`)
- `output_parent_path` (optional): parent directory for direct input mode outputs
- `auto_alpha_hint_if_missing` (default `true`): if no alpha input is connected, generate a coarse hint from the greenscreen automatically
- `backend` (default `auto`): `auto`, `torch`, or `mlx`
- `device` (default `auto`): `auto`, `cuda`, `mps`, `cpu`
- `screen_color` (default `auto`): `auto`, `green`, or `blue`
- `input_is_linear` (default `false`)
- `despill_strength` (default `0.5`)
- `auto_despeckle` (default `true`)
- `despeckle_size` (default `400`)
- `refiner_scale` (default `1.0`)
- `image_size` (default `2048`)
- `tiled_inference` (default `false`)
- `max_frames` (default `-1`, means all frames)
- `skip_existing` (default `true`)

## Outputs

- `output_root_path`
- `fg_output_dir`
- `matte_output_dir`
- `comp_output_dir`
- `processed_output_dir`
- `status_message`

## Notes

- First run can take longer while CorridorKey downloads the checkpoint.
- Blue-screen support depends on CorridorKey backend capability (`torch` supports blue; `mlx` is green-only at time of writing).
- In direct mode, outputs go to `<output_parent_path>/<input_stem>_corridorkey_run/Output` (or beside input if no parent path is set).
- Auto alpha-hint mode is a convenience fallback; for best edge detail and hard shots, supplying a dedicated alpha hint is still recommended.
