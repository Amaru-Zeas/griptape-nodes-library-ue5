from typing import List, Optional, Union

import numpy as np
import scipy
import torch
import torch.nn.functional as F
from diffusers.models import AutoencoderKLWan
from diffusers.pipelines.pipeline_utils import DiffusionPipeline
from diffusers.pipelines.wan.pipeline_output import WanPipelineOutput
from diffusers.schedulers import FlowMatchEulerDiscreteScheduler
from diffusers.utils import is_torch_xla_available
from diffusers.utils.torch_utils import randn_tensor
from diffusers.video_processor import VideoProcessor
from einops import rearrange

from transformer_minimax_remover import Transformer3DModel

if is_torch_xla_available():
    import torch_xla.core.xla_model as xm

    XLA_AVAILABLE = True
else:
    XLA_AVAILABLE = False


class MinimaxRemoverPipeline(DiffusionPipeline):
    model_cpu_offload_seq = "transformer->vae"
    _callback_tensor_inputs = ["latents"]

    def __init__(
        self,
        transformer: Transformer3DModel,
        vae: AutoencoderKLWan,
        scheduler: FlowMatchEulerDiscreteScheduler,
    ):
        super().__init__()
        self.register_modules(vae=vae, transformer=transformer, scheduler=scheduler)
        self.vae_scale_factor_temporal = 2 ** sum(self.vae.temperal_downsample) if getattr(self, "vae", None) else 4
        self.vae_scale_factor_spatial = 2 ** len(self.vae.temperal_downsample) if getattr(self, "vae", None) else 8
        self.video_processor = VideoProcessor(vae_scale_factor=self.vae_scale_factor_spatial)

    def prepare_latents(
        self,
        batch_size: int,
        num_channels_latents: int = 16,
        height: int = 720,
        width: int = 1280,
        num_latent_frames: int = 21,
        dtype: Optional[torch.dtype] = None,
        device: Optional[torch.device] = None,
        generator: Optional[Union[torch.Generator, List[torch.Generator]]] = None,
        latents: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        if latents is not None:
            return latents.to(device=device, dtype=dtype)

        shape = (
            batch_size,
            num_channels_latents,
            num_latent_frames,
            int(height) // self.vae_scale_factor_spatial,
            int(width) // self.vae_scale_factor_spatial,
        )
        return randn_tensor(shape, generator=generator, device=device, dtype=dtype)

    def expand_masks(self, masks: torch.Tensor, iterations: int) -> torch.Tensor:
        masks_np = masks.cpu().detach().numpy()
        expanded = []
        for mask in masks_np:
            mask = mask > 0
            mask = scipy.ndimage.binary_dilation(mask, iterations=iterations)
            expanded.append(mask)
        masks_np = np.array(expanded).astype(np.float32)
        out = torch.from_numpy(masks_np)
        out = out.repeat(1, 1, 1, 3)
        out = rearrange(out, "f h w c -> c f h w")
        return out[None, ...]

    def resize(self, images: torch.Tensor, height: int, width: int) -> torch.Tensor:
        bsz, _, frames, _, _ = images.shape
        images = rearrange(images, "b c f h w -> (b f) c h w")
        images = F.interpolate(images, (height, width), mode="bilinear")
        images = rearrange(images, "(b f) c h w -> b c f h w", b=bsz, f=frames)
        return images

    @torch.no_grad()
    def __call__(
        self,
        height: int = 720,
        width: int = 1280,
        num_frames: int = 81,
        num_inference_steps: int = 50,
        generator: Optional[Union[torch.Generator, List[torch.Generator]]] = None,
        images: Optional[torch.Tensor] = None,
        masks: Optional[torch.Tensor] = None,
        latents: Optional[torch.Tensor] = None,
        output_type: Optional[str] = "np",
        iterations: int = 16,
    ):
        if images is None or masks is None:
            raise ValueError("Both `images` and `masks` are required.")

        device = self._execution_device
        batch_size = 1
        work_dtype = self.transformer.dtype if hasattr(self.transformer, "dtype") else torch.float16

        self.scheduler.set_timesteps(num_inference_steps, device=device)
        timesteps = self.scheduler.timesteps

        num_channels_latents = 16
        num_latent_frames = (num_frames - 1) // self.vae_scale_factor_temporal + 1
        latents = self.prepare_latents(
            batch_size,
            num_channels_latents,
            height,
            width,
            num_latent_frames,
            work_dtype,
            device,
            generator,
            latents,
        )

        masks = self.expand_masks(masks, iterations)
        masks = self.resize(masks, height, width).to(device=device, dtype=work_dtype)
        masks[masks > 0] = 1

        images = rearrange(images, "f h w c -> c f h w")
        images = self.resize(images[None, ...], height, width).to(device=device, dtype=work_dtype)
        masked_images = images * (1 - masks)

        latents_mean = torch.tensor(self.vae.config.latents_mean).view(1, self.vae.config.z_dim, 1, 1, 1).to(
            self.vae.device, work_dtype
        )
        latents_std = 1.0 / torch.tensor(self.vae.config.latents_std).view(1, self.vae.config.z_dim, 1, 1, 1).to(
            self.vae.device, work_dtype
        )

        masked_latents = self.vae.encode(masked_images).latent_dist.mode()
        masks_latents = self.vae.encode(2 * masks - 1.0).latent_dist.mode()
        masked_latents = (masked_latents - latents_mean) * latents_std
        masks_latents = (masks_latents - latents_mean) * latents_std

        with self.progress_bar(total=num_inference_steps) as progress_bar:
            for t in timesteps:
                latent_model_input = latents.to(work_dtype)
                latent_model_input = torch.cat([latent_model_input, masked_latents, masks_latents], dim=1)
                timestep = t.expand(latents.shape[0])

                noise_pred = self.transformer(hidden_states=latent_model_input, timestep=timestep)[0]
                latents = self.scheduler.step(noise_pred, t, latents, return_dict=False)[0]
                progress_bar.update()

        latents = latents.to(work_dtype) / latents_std + latents_mean
        video = self.vae.decode(latents, return_dict=False)[0]
        video = self.video_processor.postprocess_video(video, output_type=output_type)
        return WanPipelineOutput(frames=video)
