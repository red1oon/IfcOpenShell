#!/usr/bin/env python3
"""
Extract tiles from survey image for AI processing.
Creates manageable tile images that can be read by AI for elevation extraction.
"""

import json
from pathlib import Path
from PIL import Image


def extract_tiles(image_path: str, output_dir: str, tile_size: int = 1500):
    """Extract tiles from image for AI processing."""

    print(f"Loading image: {image_path}")
    img = Image.open(image_path)
    width, height = img.size
    print(f"Image size: {width} x {height} pixels")

    tiles_dir = Path(output_dir) / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    tiles = []
    tile_id = 0

    for y in range(0, height, tile_size):
        for x in range(0, width, tile_size):
            # Calculate tile bounds
            x2 = min(x + tile_size, width)
            y2 = min(y + tile_size, height)

            # Extract tile
            tile = img.crop((x, y, x2, y2))
            tile_path = tiles_dir / f"tile_{tile_id:03d}_x{x}_y{y}.png"
            tile.save(tile_path, optimize=True)

            tiles.append({
                "id": tile_id,
                "path": str(tile_path),
                "x_offset": x,
                "y_offset": y,
                "width": x2 - x,
                "height": y2 - y
            })

            tile_id += 1
            print(f"  Tile {tile_id}: ({x}, {y}) - ({x2}, {y2})")

    # Save tile metadata
    metadata = {
        "source_image": str(image_path),
        "image_width": width,
        "image_height": height,
        "tile_size": tile_size,
        "tile_count": len(tiles),
        "tiles": tiles
    }

    with open(Path(output_dir) / "tiles_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nGenerated {len(tiles)} tiles")
    return metadata


if __name__ == "__main__":
    base = Path(__file__).parent
    extract_tiles(
        str(base / "survey_highres.png"),
        str(base / "raster_output"),
        tile_size=1500
    )
