# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Your Engineering Firm
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Qualified Path: src/bonsai/bonsai/bim/module/federation/logging_utils.py

Federation Logging Utilities
-----------------------------
Console logging to timestamped files for easier debugging and troubleshooting.

Usage:
    from . import logging_utils

    # Start logging to file
    logging_utils.start_file_logging()

    # Use normal print statements - they'll go to both console and file
    print("This message goes to both console and file")

    # Stop logging when done
    logging_utils.stop_file_logging()

    # Or use context manager (recommended)
    with logging_utils.FileLogging():
        print("This is logged to file")
"""

import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO


# Global state for logging
_log_file: Optional[TextIO] = None
_original_stdout: Optional[TextIO] = None
_original_stderr: Optional[TextIO] = None
_tee_stdout: Optional['TeeStream'] = None
_tee_stderr: Optional['TeeStream'] = None


class TeeStream:
    """Stream that writes to both console and file simultaneously."""

    def __init__(self, file_stream: TextIO, console_stream: TextIO):
        self.file = file_stream
        self.console = console_stream

    def write(self, data: str):
        """Write to both file and console."""
        # Check if file is still open before writing
        if self.file and not self.file.closed:
            try:
                self.file.write(data)
                self.file.flush()  # Ensure immediate write
            except (ValueError, OSError):
                # File was closed, skip file writing
                pass
        self.console.write(data)
        self.console.flush()

    def flush(self):
        """Flush both streams."""
        if self.file and not self.file.closed:
            try:
                self.file.flush()
            except (ValueError, OSError):
                pass
        self.console.flush()

    def isatty(self):
        """Check if console is a terminal."""
        return self.console.isatty()


def get_log_filepath() -> Path:
    """
    Get timestamped log file path.

    Returns:
        Path to log file: ~/Documents/bonsai/consolelogs/console_YYYYMMDD_HHMMSS.log
    """
    home = Path.home()

    # Priority 1: ~/Documents/bonsai/consolelogs/
    bonsai_consolelogs = home / "Documents" / "bonsai" / "consolelogs"
    if bonsai_consolelogs.exists() and bonsai_consolelogs.is_dir():
        log_dir = bonsai_consolelogs
    elif (home / "Documents" / "bonsai").exists():
        # Create consolelogs folder if bonsai exists but consolelogs doesn't
        bonsai_consolelogs.mkdir(parents=True, exist_ok=True)
        log_dir = bonsai_consolelogs
    else:
        # Priority 2: ~/Documents/
        documents = home / "Documents"
        if documents.exists() and documents.is_dir():
            log_dir = documents
        else:
            # Priority 3: /tmp/ fallback
            log_dir = Path("/tmp")

    # Create timestamp: YYYYMMDD_HHMMSS
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Format: console_YYYYMMDD_HHMMSS.log
    log_filename = f"console_{timestamp}.log"

    return log_dir / log_filename


def start_file_logging() -> Path:
    """
    Start logging console output to timestamped file.

    All print statements will be written to both console and file.

    Returns:
        Path to created log file
    """
    global _log_file, _original_stdout, _original_stderr, _tee_stdout, _tee_stderr

    # Don't start if already logging
    if _log_file is not None:
        return Path(_log_file.name)

    # Create log file
    log_path = get_log_filepath()
    _log_file = open(log_path, 'w', encoding='utf-8')

    # Save original streams
    _original_stdout = sys.stdout
    _original_stderr = sys.stderr

    # Create tee streams
    _tee_stdout = TeeStream(_log_file, _original_stdout)
    _tee_stderr = TeeStream(_log_file, _original_stderr)

    # Redirect stdout and stderr
    sys.stdout = _tee_stdout
    sys.stderr = _tee_stderr

    # Write header
    print("=" * 70)
    print(f"FEDERATION LOG - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Log file: {log_path}")
    print("=" * 70)
    print()

    return log_path


def stop_file_logging():
    """
    Stop logging to file and restore original console streams.
    """
    global _log_file, _original_stdout, _original_stderr, _tee_stdout, _tee_stderr

    if _log_file is None:
        return  # Not logging

    # Write footer
    print()
    print("=" * 70)
    print(f"LOG END - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Restore original streams
    sys.stdout = _original_stdout
    sys.stderr = _original_stderr

    # Close log file
    _log_file.close()

    # Print confirmation to console
    print(f"✓ Log saved to: {_log_file.name}")

    # Reset state
    _log_file = None
    _original_stdout = None
    _original_stderr = None
    _tee_stdout = None
    _tee_stderr = None


class FileLogging:
    """
    Context manager for file logging.

    Example:
        with FileLogging():
            print("This is logged to file")
        # Automatically stops logging when done
    """

    def __init__(self):
        self.log_path = None

    def __enter__(self):
        self.log_path = start_file_logging()
        return self.log_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        stop_file_logging()
        return False  # Don't suppress exceptions


def log(message: str, level: str = "INFO"):
    """
    Convenience function to log a message with timestamp and level.

    Args:
        message: Message to log
        level: Log level (INFO, WARNING, ERROR, DEBUG)
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")
