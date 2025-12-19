# Sample Files

## sample_output.json

This is a real extraction from a Malaysian JKR survey drawing (1:500 scale).

Contains:
- 557 ground elevation points
- Pixel coordinates from Google Vision OCR
- Scale: 0.0423 m/pixel (calculated from chainage markers)
- Image dimensions: 9934 x 7017 pixels

## To Test Without the Original PNG

You can test the Blender import script with any PNG:

1. Create a blank 9934x7017 image (or any size)
2. Update sample_output.json metadata to match your image dimensions
3. Run: blender --background --python scripts/survey_to_blend.py -- samples/sample_output.json your_image.png output.blend

## Original Survey Image

The original survey_highres.png is ~8.6 MB and not included in the repo.
Contact BIM Syncro Engineers for sample survey images.
