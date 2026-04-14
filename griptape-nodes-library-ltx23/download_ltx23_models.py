from __future__ import annotations

import argparse
import sys
from pathlib import Path


CORE_ASSETS = [
    ("Lightricks/LTX-2.3", "ltx-2.3-22b-dev.safetensors", "checkpoints"),
    ("Lightricks/LTX-2.3", "ltx-2.3-22b-distilled.safetensors", "checkpoints"),
    ("Lightricks/LTX-2.3", "ltx-2.3-spatial-upscaler-x2-1.0.safetensors", "upscalers"),
    ("Lightricks/LTX-2.3", "ltx-2.3-spatial-upscaler-x1.5-1.0.safetensors", "upscalers"),
    ("Lightricks/LTX-2.3", "ltx-2.3-temporal-upscaler-x2-1.0.safetensors", "upscalers"),
    ("Lightricks/LTX-2.3", "ltx-2.3-22b-distilled-lora-384.safetensors", "distilled_lora"),
]

EXTRA_LORAS = [
    (
        "Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control",
        "ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors",
        "loras/ic",
    ),
    (
        "Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control",
        "ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors",
        "loras/ic",
    ),
    ("Lightricks/LTX-2-19b-IC-LoRA-Detailer", "ltx-2-19b-ic-lora-detailer.safetensors", "loras/ic"),
    ("Lightricks/LTX-2-19b-IC-LoRA-Pose-Control", "ltx-2-19b-ic-lora-pose-control.safetensors", "loras/ic"),
    (
        "Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-In",
        "ltx-2-19b-lora-camera-control-dolly-in.safetensors",
        "loras/camera",
    ),
    (
        "Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Left",
        "ltx-2-19b-lora-camera-control-dolly-left.safetensors",
        "loras/camera",
    ),
    (
        "Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Out",
        "ltx-2-19b-lora-camera-control-dolly-out.safetensors",
        "loras/camera",
    ),
    (
        "Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Right",
        "ltx-2-19b-lora-camera-control-dolly-right.safetensors",
        "loras/camera",
    ),
    (
        "Lightricks/LTX-2-19b-LoRA-Camera-Control-Jib-Down",
        "ltx-2-19b-lora-camera-control-jib-down.safetensors",
        "loras/camera",
    ),
    (
        "Lightricks/LTX-2-19b-LoRA-Camera-Control-Jib-Up",
        "ltx-2-19b-lora-camera-control-jib-up.safetensors",
        "loras/camera",
    ),
    (
        "Lightricks/LTX-2-19b-LoRA-Camera-Control-Static",
        "ltx-2-19b-lora-camera-control-static.safetensors",
        "loras/camera",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Download LTX-2.3 model assets into a local folder.")
    parser.add_argument("--models-root", required=True, help="Destination root directory.")
    parser.add_argument("--all", action="store_true", help="Also download official extra LoRAs.")
    parser.add_argument(
        "--with-gemma",
        action="store_true",
        help="Also download Gemma text encoder snapshot (very large and may require HF auth).",
    )
    parser.add_argument("--hf-token", default="", help="Optional Hugging Face token.")
    parser.add_argument("--force-redownload", action="store_true", help="Force refresh files.")
    args = parser.parse_args()

    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except Exception as e:
        print(f"Missing huggingface_hub: {e}", file=sys.stderr)
        return 2

    root = Path(args.models_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    token = args.hf_token.strip() or None

    assets = list(CORE_ASSETS)
    if args.all:
        assets.extend(EXTRA_LORAS)

    failed = 0
    for repo_id, filename, subdir in assets:
        local_dir = root / subdir
        local_dir.mkdir(parents=True, exist_ok=True)
        print(f"[DOWNLOAD] {repo_id}/{filename} -> {local_dir}")
        try:
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=str(local_dir),
                local_dir_use_symlinks=False,
                token=token,
                force_download=args.force_redownload,
            )
        except Exception as e:
            failed += 1
            print(f"[FAILED] {repo_id}/{filename}: {e}", file=sys.stderr)

    if args.with_gemma:
        gemma_dir = root / "gemma"
        gemma_dir.mkdir(parents=True, exist_ok=True)
        print("[DOWNLOAD] google/gemma-3-12b-it-qat-q4_0-unquantized (snapshot)")
        try:
            snapshot_download(
                repo_id="google/gemma-3-12b-it-qat-q4_0-unquantized",
                local_dir=str(gemma_dir),
                local_dir_use_symlinks=False,
                token=token,
                force_download=args.force_redownload,
            )
        except Exception as e:
            failed += 1
            print(f"[FAILED] Gemma snapshot: {e}", file=sys.stderr)

    print(f"[DONE] models_root={root} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
