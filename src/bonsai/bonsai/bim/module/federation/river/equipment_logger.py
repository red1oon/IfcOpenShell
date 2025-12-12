# Bonsai - OpenBIM Blender Add-on
# River Equipment Placement - Logger Module

"""
Equipment Placement Logger
===========================
Logging utility for river equipment placement operations.
Writes to both console and file for debugging.
"""

from pathlib import Path
from datetime import datetime


class RiverEquipmentLogger:
    """Logger that writes to both console and file for debugging"""

    def __init__(self):
        self.log_dir = Path.home() / "Documents" / "bonsai" / "consolelogs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "river_equipment_placement.txt"

        # Initialize log file
        header = f"""
{'='*70}
RIVER EQUIPMENT PLACEMENT - PHASE 1 POC
{'='*70}
Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Log File: {self.log_file}
{'='*70}
"""
        with open(self.log_file, 'w') as f:
            f.write(header + '\n')
        print(header)

    def log(self, message, error=False):
        """Log to both console and file"""
        prefix = "❌" if error else "→"
        formatted = f"{prefix} {message}"

        print(formatted)
        try:
            with open(self.log_file, 'a') as f:
                f.write(formatted + '\n')
        except:
            pass

        return formatted

    def section(self, title):
        """Log section header"""
        line = f"\n{'-'*70}"
        header = f"{title}"
        formatted = f"{line}\n{header}\n{line}"

        print(formatted)
        try:
            with open(self.log_file, 'a') as f:
                f.write(formatted + '\n')
        except:
            pass


# Global logger instance
LOGGER = RiverEquipmentLogger()
LOGGER.section("LOGGER MODULE INITIALIZED")
