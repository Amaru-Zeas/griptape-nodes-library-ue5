# SAM2 Point Picker Library for Griptape Nodes

Artist-friendly point-driven segmentation with SAM2.

## Included Node

- **Image Mask via Point Picker + SAM2**
  - Load your image
  - Click positive and negative points in the widget
  - Run the node to output a binary mask

## Inputs

- `input_image` (`ImageArtifact` or `ImageUrlArtifact`)
- `sam2_model` (Hugging Face repo selector)
- `mask_threshold`
- `multimask_output`

## Outputs

- `output_mask`
- `sam_points`
- `status_message`

## Notes

- First run loads image preview into widget.
- After adding points, run again to regenerate the mask.
