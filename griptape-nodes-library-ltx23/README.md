# GTN LTX-2.3

LTX-2.3 generation nodes for Griptape Nodes (GTN), with explicit multi-LoRA support.

## Included Nodes

- **LTX-2.3 Defaults** - emits starter model ids, module name, and baseline generation values.
- **LTX-2.3 LoRA Stack Builder** - builds a JSON LoRA stack payload from up to 4 LoRA slots.
- **LTX-2.3 Model Downloader** - downloads core/all official LTX-2.3 assets into a local project models folder.
- **LTX-2.3 Generate** - runs local `ltx_pipelines` modules via subprocess and returns generated video.
  - Includes collapsible UI groups for prompt/pipeline, model paths, conditioning, generation settings, and debug.

## Why this design

- LTX-2.3 support in Diffusers is still evolving.
- This library uses official LTX pipeline modules (`python -m ltx_pipelines.*`) for immediate compatibility.
- GTN-facing behavior still looks like a standard generation node with normal inputs/outputs.

## Requirements

- A local checkout of `https://github.com/Lightricks/LTX-2`.
- A Python environment with `ltx-pipelines` dependencies installed.
- Local model assets (checkpoint, Gemma root, upsampler, and optional distilled LoRA) downloaded from the LTX-2.3 model page.

## Notes

- `pipeline_module` defaults to `ti2vid_two_stages`.
- `pipeline_module` supports: `ti2vid_two_stages`, `ti2vid_two_stages_hq`, `distilled`, `ic_lora`, `retake`.
- Multi-LoRA is passed by repeated `--lora <path> <strength>` arguments.
- The node supports optional `extra_cli_args` for advanced options not yet exposed as first-class params.
- `LTX-2.3 Generate` can auto-resolve model paths from `models_root` if you keep the downloader's folder layout.
- Image/video conditioning support:
  - Image-to-video via `input_image` -> `--image`.
  - Video-to-video style conditioning via `ic_lora` + `input_video` -> `--video-conditioning`.
  - Retake video editing via `retake` + `input_video` + start/end time.
- The generation node currently targets text-to-video style runs first; additional dedicated nodes can be added for IC-LoRA and retake flows.
