# PDF-to-Blender Survey Pipeline

Extract ground elevation points from topographic survey PDFs and visualize in Blender.

**Tested:** December 2025 - 557+ elevation points with pixel-perfect alignment.

---

## Quick Start

1. Set up Google Cloud credentials (one-time)
2. Run extraction: 
3. Generate Blender file: 

---

## Google Cloud Vision API Setup

### Step 1: Create Google Cloud Project

1. Go to https://console.cloud.google.com/
2. Create a new project or select existing
3. Note your Project ID

### Step 2: Enable Vision API

1. Go to APIs and Services -> Enable APIs and Services
2. Search for Cloud Vision API
3. Click Enable

### Step 3: Create Service Account

1. Go to IAM and Admin -> Service Accounts
2. Click Create Service Account
3. Name: vision-api-user (or any name)
4. Role: Cloud Vision API User
5. Click Done

### Step 4: Create and Download Key

1. Click on your new service account
2. Go to Keys tab
3. Click Add Key -> Create new key
4. Select JSON format
5. Save the downloaded file securely (e.g., vision-api.json)

### Step 5: Set Environment Variable

Windows (Command Prompt):
    set GOOGLE_APPLICATION_CREDENTIALS=C:\path	oision-api.json

Windows (PowerShell):
    :GOOGLE_APPLICATION_CREDENTIALS = "C:\path	oision-api.json"

Linux/Mac:
    export GOOGLE_APPLICATION_CREDENTIALS="/path/to/vision-api.json"

### Step 6: Install Python Dependencies

    pip install google-cloud-vision Pillow

---

## Critical Bug Fixes (IMPORTANT)

### Bug #1: Blender Image Y-Scale Compression

Symptom: Image displays at 70% of expected height.
Cause: Blender normalizes image to longest dimension, then applies scale.

    WRONG:  empty.scale = (world_width, world_height, 1.0)
    RIGHT:  empty.scale = (world_width, world_width, 1.0)  # Width for BOTH\!

### Bug #2: Decimal Separator

Symptom: Missing elevation values like 44.317.
Cause: Vision sometimes returns comma instead of period (44,317).

    Solution: Accept both . and , in regex, normalize with replace(",", ".")

### Bug #3: Image Dimensions

Symptom: Points shifted from expected positions.
Cause: Vision API text bounds are smaller than actual image.

    Solution: Use PIL Image.open(path).size, NOT max of Vision text bounds

### Bug #4: Image Anchor Offset

Symptom: Diagonal drift in point positions.
Cause: Default anchor is center (-0.5, -0.5).

    Solution: Set empty.empty_image_offset = (0, 0)

---

## Scale Calculation

### From Chainage Markers (Most Accurate)

Find chainage markers like "T 16800" and "T 17100":
    pixel_span = 7518 - 427 = 7091 pixels
    real_span = 17100 - 16800 = 300 meters
    scale = 300 / 7091 = 0.0423 m/pixel

### From Drawing Scale (Quick)

For 1:500 at 300 DPI:
    scale = 0.042 m/pixel

---

## Coordinate Transform

Image Y=0 is top, Blender Y=0 is bottom. Must flip:

    x_world = px * scale
    y_world = (image_height - py) * scale

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Y compressed | Use (width, width, 1) not (width, height, 1) |
| Points shifted | Use PIL for dimensions, not Vision bounds |
| Missing values | Accept comma decimal separator |
| Diagonal drift | Set empty_image_offset = (0, 0) |

---

## Requirements

- Python: google-cloud-vision, Pillow
- Blender 3.0+ (tested on 4.0, 5.0)

---

## Credits

Developed for BIM Syncro Engineers Sdn Bhd
Pipeline tested on Malaysian JKR road survey drawings (1:500 scale)
Version 1.0 - December 2025