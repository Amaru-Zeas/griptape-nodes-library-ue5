# OpenPose 3D Editor Library for Griptape Nodes

A full-featured 3D OpenPose skeleton editor built as a Griptape Nodes custom library. Edit human poses interactively in 3D, capture pose images, generate depth/normal maps, and export to ControlNet format — all directly inside your Griptape Nodes workflow.

**Based on:** [sd-webui-3d-open-pose-editor](https://github.com/nonnonstop/sd-webui-3d-open-pose-editor)

## Nodes

### OpenPose 3D Editor (Pose Editor)
The main editor node with a full 3D widget built on THREE.js.

**Features:**
- **18-keypoint OpenPose skeleton** with proper color coding
- **Joint rotation** via TransformControls gizmos (click joint → rotate)
- **Joint translation** mode (press X or use toolbar)
- **Camera navigation**: orbit (left-drag), zoom (scroll), pan (right-drag)
- **Body parameters**: Adjustable shoulder width, arm length, leg length, torso height, hip width
- **Preset poses**: T-Pose, A-Pose, Walking, Sitting, Relaxed
- **Image capture**: Skeleton on black background (📷 Pose button)
- **Depth map** capture (📷 Depth button)
- **Normal map** capture (📷 Normal button)
- **Save/Load** scene as JSON
- **Undo/Redo** (Ctrl+Z / Ctrl+Y)

**Outputs:**
| Output | Type | Description |
|---|---|---|
| `joints_json` | str | All 18 keypoint world positions as JSON |
| `captured_image` | str | Base64 PNG data URL of captured pose image |
| `depth_map` | str | Base64 PNG data URL of depth map |
| `normal_map` | str | Base64 PNG data URL of normal map |
| `scene_json` | str | Full scene state JSON for save/restore |
| `joint_count` | int | Number of joints |

### Save Pose Image (Pose Tools)
Decode and save a captured base64 image to a PNG file.

**Inputs:**
- `image_data` — Base64 PNG data URL (connect to `captured_image`, `depth_map`, or `normal_map`)
- `file_path` — Output file path (default: `pose_output.png`)

**Outputs:**
- `saved_path` — Absolute path of saved file
- `success` — Whether save succeeded

### Load Pose Scene (Pose Tools)
Load a previously saved pose scene JSON file.

**Inputs:**
- `file_path` — Path to a saved scene JSON file

**Outputs:**
- `scene_json` — Full scene state as JSON string
- `joints_json` — Extracted joint positions
- `success` — Whether load succeeded

### Pose to ControlNet (Pose Tools)
Convert 3D joint positions to 2D OpenPose format for ControlNet.

**Inputs:**
- `joints_json` — 3D joint positions from the editor
- `image_width` — Output width (default: 512)
- `image_height` — Output height (default: 768)
- `view` — Projection: `front`, `side`, or `top`

**Outputs:**
- `openpose_json` — Standard OpenPose JSON for ControlNet
- `keypoints_2d` — 2D keypoints array

## Keyboard Shortcuts

| Key | Action |
|---|---|
| **R** | Rotate mode (default) |
| **X** | Translate mode |
| **Ctrl+Z** | Undo |
| **Ctrl+Y** / **Ctrl+Shift+Z** | Redo |
| **Escape** | Deselect joint |

## Example Workflow

```
[OpenPose 3D Editor] → captured_image → [Save Pose Image] → saved_path
                     → joints_json → [Pose to ControlNet] → openpose_json → [ControlNet Node]
                     → depth_map → [Save Pose Image] → saved_path
```

## Installation

1. Copy the `griptape-nodes-library-openpose` folder to your Griptape Nodes custom libraries directory
2. Restart Griptape Nodes
3. The "OpenPose 3D Editor Library" should appear in your library list

## Dependencies

- **THREE.js r128** — Loaded automatically from CDN (no installation needed)
- No Python pip dependencies required

## Credits

- [sd-webui-3d-open-pose-editor](https://github.com/nonnonstop/sd-webui-3d-open-pose-editor) — Original extension
- [ZhUyU1997 - Online 3D Openpose Editor](https://github.com/ZhUyU1997/open-pose-editor) — Original online editor
- [OpenPose](https://github.com/CMU-Perceptual-Computing-Lab/openpose) — Human pose estimation
