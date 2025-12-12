# Bonsai - OpenBIM Blender Add-on
# River Map Cache - Aggressive tile caching with LRU eviction
# Minimizes API calls through intelligent cache management

"""
River Map Cache - Tile Cache Management
========================================
Manages cached Google Maps tiles with LRU eviction policy
and cost tracking to maximize use of free tier.

Features:
- Aggressive caching (never refetch same tile)
- LRU eviction when cache size limit reached
- Cost tracking and usage logs
- Cache statistics and health monitoring
"""

import sqlite3
from pathlib import Path
from typing import Dict, Tuple, Optional, List
from datetime import datetime
import hashlib
import json
import urllib.request
import urllib.parse


# =============================================================================
# TILE CACHE MANAGER
# =============================================================================

class TileCache:
    """Manage cached map tiles with LRU eviction"""

    def __init__(self, cache_dir: Path, max_size_mb: int = 500):
        """Initialize tile cache

        Args:
            cache_dir: Directory to store cached tiles
            max_size_mb: Maximum cache size in MB (default 500 MB)
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.max_size_bytes = max_size_mb * 1024 * 1024

        # Cache metadata database
        self.db_path = self.cache_dir / "cache_metadata.db"
        self._init_cache_db()

    def _init_cache_db(self):
        """Initialize cache metadata database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create cache entries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                tile_id TEXT PRIMARY KEY,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                zoom INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_accessed_at TEXT NOT NULL,
                access_count INTEGER DEFAULT 1
            )
        """)

        # Create API usage log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                tile_id TEXT NOT NULL,
                cost REAL NOT NULL,
                cached INTEGER NOT NULL,
                layer_type TEXT
            )
        """)

        conn.commit()
        conn.close()

    def get_tile_id(self, lat: float, lon: float, zoom: int) -> str:
        """Generate unique tile ID"""
        # Use hash for compact ID
        tile_str = f"{lat:.6f}_{lon:.6f}_{zoom}"
        return hashlib.md5(tile_str.encode()).hexdigest()[:16]

    def get_cache_path(self, lat: float, lon: float, zoom: int) -> Path:
        """Get cache file path for tile"""
        tile_id = self.get_tile_id(lat, lon, zoom)
        filename = f"tile_{tile_id}_z{zoom}.jpg"
        return self.cache_dir / filename

    def is_cached(self, lat: float, lon: float, zoom: int) -> bool:
        """Check if tile is already cached"""
        cache_path = self.get_cache_path(lat, lon, zoom)
        return cache_path.exists()

    def get_cached_tile(self, lat: float, lon: float, zoom: int) -> Optional[str]:
        """Get cached tile path and update access time"""
        if not self.is_cached(lat, lon, zoom):
            return None

        cache_path = self.get_cache_path(lat, lon, zoom)
        tile_id = self.get_tile_id(lat, lon, zoom)

        # Update access time and count
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE cache_entries
            SET last_accessed_at = ?,
                access_count = access_count + 1
            WHERE tile_id = ?
        """, (datetime.now().isoformat(), tile_id))

        conn.commit()
        conn.close()

        return str(cache_path)

    def add_tile_to_cache(self, lat: float, lon: float, zoom: int, tile_data: bytes) -> str:
        """Add new tile to cache"""
        cache_path = self.get_cache_path(lat, lon, zoom)
        tile_id = self.get_tile_id(lat, lon, zoom)

        # Save tile file
        with open(cache_path, 'wb') as f:
            f.write(tile_data)

        file_size = len(tile_data)

        # Add to metadata database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT OR REPLACE INTO cache_entries
            (tile_id, lat, lon, zoom, file_path, file_size, created_at, last_accessed_at, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (tile_id, lat, lon, zoom, str(cache_path), file_size, now, now))

        conn.commit()
        conn.close()

        # Check if cache size exceeded and evict if needed
        self._check_and_evict_lru()

        return str(cache_path)

    def _check_and_evict_lru(self):
        """Check cache size and evict least recently used tiles if exceeded"""
        total_size = self.get_cache_size_bytes()

        if total_size <= self.max_size_bytes:
            return

        print(f"⚠️  Cache size ({total_size/1024/1024:.1f} MB) exceeds limit ({self.max_size_bytes/1024/1024:.1f} MB)")
        print("   Running LRU eviction...")

        # Get tiles ordered by last access (oldest first)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT tile_id, file_path, file_size, last_accessed_at
            FROM cache_entries
            ORDER BY last_accessed_at ASC
        """)

        tiles = cursor.fetchall()
        bytes_to_free = total_size - self.max_size_bytes

        evicted_count = 0
        freed_bytes = 0

        for tile_id, file_path, file_size, last_accessed in tiles:
            if freed_bytes >= bytes_to_free:
                break

            # Delete file
            path = Path(file_path)
            if path.exists():
                path.unlink()

            # Delete from database
            cursor.execute("DELETE FROM cache_entries WHERE tile_id = ?", (tile_id,))

            evicted_count += 1
            freed_bytes += file_size

        conn.commit()
        conn.close()

        print(f"✅ Evicted {evicted_count} tiles, freed {freed_bytes/1024/1024:.1f} MB")

    def get_cache_size_bytes(self) -> int:
        """Get total cache size in bytes"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT SUM(file_size) FROM cache_entries")
        result = cursor.fetchone()[0]

        conn.close()

        return result if result else 0

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total entries
        cursor.execute("SELECT COUNT(*) FROM cache_entries")
        count = cursor.fetchone()[0]

        # Total size
        cursor.execute("SELECT SUM(file_size) FROM cache_entries")
        size_bytes = cursor.fetchone()[0] or 0

        # Most accessed tiles
        cursor.execute("""
            SELECT lat, lon, zoom, access_count
            FROM cache_entries
            ORDER BY access_count DESC
            LIMIT 5
        """)
        top_tiles = cursor.fetchall()

        # Zoom level distribution
        cursor.execute("""
            SELECT zoom, COUNT(*) as count
            FROM cache_entries
            GROUP BY zoom
            ORDER BY zoom
        """)
        zoom_dist = cursor.fetchall()

        conn.close()

        return {
            'count': count,
            'size_bytes': size_bytes,
            'size_mb': size_bytes / 1024 / 1024,
            'max_size_mb': self.max_size_bytes / 1024 / 1024,
            'usage_percent': (size_bytes / self.max_size_bytes * 100) if self.max_size_bytes > 0 else 0,
            'top_tiles': top_tiles,
            'zoom_distribution': zoom_dist
        }

    def log_api_call(self, lat: float, lon: float, zoom: int, cost: float, cached: bool, layer_type: str = 'satellite'):
        """Log API call for tracking"""
        tile_id = self.get_tile_id(lat, lon, zoom)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO api_usage_log
            (timestamp, tile_id, cost, cached, layer_type)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), tile_id, cost, int(cached), layer_type))

        conn.commit()
        conn.close()

    def get_api_usage_stats(self) -> Dict:
        """Get API usage statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total API calls (non-cached)
        cursor.execute("SELECT COUNT(*) FROM api_usage_log WHERE cached = 0")
        api_calls = cursor.fetchone()[0]

        # Total cost
        cursor.execute("SELECT SUM(cost) FROM api_usage_log WHERE cached = 0")
        total_cost = cursor.fetchone()[0] or 0.0

        # Total requests (including cached)
        cursor.execute("SELECT COUNT(*) FROM api_usage_log")
        total_requests = cursor.fetchone()[0]

        # Cached requests
        cursor.execute("SELECT COUNT(*) FROM api_usage_log WHERE cached = 1")
        cached_requests = cursor.fetchone()[0]

        conn.close()

        free_tier = 200.0  # $200/month
        remaining = free_tier - total_cost

        return {
            'api_calls': api_calls,
            'total_cost': total_cost,
            'free_tier': free_tier,
            'remaining': remaining,
            'remaining_percent': (remaining / free_tier * 100) if free_tier > 0 else 0,
            'total_requests': total_requests,
            'cached_requests': cached_requests,
            'cache_hit_rate': (cached_requests / total_requests * 100) if total_requests > 0 else 0
        }

    def clear_cache(self):
        """Clear all cached tiles"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all file paths
        cursor.execute("SELECT file_path FROM cache_entries")
        files = cursor.fetchall()

        # Delete all files
        deleted = 0
        for (file_path,) in files:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                deleted += 1

        # Clear database
        cursor.execute("DELETE FROM cache_entries")
        conn.commit()
        conn.close()

        print(f"✅ Cleared cache: {deleted} tiles deleted")

    def export_cache_archive(self, archive_path: Path) -> Dict:
        """Export cache to archive file for sharing/backup

        Creates a portable archive containing:
        - All cached tile images
        - Cache metadata database
        - Manifest with georef bounds for verification

        Args:
            archive_path: Path to save archive (.tar.gz)

        Returns:
            Dict with archive stats
        """
        import tarfile
        import shutil

        print(f"\n{'='*70}")
        print(f"📦 EXPORTING CACHE ARCHIVE")
        print(f"{'='*70}")

        # Get cache stats
        stats = self.get_cache_stats()
        print(f"Tiles to archive: {stats['count']}")
        print(f"Total size: {stats['size_mb']:.1f} MB")

        # Create archive
        with tarfile.open(archive_path, "w:gz") as tar:
            # Add all tile images
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT file_path FROM cache_entries")
            files = cursor.fetchall()

            for (file_path,) in files:
                path = Path(file_path)
                if path.exists():
                    arcname = f"tiles/{path.name}"
                    tar.add(path, arcname=arcname)

            conn.close()

            # Add metadata database
            tar.add(self.db_path, arcname="cache_metadata.db")

            # Create manifest
            manifest = {
                'export_date': datetime.now().isoformat(),
                'tile_count': stats['count'],
                'size_mb': stats['size_mb'],
                'zoom_distribution': stats['zoom_distribution'],
                'format_version': '1.0'
            }

            # Read georef config for verification
            try:
                conn = sqlite3.connect(Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"))
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM georef_config LIMIT 1")
                row = cursor.fetchone()
                conn.close()

                if row:
                    manifest['georef_bounds'] = {
                        'blender_x_min': row[2],
                        'blender_x_max': row[3],
                        'blender_y_min': row[4],
                        'blender_y_max': row[5],
                        'gps_lon_min': row[6],
                        'gps_lon_max': row[7],
                        'gps_lat_min': row[8],
                        'gps_lat_max': row[9]
                    }
            except:
                pass

            # Write manifest
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(manifest, f, indent=2)
                manifest_path = Path(f.name)

            tar.add(manifest_path, arcname="manifest.json")
            manifest_path.unlink()

        archive_size_mb = archive_path.stat().st_size / 1024 / 1024

        print(f"\n✅ Archive created:")
        print(f"   Path: {archive_path}")
        print(f"   Size: {archive_size_mb:.1f} MB")
        print(f"   Tiles: {stats['count']}")
        print(f"{'='*70}\n")

        return {
            'archive_path': str(archive_path),
            'archive_size_mb': archive_size_mb,
            'tile_count': stats['count']
        }

    def import_cache_archive(self, archive_path: Path, verify_georef: bool = True) -> Dict:
        """Import cache from archive file

        Args:
            archive_path: Path to archive (.tar.gz)
            verify_georef: Verify georef bounds match current database

        Returns:
            Dict with import stats
        """
        import tarfile
        import tempfile

        print(f"\n{'='*70}")
        print(f"📥 IMPORTING CACHE ARCHIVE")
        print(f"{'='*70}")
        print(f"Archive: {archive_path}")

        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        # Extract to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Extract archive
            print("Extracting archive...")
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(temp_path)

            # Read manifest
            manifest_path = temp_path / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)

                print(f"\nArchive Info:")
                print(f"  Export date: {manifest.get('export_date', 'unknown')}")
                print(f"  Tiles: {manifest.get('tile_count', 0)}")
                print(f"  Size: {manifest.get('size_mb', 0):.1f} MB")

                # Verify georef bounds if requested
                if verify_georef and 'georef_bounds' in manifest:
                    print(f"\n🔍 Verifying georef bounds...")
                    try:
                        conn = sqlite3.connect(Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"))
                        cursor = conn.cursor()
                        cursor.execute("SELECT * FROM georef_config LIMIT 1")
                        row = cursor.fetchone()
                        conn.close()

                        if row:
                            current_bounds = {
                                'gps_lon_min': row[6],
                                'gps_lon_max': row[7],
                                'gps_lat_min': row[8],
                                'gps_lat_max': row[9]
                            }

                            archive_bounds = manifest['georef_bounds']

                            # Check if bounds match (within 0.001 degrees ≈ 100m)
                            matches = all(
                                abs(current_bounds[key] - archive_bounds[key]) < 0.001
                                for key in current_bounds.keys()
                            )

                            if matches:
                                print(f"   ✅ Georef bounds match - tiles will align correctly")
                            else:
                                print(f"   ⚠️  WARNING: Georef bounds mismatch!")
                                print(f"      Current: Lon {current_bounds['gps_lon_min']:.6f}-{current_bounds['gps_lon_max']:.6f}, "
                                      f"Lat {current_bounds['gps_lat_min']:.6f}-{current_bounds['gps_lat_max']:.6f}")
                                print(f"      Archive: Lon {archive_bounds['gps_lon_min']:.6f}-{archive_bounds['gps_lon_max']:.6f}, "
                                      f"Lat {archive_bounds['gps_lat_min']:.6f}-{archive_bounds['gps_lat_max']:.6f}")
                                print(f"      Tiles may not align correctly with current river model!")
                    except Exception as e:
                        print(f"   ⚠️  Could not verify georef bounds: {e}")

            # Copy tiles
            tiles_dir = temp_path / "tiles"
            if tiles_dir.exists():
                print(f"\nCopying tiles to cache...")
                imported = 0
                for tile_file in tiles_dir.glob("*.jpg"):
                    dest = self.cache_dir / tile_file.name
                    if not dest.exists():  # Don't overwrite existing
                        import shutil
                        shutil.copy2(tile_file, dest)
                        imported += 1

                print(f"   Imported {imported} new tiles")

            # Import metadata database
            db_temp = temp_path / "cache_metadata.db"
            if db_temp.exists():
                print(f"Merging metadata...")

                # Merge into current database
                conn_src = sqlite3.connect(db_temp)
                conn_dst = sqlite3.connect(self.db_path)

                cursor_src = conn_src.cursor()
                cursor_src.execute("SELECT * FROM cache_entries")
                entries = cursor_src.fetchall()

                cursor_dst = conn_dst.cursor()

                merged = 0
                for entry in entries:
                    # Check if tile already exists
                    tile_id = entry[0]
                    cursor_dst.execute("SELECT tile_id FROM cache_entries WHERE tile_id = ?", (tile_id,))
                    if not cursor_dst.fetchone():
                        # Insert new entry (update file_path to current cache dir)
                        new_entry = list(entry)
                        new_entry[4] = str(self.cache_dir / Path(entry[4]).name)  # Update file_path
                        cursor_dst.execute("""
                            INSERT INTO cache_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, new_entry)
                        merged += 1

                conn_dst.commit()
                conn_src.close()
                conn_dst.close()

                print(f"   Merged {merged} metadata entries")

        print(f"\n✅ Cache import complete")
        print(f"{'='*70}\n")

        return {
            'imported_tiles': imported if 'imported' in locals() else 0,
            'merged_entries': merged if 'merged' in locals() else 0
        }


