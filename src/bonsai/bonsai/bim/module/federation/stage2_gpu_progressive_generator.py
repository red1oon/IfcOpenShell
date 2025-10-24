"""
Stage 2 GPU Progressive Loading - Generator Version
====================================================

Non-blocking generator that yields progress after each priority batch.
Enables truly responsive UI during loading.
"""

import bpy
import sqlite3
import time
from typing import Dict, Generator, Any
from . import semantic_utils
from .stage2_gpu_instancing import (
    get_template_object,
    calculate_transform_from_bbox,
    clear_template_cache
)


def create_semantic_shapes_progressive_generator(
    db_conn: sqlite3.Connection,
    parent_collection: bpy.types.Collection,
    discipline_collections: Dict[str, bpy.types.Collection]
) -> Generator[Dict[str, Any], None, None]:
    """
    Generator version of progressive loading - yields after each priority batch.

    Enables non-blocking loading by yielding control back to Blender's event loop
    after processing each priority level.

    Args:
        db_conn: SQLite database connection
        parent_collection: Parent federation collection
        discipline_collections: Dict to store discipline collections

    Yields:
        Progress dict with status='batch_complete' or 'complete'

    Example:
        gen = create_semantic_shapes_progressive_generator(conn, coll, disc_colls)
        for result in gen:
            if result['status'] == 'batch_complete':
                print(f"Priority {result['priority']} done")
            elif result['status'] == 'complete':
                instances = result['instances']
                break
    """

    print("\n" + "=" * 70)
    print("STAGE 2: PROGRESSIVE GPU INSTANCING (NON-BLOCKING GENERATOR)")
    print("=" * 70)

    start_time = time.time()

    # Clear template caches
    clear_template_cache()

    # NOTE: Site offset not needed! elements_rtree stores coordinates in site-local
    # system (already near origin), not world coordinates. Just convert mm → meters.

    # Query all elements from database
    cursor = db_conn.cursor()
    print("Querying database...")
    cursor.execute("""
        SELECT
            m.guid,
            m.ifc_class,
            m.discipline,
            r.min_x, r.min_y, r.min_z,
            r.max_x, r.max_y, r.max_z
        FROM elements_meta m
        JOIN elements_rtree r ON m.id = r.id
    """)

    elements = cursor.fetchall()
    total = len(elements)
    print(f"✓ Found {total:,} elements")

    # Import priority system from main module
    from .stage2_gpu_progressive import ELEMENT_PRIORITIES, get_element_priority

    # Sort by priority
    print(f"\nSorting by priority (surface elements first)...")
    elements_sorted = sorted(
        elements,
        key=lambda elem: get_element_priority(
            ifc_class=elem[1],
            min_z=elem[5],
            max_z=elem[8]
        )
    )
    print(f"✓ Sorted - surface elements will load first!")

    # Group by priority for batch processing
    priority_batches = {}
    for elem in elements_sorted:
        priority = get_element_priority(elem[1], elem[5], elem[8])
        priority_level = int(priority)
        if priority_level not in priority_batches:
            priority_batches[priority_level] = []
        priority_batches[priority_level].append(elem)

    print(f"\nPriority breakdown:")
    for level in sorted(priority_batches.keys()):
        count = len(priority_batches[level])
        pct = (count / total) * 100
        if level == 1:
            desc = "Surface (walls, roofs, slabs)"
        elif level == 2:
            desc = "Openings (windows, doors)"
        elif level == 3:
            desc = "MEP (pipes, ducts, conduits)"
        elif level == 4:
            desc = "Structure (beams, columns)"
        else:
            desc = "Interior/Equipment"
        print(f"  Priority {level}: {count:,} elements ({pct:.1f}%) - {desc}")

    print(f"\nCreating instances with NON-BLOCKING progressive loading...")
    print(f"🎯 GOAL: UI stays responsive, yields after each priority batch")
    print()

    instances = []
    instances_by_discipline = {}
    templates_used = set()
    elements_processed = 0

    # Process each priority batch
    for priority_level in sorted(priority_batches.keys()):
        batch = priority_batches[priority_level]
        batch_start = time.time()

        # Show what's loading
        if priority_level == 1:
            batch_desc = "🏢 SURFACE ELEMENTS (walls, roofs, slabs)"
        elif priority_level == 2:
            batch_desc = "🪟 OPENINGS (windows, doors)"
        elif priority_level == 3:
            batch_desc = "🔧 MEP SYSTEMS (pipes, ducts, conduits)"
        elif priority_level == 4:
            batch_desc = "🏗️  STRUCTURE (beams, columns)"
        else:
            batch_desc = "🪑 INTERIOR/EQUIPMENT"

        print(f"Loading Priority {priority_level}: {batch_desc}")
        print(f"  Elements: {len(batch):,}")

        # Create instances for this batch
        for idx, elem in enumerate(batch):
            guid, ifc_class, discipline = elem[0], elem[1], elem[2]
            min_x, min_y, min_z, max_x, max_y, max_z = elem[3:9]
            bbox = (min_x, min_y, min_z, max_x, max_y, max_z)

            # Infer semantic type
            semantic_type = semantic_utils.get_semantic_type(ifc_class)

            # Get or create template
            template_obj = get_template_object(semantic_type, ifc_class, parent_collection)
            templates_used.add(f"{semantic_type}_{ifc_class}")

            # Calculate transform
            location, scale, rotation = calculate_transform_from_bbox(bbox, semantic_type, ifc_class)

            # NOTE: Bbox coordinates in elements_rtree are already in site-local coords
            # (near origin), so NO offset needed!

            # Create instance
            instance = bpy.data.objects.new(guid, template_obj.data)
            instance.location = location
            instance.scale = scale
            instance.rotation_euler = rotation

            # Store metadata
            instance['ifc_class'] = ifc_class
            instance['guid'] = guid
            instance['discipline'] = discipline
            instance['is_gpu_instance'] = True
            instance['template_type'] = f"{semantic_type}_{ifc_class}"
            instance['priority'] = priority_level

            # Group by discipline
            if discipline not in instances_by_discipline:
                instances_by_discipline[discipline] = []
            instances_by_discipline[discipline].append(instance)

            instances.append(instance)
            elements_processed += 1

            # Progress within batch (every 1000 elements)
            if (idx + 1) % 1000 == 0:
                batch_elapsed = time.time() - batch_start
                print(f"    ⏳ {idx+1:,}/{len(batch):,} ({batch_elapsed:.1f}s)")

        batch_elapsed = time.time() - batch_start
        total_elapsed = time.time() - start_time

        print(f"  ✓ Priority {priority_level} complete: {len(batch):,} elements in {batch_elapsed:.2f}s")
        print(f"  ✓ Total progress: {elements_processed:,}/{total:,} ({total_elapsed:.1f}s elapsed)")

        # YIELD after each priority batch - returns control to Blender!
        yield {
            'status': 'batch_complete',
            'priority': priority_level,
            'batch_size': len(batch),
            'processed': elements_processed,
            'total': total,
            'elapsed': total_elapsed
        }

        # Small pause between batches
        if priority_level < max(priority_batches.keys()):
            print(f"  ⏸️  Pausing 0.5s before next priority batch...")
            time.sleep(0.5)
        print()

    # All instances created - now link to collections
    print(f"\nLinking {len(instances):,} instances to collections...")
    link_start = time.time()

    for discipline, disc_instances in instances_by_discipline.items():
        # Create discipline collection
        if discipline not in discipline_collections:
            disc_coll = bpy.data.collections.new(f"Discipline_{discipline}")
            parent_collection.children.link(disc_coll)
            discipline_collections[discipline] = disc_coll

        # Batch link
        collection = discipline_collections[discipline]
        for instance in disc_instances:
            collection.objects.link(instance)

    link_elapsed = time.time() - link_start
    print(f"✓ Collection linking: {link_elapsed:.2f}s")

    # Final scene update
    print(f"\nFinal scene update...")
    final_update_start = time.time()
    bpy.context.view_layer.update()
    final_update_elapsed = time.time() - final_update_start
    print(f"✓ Final update complete ({final_update_elapsed:.2f}s)")

    # Results
    total_elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print("PROGRESSIVE LOADING COMPLETE")
    print("=" * 70)
    print(f"✓ Total instances: {len(instances):,}")
    print(f"✓ Unique templates: {len(templates_used)}")
    print(f"✓ Total time: {total_elapsed:.2f}s")
    print(f"✓ Time per instance: {(total_elapsed / total * 1000):.3f}ms")

    if not bpy.app.background:
        print("\n🖱️  LOADING COMPLETE - VIEWPORT NOW RESPONSIVE!")
        print("  ✓ Mouse works normally")
        print("  ✓ Outliner accessible")
        print("  ✓ Safe to start coordination work")

    print("=" * 70)

    # FINAL YIELD with complete status and results
    yield {
        'status': 'complete',
        'instances': instances,
        'templates_used': templates_used,
        'total_time': total_elapsed,
        'instances_by_discipline': instances_by_discipline
    }
