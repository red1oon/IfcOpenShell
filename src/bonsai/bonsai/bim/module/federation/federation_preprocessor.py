#!/usr/bin/env python3
"""
Qualified Path: src/bonsai/bonsai/bim/module/federation/federation_preprocessor.py

Federation Preprocessor - Standalone IFC Bbox Extraction
---------------------------------------------------------
Extracts bounding boxes from multiple IFC files and stores in SQLite database
for fast spatial queries during multi-model coordination.

Usage:
    python federation_preprocessor.py \
        --files ARC.ifc ACMV.ifc STR.ifc \
        --output terminal1_federation.db \
        --disciplines ARC ACMV STR

Requirements:
    - ifcopenshell
    - sqlite3 (built-in)
    - multiprocessing (built-in)
"""

import argparse
import json
import logging
import multiprocessing
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import ifcopenshell
import ifcopenshell.geom


# Schema version for future migrations
SCHEMA_VERSION = "1.0.0"

# IFC classes to include (geometric elements only)
GEOMETRIC_CLASSES = {
    # Structural elements
    "IfcWall", "IfcWallStandardCase", "IfcCurtainWall",
    "IfcBeam", "IfcColumn", "IfcSlab", "IfcRoof", "IfcFooting", "IfcPile",
    "IfcStair", "IfcStairFlight", "IfcRamp", "IfcRampFlight",
    
    # Building elements
    "IfcDoor", "IfcWindow", "IfcPlate", "IfcMember", "IfcCovering",
    "IfcRailing", "IfcBuildingElementProxy",
    
    # MEP elements
    "IfcDuctSegment", "IfcDuctFitting", "IfcAirTerminal",
    "IfcPipeSegment", "IfcPipeFitting", "IfcFlowTerminal",
    "IfcCableCarrierSegment", "IfcCableCarrierFitting",
    "IfcCableSegment", "IfcDistributionElement",
    "IfcFlowController", "IfcFlowFitting", "IfcFlowMovingDevice",
    "IfcFlowStorageDevice", "IfcFlowTreatmentDevice",
    
    # Furniture and equipment
    "IfcFurnishingElement", "IfcFurniture", "IfcSystemFurnitureElement",
}


