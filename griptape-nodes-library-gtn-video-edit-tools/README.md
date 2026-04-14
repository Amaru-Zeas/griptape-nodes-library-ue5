# GTN Video Edit Tools

Frame-accurate video utility widgets for Griptape Nodes.

## Included Nodes

- **Video Frame Editor** - import a video, move frame-by-frame (buttons, slider, and mouse wheel), and extract the current frame as a PNG image data URL.
- **Video Blend** - combine two videos into one with simple frame-by-frame blend modes (`normal`, `screen`, `multiply`, `add`, `overlay`).
- **Video Color Match** - transfer color characteristics from a reference video to a target video using `color-matcher` methods (`mkl`, `hm`, `reinhard`, `mvgd`, `hm-mvgd-hm`, `hm-mkl-hm`) with adjustable strength.

## Outputs

- `frame_image_data` - extracted PNG frame as a base64 data URL.
- `frame_index` - current frame index (0-based).
- `frame_time_seconds` - timestamp for the current frame.
- `video_fps` - FPS used for frame indexing.
- `total_frames` - estimated total frame count from `duration * fps`.
- `video_name` - selected local video filename.
- `output_video` (Video Blend) - single blended video output.
- `output_video` (Video Color Match) - single color-matched video output.
