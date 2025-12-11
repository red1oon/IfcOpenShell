#!/usr/bin/env python3
"""
River Utilities

Collection of utility functions for river monitoring equipment management
and validation in Blender federation models.
"""

import bpy
from collections import defaultdict


def check_duplicate_equipment():
    """
    Check for equipment objects sharing the same location.

    Returns:
        tuple: (duplicates_found: bool, duplicate_locations: dict)

    Usage:
        duplicates, locations = check_duplicate_equipment()
        if duplicates:
            for loc, items in locations.items():
                print(f"Duplicate at {loc}: {items}")
    """
    # Dictionary to group equipment by location
    location_groups = defaultdict(list)

    # Collect all equipment objects
    for obj in bpy.data.objects:
        # Match equipment naming pattern (contains 'Equipment' or ends with _NNN)
        if 'Equipment' in obj.name or obj.name.split('_')[-1].isdigit():
            # Round location to 3 decimal places to handle floating point precision
            loc = tuple(round(coord, 3) for coord in obj.location)
            location_groups[loc].append(obj.name)

    # Find locations with multiple equipment
    duplicate_locations = {
        loc: items for loc, items in location_groups.items() if len(items) > 1
    }

    return len(duplicate_locations) > 0, duplicate_locations


def print_duplicate_equipment_report():
    """Print a formatted report of duplicate equipment locations."""
    duplicates_found, duplicate_locations = check_duplicate_equipment()

    if not duplicates_found:
        print('✓ No equipment found at the same location.')
        return

    print('\n⚠ DUPLICATE EQUIPMENT LOCATIONS FOUND:\n')
    for location, equipment in sorted(duplicate_locations.items()):
        print(f'Location {location}:')
        for item in sorted(equipment):
            print(f'  - {item}')

    print(f'\n⚠ Locations with duplicates: {len(duplicate_locations)}')


# Standalone script mode
if __name__ == "__main__":
    print_duplicate_equipment_report()
