# GTN DiT360

GTN node library for DiT360-style 360 panorama workflows with FLUX.1-dev.

This library ports the practical, GTN-friendly parts of the ComfyUI DiT360 flow:

- FLUX.1-dev + DiT360 LoRA preset outputs
- 2:1 equirectangular dimension helper
- edge blending post-process for seamless left/right wrap

## Included Nodes

- **DiT360 Flux Dev Preset** - emits recommended model/LoRA identifiers and generation defaults.
- **DiT360 Equirect Dimensions** - computes valid 2:1 dimensions and latent-space sizes.
- **DiT360 Edge Blender** - blends horizontal panorama edges and returns an `ImageArtifact`.

## Notes

- Use with your existing GTN Diffusers/Flux nodes from Advanced Media.
- DiT360 model internals from ComfyUI (sampler patching, RoPE patching) are not reimplemented here because GTN uses a different execution/runtime model.