class ProgressTracker:
    """Track and report preprocessing progress"""
    
    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.start_time = time.time()
        self.files_processed = 0
        self.total_elements = 0
        self.file_stats = []
    
    def update_file(self, filename: str, discipline: str, element_count: int, duration: float):
        """Record statistics for a processed file"""
        self.files_processed += 1
        self.total_elements += element_count
        
        self.file_stats.append({
            "filename": filename,
            "discipline": discipline,
            "elements": element_count,
            "duration_seconds": round(duration, 2)
        })
        
        self._write_progress()
    
    def _write_progress(self):
        """Write progress to JSON file"""
        elapsed = time.time() - self.start_time
        
        progress_data = {
            "schema_version": SCHEMA_VERSION,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "in_progress" if self.files_processed > 0 else "starting",
            "files_processed": self.files_processed,
            "total_elements": self.total_elements,
            "elapsed_seconds": round(elapsed, 2),
            "files": self.file_stats
        }
        
        with open(self.output_path, 'w') as f:
            json.dump(progress_data, f, indent=2)
    
    def finalize(self, db_path: Path, success: bool = True):
        """Write final summary"""
        elapsed = time.time() - self.start_time
        
        summary = {
            "schema_version": SCHEMA_VERSION,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "completed" if success else "failed",
            "total_files": self.files_processed,
            "total_elements": self.total_elements,
            "total_duration_seconds": round(elapsed, 2),
            "database_path": str(db_path),
            "database_size_mb": round(db_path.stat().st_size / (1024 * 1024), 2) if db_path.exists() else 0,
            "files": self.file_stats
        }
        
        with open(self.output_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        return summary


class FederationPreprocessor:
    """Extract bounding boxes from IFC files for federation"""
    
    def __init__(self, output_db_path: Path, progress_file: Optional[Path] = None):
        self.output_db_path = Path(output_db_path)
        self.progress_file = progress_file or self.output_db_path.with_suffix('.json')
        self.progress = ProgressTracker(self.progress_file)
        self.logger = self._setup_logging()
    
    def _setup_logging(self) -> logging.Logger:
        """Configure logging"""
        logger = logging.getLogger('FederationPreprocessor')
        logger.setLevel(logging.INFO)
        
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
    
    def _init_database(self):
        """Create database schema"""
        conn = sqlite3.connect(self.output_db_path)
        cursor = conn.cursor()
        
        # Schema version table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_info (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES (?, ?)",
                      ("version", SCHEMA_VERSION))
        
        # Main elements table
        # Metadata table (non-spatial attributes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS elements_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guid TEXT UNIQUE NOT NULL,
                discipline TEXT NOT NULL,
                ifc_class TEXT NOT NULL,
                filepath TEXT NOT NULL
            )
        """)
        
        # Non-spatial indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_guid ON elements_meta(guid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_discipline ON elements_meta(discipline)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ifc_class ON elements_meta(ifc_class)")
        
        # Spatial index (SQLite R-tree virtual table for 3D bounding boxes)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS elements_rtree USING rtree(
                id,              -- References elements_meta.id
                min_x, max_x,    -- X-axis bounds
                min_y, max_y,    -- Y-axis bounds
                min_z, max_z     -- Z-axis bounds
            )
        """)
        
        conn.commit()
        conn.close()
        
        self.logger.info(f"Initialized database: {self.output_db_path}")
    
    def process_ifc_files(self, file_paths: List[Path], disciplines: Optional[List[str]] = None):
        """
        Process multiple IFC files and extract bounding boxes
        
        Args:
            file_paths: List of IFC file paths
            disciplines: Optional list of discipline tags (auto-detected from filenames if None)
        """
        self.logger.info(f"Starting preprocessing of {len(file_paths)} files")
        
        # Initialize database
        self._init_database()
        
        # Auto-detect disciplines from filenames if not provided
        if disciplines is None:
            disciplines = [self._detect_discipline(fp) for fp in file_paths]
        
        # Process each file
        for file_path, discipline in zip(file_paths, disciplines):
            try:
                self._process_single_file(file_path, discipline)
            except Exception as e:
                self.logger.error(f"Failed to process {file_path}: {e}")
                import traceback
                traceback.print_exc()
        
        # Finalize progress report
        summary = self.progress.finalize(self.output_db_path, success=True)
        self._print_summary(summary)
    
    def _detect_discipline(self, file_path: Path) -> str:
        """Auto-detect discipline tag from filename"""
        # Common patterns: ARC.ifc, ACMV_R01.ifc, Terminal1_STR.ifc
        stem = file_path.stem.upper()
        
        # Extract first word/abbreviation
        for part in stem.split('_'):
            if len(part) >= 2 and part.isalpha():
                return part[:10]  # Limit to 10 chars
        
        # Fallback: use stem
        return stem[:10]
    
    def _process_single_file(self, file_path: Path, discipline: str):
        """Process a single IFC file"""
        start_time = time.time()
        
        self.logger.info(f"Processing {file_path.name} (discipline: {discipline})")
        
        # Open IFC file
        ifc_file = ifcopenshell.open(file_path)
        
        # Extract bounding boxes
        elements_data = self._extract_bboxes_multicore(ifc_file, file_path, discipline)
        
        # Store to database
        self._store_to_database(elements_data)
        
        # Update progress
        duration = time.time() - start_time
        self.progress.update_file(
            filename=file_path.name,
            discipline=discipline,
            element_count=len(elements_data),
            duration=duration
        )
        
        self.logger.info(f"✓ Completed {file_path.name}: {len(elements_data)} elements in {duration:.1f}s")
    
    def _extract_bboxes_multicore(self, ifc_file: ifcopenshell.file, 
                                   file_path: Path, discipline: str) -> List[Dict]:
        """Extract bounding boxes using multicore geometry processing"""
        elements_data = []
        
        # Create geometry settings
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        # Create iterator with multicore support
        num_cores = multiprocessing.cpu_count()
        iterator = ifcopenshell.geom.iterator(settings, ifc_file, num_cores)
        
        if not iterator.initialize():
            self.logger.warning(f"Failed to initialize geometry iterator for {file_path.name}")
            return elements_data
        
        processed_count = 0
        while True:
            try:
                shape = iterator.get()
                element = ifc_file.by_id(shape.id)
                
                # Filter to geometric elements only
                if element.is_a() not in GEOMETRIC_CLASSES:
                    if not iterator.next():
                        break
                    continue
                
                # Extract bounding box from geometry
                bbox = self._calculate_bbox(shape)
                
                if bbox:
                    global_id = getattr(element, 'GlobalId', None)
                    if not global_id:
                        # Generate fallback ID
                        global_id = f"NO_GUID_{element.id()}"
                    
                    elements_data.append({
                        'guid': global_id,
                        'discipline': discipline,
                        'ifc_class': element.is_a(),
                        'min_x': bbox[0],
                        'min_y': bbox[1],
                        'min_z': bbox[2],
                        'max_x': bbox[3],
                        'max_y': bbox[4],
                        'max_z': bbox[5],
                        'filepath': str(file_path.absolute())
                    })
                    
                    processed_count += 1
                    if processed_count % 1000 == 0:
                        self.logger.info(f"  Processed {processed_count} elements...")
                
            except Exception as e:
                self.logger.warning(f"  Skipping element due to error: {e}")
            
            if not iterator.next():
                break
        
        return elements_data
    
    def _calculate_bbox(self, shape) -> Optional[Tuple[float, float, float, float, float, float]]:
        """Calculate bounding box from shape geometry"""
        try:
            # Get vertices from geometry
            geometry = shape.geometry
            verts = geometry.verts
            
            # Group into (x, y, z) tuples
            vertices = [(verts[i], verts[i+1], verts[i+2]) 
                       for i in range(0, len(verts), 3)]
            
            if not vertices:
                return None
            
            # Calculate min/max for each axis
            xs, ys, zs = zip(*vertices)
            
            return (
                min(xs), min(ys), min(zs),  # min_x, min_y, min_z
                max(xs), max(ys), max(zs)   # max_x, max_y, max_z
            )
            
        except Exception as e:
            self.logger.debug(f"Failed to calculate bbox: {e}")
            return None
    
    def _store_to_database(self, elements_data: List[Dict]):
        """Store element data to SQLite database (metadata + spatial R-tree)"""
        if not elements_data:
            return
        
        conn = sqlite3.connect(self.output_db_path)
        cursor = conn.cursor()
        
        # Insert each element into both tables
        for elem in elements_data:
            # Insert metadata first
            cursor.execute("""
                INSERT OR REPLACE INTO elements_meta (guid, discipline, ifc_class, filepath)
                VALUES (?, ?, ?, ?)
            """, (elem['guid'], elem['discipline'], elem['ifc_class'], elem['filepath']))
            
            # Get the ID (either newly inserted or existing)
            cursor.execute("SELECT id FROM elements_meta WHERE guid = ?", (elem['guid'],))
            elem_id = cursor.fetchone()[0]
            
            # Delete old R-tree entry if exists (can't update R-tree, must delete+insert)
            cursor.execute("DELETE FROM elements_rtree WHERE id = ?", (elem_id,))
            
            # Insert into R-tree
            cursor.execute("""
                INSERT INTO elements_rtree (id, min_x, max_x, min_y, max_y, min_z, max_z)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (elem_id, elem['min_x'], elem['max_x'], 
                  elem['min_y'], elem['max_y'], elem['min_z'], elem['max_z']))
        
        conn.commit()
        conn.close()
    
    def _print_summary(self, summary: Dict):
        """Print final summary to console"""
        print("\n" + "="*60)
        print("FEDERATION PREPROCESSING COMPLETE")
        print("="*60)
        print(f"Status:           {summary['status']}")
        print(f"Total Files:      {summary['total_files']}")
        print(f"Total Elements:   {summary['total_elements']:,}")
        print(f"Duration:         {summary['total_duration_seconds']:.1f} seconds")
        print(f"Database:         {summary['database_path']}")
        print(f"Database Size:    {summary['database_size_mb']:.2f} MB")
        print(f"Progress Report:  {self.progress_file}")
        print("\nPer-File Statistics:")
        print("-"*60)
        for file_stat in summary['files']:
            print(f"  {file_stat['filename']:<30} "
                  f"{file_stat['discipline']:<8} "
                  f"{file_stat['elements']:>6} elements "
                  f"({file_stat['duration_seconds']:.1f}s)")
        print("="*60 + "\n")


def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(
        description="Extract bounding boxes from IFC files for multi-model federation"
    )
    parser.add_argument(
        '--files', 
        nargs='+', 
        required=True,
        help='IFC file paths to process'
    )
    parser.add_argument(
        '--output', 
        required=True,
        help='Output SQLite database path'
    )
    parser.add_argument(
        '--disciplines',
        nargs='+',
        help='Discipline tags (auto-detected from filenames if omitted)'
    )
    parser.add_argument(
        '--progress',
        help='Progress report JSON file path (default: output_path.json)'
    )
    
    args = parser.parse_args()
    
    # Convert to Path objects
    file_paths = [Path(f) for f in args.files]
    output_path = Path(args.output)
    progress_path = Path(args.progress) if args.progress else None
    
    # Validate input files exist
    for file_path in file_paths:
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}")
            return 1
    
    # Process files
    preprocessor = FederationPreprocessor(output_path, progress_path)
    preprocessor.process_ifc_files(file_paths, args.disciplines)
    
    return 0


if __name__ == "__main__":
    exit(main())