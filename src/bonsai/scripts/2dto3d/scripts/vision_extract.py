#!/usr/bin/env python3
"""
Vision API Extraction - Step 2 of 2D-to-3D Pipeline

Extracts text with pixel positions using Google Cloud Vision API.
ONE API call per image, cached forever for repeated runs.

CRITICAL: This script checks for cached JSON before calling API.
If cache exists, it loads from cache (no API call).
"""

import sys
import json
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)


def get_cache_path(image_path: str, cache_dir: str = None) -> Path:
    """Get the cache file path for an image."""
    image_path = Path(image_path)
    if cache_dir:
        cache_path = Path(cache_dir)
    else:
        # Default: same directory as image
        cache_path = image_path.parent

    return cache_path / f"{image_path.stem}_raw.json"


def load_from_cache(cache_file: Path) -> dict:
    """Load extraction from cache if it exists."""
    if cache_file.exists():
        print(f"CACHE HIT: Loading from {cache_file.name}")
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_to_cache(data: dict, cache_file: Path):
    """Save extraction to cache."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"CACHED: Saved to {cache_file.name}")


def extract_from_image(image_path: str, cache_dir: str = None, force: bool = False) -> dict:
    """
    Extract text + positions using Google Vision API.

    Args:
        image_path: Path to PNG image
        cache_dir: Directory for cache files (default: same as image)
        force: If True, ignore cache and call API anyway

    Returns:
        Extraction dictionary with metadata and text_items
    """
    image_path = Path(image_path)
    cache_file = get_cache_path(image_path, cache_dir)

    # Check cache first (unless force=True)
    if not force:
        cached = load_from_cache(cache_file)
        if cached:
            return cached

    # No cache - need to call Vision API
    print(f"CACHE MISS: Calling Vision API for {image_path.name}")

    try:
        from google.cloud import vision
    except ImportError:
        print("ERROR: google-cloud-vision not installed.")
        print("Run: pip install google-cloud-vision")
        sys.exit(1)

    # Check credentials
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        # Try default location
        default_creds = Path("C:/Dev/bonsai-extensions/WORK_DIR/vision-api.json")
        if default_creds.exists():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(default_creds)
            print(f"Using credentials: {default_creds}")
        else:
            print("ERROR: GOOGLE_APPLICATION_CREDENTIALS not set")
            print("Set it with: $env:GOOGLE_APPLICATION_CREDENTIALS='path/to/credentials.json'")
            sys.exit(1)

    # CRITICAL: Get image dimensions from PIL (not API bounds)
    img = Image.open(image_path)
    width, height = img.size
    print(f"Image dimensions (PIL): {width} x {height}")

    # Call Vision API
    client = vision.ImageAnnotatorClient()

    with open(image_path, 'rb') as f:
        content = f.read()

    image = vision.Image(content=content)

    print("Calling Vision API (document_text_detection)...")
    response = client.document_text_detection(image=image)

    if response.error.message:
        raise Exception(f"Vision API error: {response.error.message}")

    # Process annotations
    extractions = []

    # Skip first annotation (full text block)
    for text in response.text_annotations[1:]:
        vertices = text.bounding_poly.vertices

        # Calculate center point
        x = sum(v.x for v in vertices) / 4
        y = sum(v.y for v in vertices) / 4

        extractions.append({
            "text": text.description.strip(),
            "x": round(x, 1),
            "y": round(y, 1),
            "bbox": {
                "x1": vertices[0].x if vertices[0].x else 0,
                "y1": vertices[0].y if vertices[0].y else 0,
                "x2": vertices[2].x if vertices[2].x else 0,
                "y2": vertices[2].y if vertices[2].y else 0
            }
        })

    result = {
        "metadata": {
            "source": str(image_path),
            "image_dimensions": {"width": width, "height": height},
            "extraction_count": len(extractions),
            "api_called": True
        },
        "text_items": extractions
    }

    print(f"Extracted {len(extractions)} text items")

    # Save to cache
    save_to_cache(result, cache_file)

    return result


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python vision_extract.py <image_path> [cache_dir] [--force]")
        print("")
        print("Examples:")
        print("  python vision_extract.py page1.png")
        print("  python vision_extract.py page1.png ../CACHE")
        print("  python vision_extract.py page1.png ../CACHE --force")
        print("")
        print("Options:")
        print("  --force  : Ignore cache and call API anyway")
        print("")
        print("NOTE: Cached results are used by default. API is only called once.")
        sys.exit(1)

    image_path = sys.argv[1]
    cache_dir = None
    force = False

    for arg in sys.argv[2:]:
        if arg == "--force":
            force = True
        else:
            cache_dir = arg

    result = extract_from_image(image_path, cache_dir, force)

    print("")
    print(f"Total text items: {result['metadata']['extraction_count']}")
    print(f"Image size: {result['metadata']['image_dimensions']['width']} x {result['metadata']['image_dimensions']['height']}")


if __name__ == "__main__":
    main()
