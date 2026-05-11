# MatAnyone Library for Griptape Nodes

Single-node MatAnyone integration with fixed model wiring and automatic model download.

## Included Nodes

- **MatAnyone Video Matte (Auto Model)**
  - Input: source video path + first-frame target mask path
  - Output: foreground video path + alpha video path
  - Uses fixed model repo: `PeiqingYang/MatAnyone`
  - Auto-downloads/caches model files from Hugging Face
- **MatAnyone First-Frame Mask (SAM2 Auto)**
  - Input: source video path
  - Output: generated first-frame mask path
  - Uses fixed SAM2 model: `facebook/sam2-hiera-large`
  - Auto-downloads/caches SAM2 files from Hugging Face
  - Uses center positive point by default to segment the main subject
- **MatAnyone One-Click Matte**
  - Input: source video path
  - Output: generated mask path + foreground video + alpha video
  - Runs SAM2 auto first-frame mask and MatAnyone matting in a single node run
  - Uses fixed model repos for both SAM2 and MatAnyone

## Inputs

- `input_video_path` (required): video file or frame-folder path
- `input_mask_path` (required): first-frame segmentation mask path
- `output_directory` (optional): result folder (auto-created if missing)
- `output_suffix` (optional): filename suffix for output naming
- `n_warmup` (default `10`)
- `r_erode` (default `10`)
- `r_dilate` (default `10`)
- `max_size` (default `-1`, unlimited)
- `save_image` (default `false`)

## Outputs

- `foreground_video_path`
- `alpha_video_path`
- `model_cache_path`
- `status_message`

Mask helper node outputs:

- `output_mask_path_out`
- `first_frame_path`
- `sam2_model_cache_path`
- `status_message`

One-click node outputs:

- `output_mask_path_out`
- `first_frame_path`
- `foreground_video_path`
- `alpha_video_path`
- `sam2_model_cache_path`
- `matanyone_model_cache_path`
- `status_message`

## Notes

- Model selection is intentionally hardcoded to avoid manual setup.
- First run may take longer while MatAnyone assets are downloaded.
