# GTN Flow Denoise

GTN library adaptation of [ComfyUI-FlowDenoise](https://github.com/AIMZ-GFX/ComfyUI-FlowDenoise) for frame-sequence denoising workflows in Griptape Nodes.

## Included Nodes

- **Temporal Flow Average**: Optical-flow aligned temporal averaging (`raft_small`, `raft_large`, optional `memfof`)
- **Extract Noise (Chroma/Luma)**: Visualize total/chroma/luma noise between original and clean sequences
- **Selective Denoise**: Blend original and clean frames with independent chroma/luma strengths

## Inputs / Outputs

Nodes consume image frame sequences as `list[ImageArtifact]` (single images are accepted and treated as a 1-frame sequence), and return frame sequences as `list[ImageArtifact]`.

## Source Attribution

Core denoising implementation is based on `AIMZ-GFX/ComfyUI-FlowDenoise` (MIT).

## Dependency Note

`memfof` is installed from source (`msu-video-group/memfof`) using:

`memfof @ git+https://github.com/msu-video-group/memfof.git`

This requires `git` to be available on your system. If installation fails in your environment, the node can still run with RAFT models.