# =============================================================================
# GOOGLE MAPS API FETCHER
# =============================================================================

class GoogleMapsFetcher:
    """Fetch tiles from Google Maps Static API"""

    COST_PER_TILE = 0.002  # $0.002 per static map load

    @staticmethod
    def fetch_tile(lat: float, lon: float, zoom: int, api_key: str,
                   maptype: str = 'satellite', size: int = 640) -> bytes:
        """Fetch tile from Google Maps Static API

        Args:
            lat: Center latitude
            lon: Center longitude
            zoom: Zoom level (1-20)
            api_key: Google Maps API key
            maptype: Map type (satellite, terrain, hybrid)
            size: Tile size in pixels (max 640)

        Returns:
            Tile image data as bytes
        """
        params = {
            'center': f'{lat},{lon}',
            'zoom': zoom,
            'size': f'{size}x{size}',
            'scale': 2,  # High DPI
            'maptype': maptype,
            'key': api_key,
            'format': 'jpg'
        }

        url = "https://maps.googleapis.com/maps/api/staticmap?" + urllib.parse.urlencode(params)

        # Download tile
        response = urllib.request.urlopen(url)
        tile_data = response.read()

        return tile_data


# =============================================================================
# HIGH-LEVEL TILE LOADER
# =============================================================================

