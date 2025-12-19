#!/usr/bin/env python3
"""
Compare Opus vs Claude extractions and generate diff report + blend file
"""

import json
from pathlib import Path

def load_json(path):
    with open(path) as f:
        return json.load(f)

def main():
    base = Path(__file__).parent

    # Load both extractions
    opus = load_json(base / "opus_full" / "z_positions_complete.json")
    claude = load_json(base / "claude_extraction.json")

    opus_points = {round(p['z'], 3): p for p in opus['points']}
    claude_points = {round(p['z'], 3): p for p in claude['points']}

    opus_zs = set(opus_points.keys())
    claude_zs = set(claude_points.keys())

    # Analysis
    common = opus_zs & claude_zs
    only_opus = opus_zs - claude_zs
    only_claude = claude_zs - opus_zs

    print("=" * 60)
    print("EXTRACTION COMPARISON: Opus vs Claude")
    print("=" * 60)
    print(f"\nOpus points:   {len(opus_zs)}")
    print(f"Claude points: {len(claude_zs)}")
    print(f"\nCommon Z values: {len(common)}")
    print(f"Only in Opus:    {len(only_opus)}")
    print(f"Only in Claude:  {len(only_claude)}")

    # Position differences for common Z values
    print("\n" + "-" * 60)
    print("POSITION DIFFERENCES (common Z values)")
    print("-" * 60)

    diffs = []
    for z in sorted(common):
        op = opus_points[z]
        cp = claude_points[z]
        dx = abs(op['x'] - cp['x'])
        dy = abs(op['y'] - cp['y'])
        dist = (dx**2 + dy**2) ** 0.5
        if dist > 10:  # Significant difference
            diffs.append({
                'z': z,
                'opus_x': op['x'], 'opus_y': op['y'],
                'claude_x': cp['x'], 'claude_y': cp['y'],
                'distance': dist
            })

    if diffs:
        print(f"\nSignificant position differences (>10px): {len(diffs)}")
        for d in sorted(diffs, key=lambda x: -x['distance'])[:10]:
            print(f"  Z={d['z']:.3f}: Opus({d['opus_x']:.0f},{d['opus_y']:.0f}) vs Claude({d['claude_x']:.0f},{d['claude_y']:.0f}) = {d['distance']:.1f}px")
    else:
        print("\nNo significant position differences!")

    # Z values only in one extraction
    if only_opus:
        print(f"\nZ values only in Opus ({len(only_opus)}):")
        for z in sorted(only_opus)[:10]:
            print(f"  {z:.3f}")
        if len(only_opus) > 10:
            print(f"  ... and {len(only_opus) - 10} more")

    if only_claude:
        print(f"\nZ values only in Claude ({len(only_claude)}):")
        for z in sorted(only_claude)[:10]:
            print(f"  {z:.3f}")
        if len(only_claude) > 10:
            print(f"  ... and {len(only_claude) - 10} more")

    # Create combined JSON for diff blend
    combined = {
        'metadata': {
            'source': 'Comparison: Opus vs Claude extraction',
            'image_dimensions': {'width': 400, 'height': 400},
            'scale': 0.1,
            'opus_count': len(opus_zs),
            'claude_count': len(claude_zs),
            'common_count': len(common)
        },
        'ground_elevations': []
    }

    # Add Claude points (these will be displayed)
    for i, pt in enumerate(claude['points']):
        combined['ground_elevations'].append({
            'id': f'CLAUDE_{i+1:03d}',
            'x': pt['x'],
            'y': pt['y'],
            'z': pt['z']
        })

    # Save combined JSON
    out_path = base / "claude_formatted.json"
    with open(out_path, 'w') as f:
        json.dump(combined, f, indent=2)

    print(f"\nSaved formatted JSON: {out_path}")
    print(f"  Points: {len(combined['ground_elevations'])}")

    # Summary stats
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    agreement = len(common) / max(len(opus_zs), len(claude_zs)) * 100
    print(f"Agreement rate: {agreement:.1f}%")
    print(f"Average position diff: {sum(d['distance'] for d in diffs)/len(diffs):.1f}px" if diffs else "Position diff: N/A")

if __name__ == "__main__":
    main()
