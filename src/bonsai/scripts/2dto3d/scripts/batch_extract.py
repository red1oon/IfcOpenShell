#!/usr/bin/env python3
"""
Batch Extraction - Extract all pages with Vision API and track quota usage.

Extracts all PDF pages, tracks API calls, fills master template systematically.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent))
from vision_extract import extract_from_image, get_cache_path


class APIUsageTracker:
    """Track Vision API usage against quota."""

    def __init__(self, quota_limit: int = 1000):
        self.quota_limit = quota_limit
        self.tracker_path = Path(__file__).parent.parent / "OUTPUT" / "api_usage.json"
        self.usage = self._load_usage()

    def _load_usage(self) -> dict:
        """Load existing usage data."""
        if self.tracker_path.exists():
            with open(self.tracker_path, 'r') as f:
                return json.load(f)
        return {
            "total_calls": 0,
            "quota_limit": self.quota_limit,
            "calls": []
        }

    def _save_usage(self):
        """Save usage data."""
        self.tracker_path.parent.mkdir(exist_ok=True)
        with open(self.tracker_path, 'w') as f:
            json.dump(self.usage, f, indent=2)

    def record_call(self, page: str, cached: bool):
        """Record an API call."""
        self.usage["calls"].append({
            "timestamp": datetime.now().isoformat(),
            "page": page,
            "cached": cached,
            "api_call": not cached
        })
        if not cached:
            self.usage["total_calls"] += 1
        self._save_usage()

    def get_summary(self) -> str:
        """Get usage summary."""
        used = self.usage["total_calls"]
        limit = self.usage["quota_limit"]
        remaining = limit - used
        return f"API Usage: {used}/{limit} ({remaining} remaining)"


def batch_extract_all_pages(cache_dir: str, force: bool = False) -> dict:
    """
    Extract all pages from CACHE directory.

    Returns:
        Dict with extraction results and API usage stats.
    """
    cache_path = Path(cache_dir)
    tracker = APIUsageTracker(quota_limit=1000)

    # Find all page PNGs
    page_files = sorted(cache_path.glob("page*.png"))

    if not page_files:
        print(f"ERROR: No page*.png files found in {cache_path}")
        return None

    print("=" * 60)
    print("BATCH EXTRACTION - Vision API")
    print("=" * 60)
    print(f"Found {len(page_files)} pages to process")
    print(f"Current {tracker.get_summary()}")
    print("-" * 60)

    results = {}
    new_calls = 0
    cached_calls = 0

    for page_file in page_files:
        page_name = page_file.stem
        cache_file = get_cache_path(str(page_file), cache_dir)

        # Check if cached
        is_cached = cache_file.exists() and not force

        if is_cached:
            print(f"  {page_name}: CACHED (no API call)")
            cached_calls += 1
        else:
            print(f"  {page_name}: EXTRACTING (API call)...")
            new_calls += 1

        # Extract (will use cache if exists)
        result = extract_from_image(str(page_file), cache_dir, force)
        results[page_name] = {
            "file": str(page_file),
            "cache": str(cache_file),
            "text_count": result["metadata"]["extraction_count"],
            "cached": is_cached
        }

        # Record usage
        tracker.record_call(page_name, is_cached)

    print("-" * 60)
    print(f"COMPLETED: {len(results)} pages processed")
    print(f"  New API calls: {new_calls}")
    print(f"  From cache: {cached_calls}")
    print(f"  {tracker.get_summary()}")
    print("=" * 60)

    return {
        "pages": results,
        "stats": {
            "total_pages": len(results),
            "new_api_calls": new_calls,
            "from_cache": cached_calls,
            "api_usage": tracker.usage
        }
    }


def main():
    """CLI entry point."""
    base_dir = Path(__file__).parent.parent
    cache_dir = base_dir / "CACHE"

    force = "--force" in sys.argv

    if force:
        print("WARNING: Force mode - will re-extract all pages (uses API quota)")
        confirm = input("Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return

    # Set credentials
    creds_path = "C:/Dev/bonsai-extensions/WORK_DIR/vision-api.json"
    if os.path.exists(creds_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

    result = batch_extract_all_pages(str(cache_dir), force)

    if result:
        # Save batch result summary
        output_path = base_dir / "OUTPUT" / "batch_extraction_result.json"
        output_path.parent.mkdir(exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\nSummary saved to: {output_path}")


if __name__ == "__main__":
    main()
