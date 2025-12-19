#!/usr/bin/env python3
"""Convert z_positions_complete.json to survey_to_blend.py expected format"""

import json
from pathlib import Path

# Load original
input_path = Path(__file__).parent / "opus_full" / "z_positions_complete.json"
with open(input_path) as f:
    data = json.load(f)

# Convert to expected format
output = {
    'metadata': {
        'source': data['metadata']['source'],
        'image_dimensions': {
            'width': 400,  # 400x400 crop
            'height': 400
        },
        'scale': 0.1,  # 1 pixel = 0.1 meters
        'point_count': data['metadata']['point_count']
    },
    'ground_elevations': []
}

# Convert points - add 'id' field
for i, pt in enumerate(data['points']):
    output['ground_elevations'].append({
        'id': f'PT_{i+1:03d}',
        'x': pt['x'],
        'y': pt['y'],
        'z': pt['z']
    })

# Save
out_path = Path(__file__).parent / "opus_full" / "survey_formatted.json"
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)

print(f'Created: {out_path}')
print(f'Points: {len(output["ground_elevations"])}')
