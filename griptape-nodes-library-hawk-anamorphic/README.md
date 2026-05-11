# Hawk Anamorphic Library for Griptape Nodes

This GTN custom library recreates the **same function type** of the Hawk anamorphic Nuke gizmo as a practical post-look node for image files:

- Lens profile flavor (`28, 35, 45, 55, 65, 80, 110`)
- Focus-dependent breathing feel
- Chromatic aberration
- Edge softness falloff
- Vignette

## Included Node

- **Hawk Anamorphic Look**
  - Input: `input_image_path`
  - Output: `output_image_path_out`
  - Uses lens profile + focus + intensity controls to apply a Hawk-style look
  - Includes a custom **HawkAnamorphicWidget** UI with sliders and profile readback

## Node Inputs

- `input_image_path` (required)
- `output_image_path` (optional)
- `lens_mm` (`28`, `35`, `45`, `55`, `65`, `80`, `110`)
- `focus_m` (default: `12.0`)
- `chromatic_aberration` (default: `0.70`)
- `edge_softness` (default: `0.65`)
- `vignette` (default: `0.45`)
- `breathing_strength` (default: `1.0`)

## Node Outputs

- `output_image_path_out` - processed file path
- `status_message` - result text
- `profile_used` - resolved profile and effective values

## Notes

- This is an approximation designed for GTN workflows and does not execute Nuke `.gizmo` graphs directly.
- Best used as the final finishing step after depth-of-field and grading.