class TileLoader:
    """High-level interface for loading tiles with caching"""

    def __init__(self, cache_dir: Path, api_key: str):
        """Initialize tile loader

        Args:
            cache_dir: Directory for tile cache
            api_key: Google Maps API key
        """
        self.cache = TileCache(cache_dir)
        self.api_key = api_key

    def load_tile(self, lat: float, lon: float, zoom: int,
                  maptype: str = 'satellite') -> Tuple[str, bool]:
        """Load tile from cache or API

        Returns:
            Tuple of (file_path, cached)
        """
        # Check cache first
        cached_path = self.cache.get_cached_tile(lat, lon, zoom)

        if cached_path:
            print(f"✅ Cached tile: lat={lat:.6f}, lon={lon:.6f}, z={zoom}")
            self.cache.log_api_call(lat, lon, zoom, 0.0, cached=True, layer_type=maptype)
            return cached_path, True

        # Fetch from API
        print(f"📥 Fetching tile: lat={lat:.6f}, lon={lon:.6f}, z={zoom} (${GoogleMapsFetcher.COST_PER_TILE:.3f})")

        tile_data = GoogleMapsFetcher.fetch_tile(lat, lon, zoom, self.api_key, maptype)

        # Add to cache
        cache_path = self.cache.add_tile_to_cache(lat, lon, zoom, tile_data)

        # Log API usage
        self.cache.log_api_call(lat, lon, zoom, GoogleMapsFetcher.COST_PER_TILE,
                               cached=False, layer_type=maptype)

        return cache_path, False

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        return self.cache.get_cache_stats()

    def get_api_usage_stats(self) -> Dict:
        """Get API usage statistics"""
        return self.cache.get_api_usage_stats()

    def clear_cache(self):
        """Clear tile cache"""
        self.cache.clear_cache()
