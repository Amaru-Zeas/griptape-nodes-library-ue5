# GTN MiniMax Remover

Video object removal node library for Griptape Nodes, based on MiniMax-Remover.

## Included Nodes

- **MiniMax Remover** - remove masked objects from a video using local MiniMax model weights.
- **MiniMax Remover v2** - simplified mask-input-only version that removes built-in segmentation controls and always uses `input_mask_video`.
- **VOID Remover** - high-end remover that runs Netflix VOID from a local repo checkout and checkpoint, with automatic binary-mask to quadmask conversion.
- **Affected Mask Builder** - generates an affected-region mask video from a primary binary mask using temporal + spatial dilation.

## Notes

- Uses local model folder with expected subdirectories: `vae`, `transformer`, and `scheduler`.
- Segmentation backends:
  - `none`: use provided mask video input.
  - `sam2`: generate masks from text prompt using Grounding DINO + SAM2.
  - `sam3`: scaffolded placeholder (not yet implemented).

### Why v2

- More predictable results when you already have a high-quality tracked mask.
- Fewer controls to tune, so less chance of prompt/threshold-induced artifacts.

### VOID usage notes

- Requires local VOID repository path and `void_pass1.safetensors`.
- Requires local base model directory (`CogVideoX-Fun-V1.5-5b-InP`) via `cogvideox_model_dir`.
- Optional pass-2 refinement is supported via `enable_pass2_refinement=true` and `void_pass2_checkpoint`.
- Optional auto-pass2: set `pass2_auto_for_long_clips=true` and choose `pass2_min_frames` (default `240`).
- Resolution can be controlled with `output_height` + `output_width` (set both; `0` keeps VOID defaults).
- Frame rate can be controlled with `output_fps` (`0` preserves source FPS).
- Steps/quality are exposed directly:
  - `pass1_num_inference_steps`, `pass1_temporal_window_size`, `pass1_max_video_length`, `pass1_guidance_scale`
  - `pass2_num_inference_steps`, `pass2_temporal_window_size`, `pass2_guidance_scale`
- Expects large GPU memory (you are well-equipped with RTX A6000 96GB).
- For max quality, connect `input_affected_mask_video` too:
  - Primary (`input_mask_video`) + affected mask are fused into full quadmask values:
  - `0` primary remove only, `63` overlap, `127` affected only, `255` keep.
- `output_video` is now the clean inpaint result (not the side-by-side tuple preview).
- Optional tuple preview is available from `output_preview_tuple_video`.

### Max-quality wiring tip

- Use `Affected Mask Builder.output_affected_mask_video` as `VOID Remover.input_affected_mask_video`.
- Good starting values: `spatial_dilation_radius=12`, `temporal_dilation_radius=2`, `exclude_primary_region=true`.
