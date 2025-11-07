"""
IFC Class Label Mapper

Database-backed dictionary for converting cryptic IFC class names to friendly
readable labels for reports, UI, and user-facing documentation.

Labels are stored in database (ifc_labels table) for easy customization
per-project or organization. Falls back to in-memory dictionary if database
not available.

Usage:
    from .ifc_label_mapper import get_friendly_label

    # Basic usage (queries database)
    label = get_friendly_label('IfcDuct', db_path='clash_status.db')
    # Returns: "HVAC Duct"

    # With element name
    label = get_friendly_label('IfcPipeFitting', db_path='clash_status.db', element_name='Main Supply')
    # Returns: "Pipe Fitting (Main Supply)"

    # Fallback without database
    label = get_friendly_label('IfcUnknownClass')
    # Returns: "IfcUnknownClass"

Database Initialization:
    sqlite3 database.db < Scripts/initialize_ifc_label_dictionary.sql
"""

import sqlite3
from pathlib import Path
from typing import Optional, Dict
import functools

# In-memory fallback dictionary (used when database not available)
# This serves as the default mapping for standard IFC classes
_FALLBACK_IFC_LABELS = {
    # MEP - HVAC
    'IfcDuct': 'HVAC Duct',
    'IfcDuctSegment': 'HVAC Duct Segment',
    'IfcDuctFitting': 'HVAC Duct Fitting',
    'IfcAirTerminal': 'Air Terminal',
    'IfcFlowTerminal': 'HVAC Terminal',
    'IfcAirToAirHeatRecovery': 'Heat Recovery Unit',
    'IfcBoiler': 'Boiler',
    'IfcChiller': 'Chiller',
    'IfcCoil': 'HVAC Coil',
    'IfcCompressor': 'Compressor',
    'IfcCondenser': 'Condenser',
    'IfcCooledBeam': 'Cooled Beam',
    'IfcCoolingTower': 'Cooling Tower',
    'IfcDamper': 'Damper',
    'IfcFan': 'Fan',
    'IfcFilter': 'Air Filter',
    'IfcHeatExchanger': 'Heat Exchanger',
    'IfcHumidifier': 'Humidifier',
    'IfcUnitaryEquipment': 'Unitary HVAC Equipment',

    # MEP - Plumbing
    'IfcPipe': 'Pipe',
    'IfcPipeSegment': 'Pipe Segment',
    'IfcPipeFitting': 'Pipe Fitting',
    'IfcValve': 'Valve',
    'IfcPump': 'Pump',
    'IfcTank': 'Tank',
    'IfcSanitaryTerminal': 'Sanitary Fixture',
    'IfcWasteTerminal': 'Waste Terminal',
    'IfcFireSuppressionTerminal': 'Fire Suppression Terminal',
    'IfcSpaceHeater': 'Space Heater',
    'IfcTubeBundle': 'Tube Bundle',

    # MEP - Electrical
    'IfcCableCarrierSegment': 'Cable Tray',
    'IfcCableCarrierFitting': 'Cable Tray Fitting',
    'IfcCableSegment': 'Cable Segment',
    'IfcElectricAppliance': 'Electrical Equipment',
    'IfcElectricDistributionBoard': 'Distribution Board',
    'IfcElectricFlowStorageDevice': 'Battery/UPS',
    'IfcElectricGenerator': 'Generator',
    'IfcElectricMotor': 'Electric Motor',
    'IfcElectricTimeControl': 'Timer Control',
    'IfcJunctionBox': 'Junction Box',
    'IfcLamp': 'Lamp',
    'IfcLightFixture': 'Light Fixture',
    'IfcMotorConnection': 'Motor Connection',
    'IfcOutlet': 'Electrical Outlet',
    'IfcProtectiveDevice': 'Protective Device',
    'IfcSwitchingDevice': 'Switch',
    'IfcTransformer': 'Transformer',

    # Structural
    'IfcBeam': 'Structural Beam',
    'IfcColumn': 'Structural Column',
    'IfcFooting': 'Foundation',
    'IfcPile': 'Pile',
    'IfcReinforcing': 'Reinforcement',
    'IfcSlab': 'Slab',
    'IfcStair': 'Stair',
    'IfcRailing': 'Railing',
    'IfcRamp': 'Ramp',
    'IfcRoof': 'Roof',

    # Architectural
    'IfcWall': 'Wall',
    'IfcDoor': 'Door',
    'IfcWindow': 'Window',
    'IfcCurtainWall': 'Curtain Wall',
    'IfcOpeningElement': 'Opening',
    'IfcSpace': 'Space',
    'IfcCovering': 'Ceiling/Floor Covering',
    'IfcFurnishingElement': 'Furniture',
    'IfcFurniture': 'Furniture',

    # Building Elements
    'IfcBuildingElementProxy': 'Generic Building Element',
    'IfcMember': 'Structural Member',
    'IfcPlate': 'Plate',
    'IfcBearing': 'Bearing',
    'IfcChimney': 'Chimney',
}


@functools.lru_cache(maxsize=256)
def _query_ifc_label_from_db(ifc_class: str, db_path: Optional[str]) -> Optional[str]:
    """
    Query IFC label from database (with caching for performance).

    Args:
        ifc_class: IFC class name
        db_path: Path to database file (None to skip database lookup)

    Returns:
        Friendly label from database, or None if not found
    """
    if not db_path or not Path(db_path).exists():
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if ifc_labels table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='ifc_labels'
        """)

        if not cursor.fetchone():
            conn.close()
            return None

        # Query friendly label
        cursor.execute("""
            SELECT friendly_label FROM ifc_labels
            WHERE ifc_class = ?
        """, (ifc_class,))

        row = cursor.fetchone()
        conn.close()

        return row[0] if row else None

    except Exception:
        return None


def get_friendly_label(
    ifc_class: str,
    element_name: Optional[str] = None,
    max_name_length: int = 30,
    db_path: Optional[str] = None
) -> str:
    """
    Convert IFC class name to human-readable label.

    Queries database first (if available), then falls back to in-memory dictionary.

    Args:
        ifc_class: IFC class name (e.g., 'IfcDuct', 'IfcPipeFitting')
        element_name: Optional element name from model (e.g., 'Main Supply Line')
        max_name_length: Maximum length for element name (default: 30 chars)
        db_path: Optional path to database with ifc_labels table

    Returns:
        Friendly readable label for reports and UI

    Examples:
        >>> get_friendly_label('IfcDuct')
        'HVAC Duct'

        >>> get_friendly_label('IfcPipeFitting', element_name='Main Supply')
        'Pipe Fitting (Main Supply)'

        >>> get_friendly_label('IfcDuct', db_path='/path/to/database.db')
        'HVAC Duct'  # from database if available
    """
    # Try database first
    friendly_name = None
    if db_path:
        friendly_name = _query_ifc_label_from_db(ifc_class, db_path)

    # Fallback to in-memory dictionary
    if not friendly_name:
        friendly_name = _FALLBACK_IFC_LABELS.get(ifc_class, ifc_class)

    # Append element name if provided and meaningful
    if element_name and len(element_name) > 0:
        # Truncate long names
        if len(element_name) > max_name_length:
            element_name = element_name[:max_name_length] + '...'

        # Check if name is meaningful (not just GUID or cryptic ID)
        # GUIDs typically have pattern like: 3gRgHpivr8ZQ1RQVC9ExXF
        if _is_meaningful_name(element_name):
            return f"{friendly_name} ({element_name})"

    return friendly_name


def _is_meaningful_name(name: str) -> bool:
    """
    Check if element name is meaningful or just a cryptic identifier.

    Args:
        name: Element name to check

    Returns:
        True if name appears to be meaningful, False if cryptic

    Examples:
        >>> _is_meaningful_name('Main Supply Line')
        True

        >>> _is_meaningful_name('3gRgHpivr8ZQ1RQVC9ExXF')
        False

        >>> _is_meaningful_name('B-32')
        True
    """
    # Skip very short names (likely IDs)
    if len(name) < 3:
        return False

    # Check if name is mostly alphanumeric gibberish (GUID-like)
    # Allow spaces, hyphens, underscores (common in meaningful names)
    allowed_special = {' ', '-', '_', '.', '/', '\\'}
    alphanumeric_count = sum(c.isalnum() for c in name)
    special_count = sum(c in allowed_special for c in name)
    total_chars = len(name)

    # If name is >80% alphanumeric with no spaces, likely a GUID
    if alphanumeric_count / total_chars > 0.8 and ' ' not in name and len(name) > 20:
        return False

    # If name has spaces or common delimiters, likely meaningful
    if any(c in name for c in [' ', '-', '/', '\\']):
        return True

    # If name is all uppercase/lowercase with no variety, might be generated
    if name.isupper() or name.islower():
        if alphanumeric_count == total_chars:
            return False

    # Default: assume meaningful
    return True


def get_element_display_name(
    guid: str,
    ifc_class: str,
    element_name: Optional[str] = None,
    storey: Optional[str] = None,
    db_path: Optional[str] = None
) -> str:
    """
    Get human-readable element display name for reports.

    Combines friendly IFC label + location context when element_name is cryptic.
    Designed for clash reports to replace cryptic GUIDs with meaningful names.

    Args:
        guid: Element GUID (for fallback display)
        ifc_class: IFC class (e.g., 'IfcDuct', 'IfcPipeFitting')
        element_name: Element name from model (may be NULL or cryptic)
        storey: Storey/floor location (e.g., '04 THIRD FLOOR LEVEL')
        db_path: Database path (for ifc_labels table lookup)

    Returns:
        Human-readable element identifier for reports

    Examples:
        >>> get_element_display_name('2eD...', 'IfcOpeningElement', None, '04 THIRD FLOOR LEVEL')
        'Opening (3rd Floor)'

        >>> get_element_display_name('289...', 'IfcPipeFitting', 'Main Supply', '04 THIRD FLOOR LEVEL')
        'Main Supply (3rd Floor)'

        >>> get_element_display_name('3gR...', 'IfcDuct', 'M_HVAC:Duct:12345', 'GROUND FLOOR LEVEL')
        'HVAC Duct (Ground Floor)'

        >>> get_element_display_name('1VM...', 'IfcBeam', None, None)
        'Structural Beam (#1VM...)'
    """
    # Get friendly IFC type
    friendly_type = get_friendly_label(ifc_class, db_path=db_path)

    # Clean up storey name for display
    location = ""
    if storey:
        import re
        # Transform "04 THIRD FLOOR LEVEL" -> "3rd Floor"
        # Transform "GROUND FLOOR LEVEL" -> "Ground Floor"
        location = (storey
                   .replace(" LEVEL", "")
                   .replace("FLOOR", "Floor")
                   .replace("THIRD", "3rd")
                   .replace("FOURTH", "4th")
                   .replace("FIFTH", "5th")
                   .replace("SECOND", "2nd")
                   .replace("FIRST", "1st")
                   .replace("GROUND", "Ground")
                   .strip())
        # Remove leading numbers if present (e.g., "04 3rd Floor" -> "3rd Floor")
        location = re.sub(r'^\d+\s+', '', location)

    # Check if element_name is meaningful
    if element_name and _is_meaningful_name(element_name):
        # Use existing name but add location context
        if location:
            return f"{element_name} ({location})"
        return element_name

    # Generate from IFC type + location
    if location:
        return f"{friendly_type} ({location})"

    # Last resort: IFC type + GUID fragment for uniqueness
    return f"{friendly_type} (#{guid[:8]})"


def get_discipline_label(discipline_code: str) -> str:
    """
    Convert discipline code to friendly name.

    Args:
        discipline_code: Discipline abbreviation (e.g., 'STR', 'MEP', 'ARC')

    Returns:
        Full discipline name

    Examples:
        >>> get_discipline_label('STR')
        'Structural'

        >>> get_discipline_label('ACMV')
        'HVAC (Air Conditioning & Mechanical Ventilation)'
    """
    DISCIPLINE_LABELS = {
        'STR': 'Structural',
        'ARC': 'Architecture',
        'MEP': 'Mechanical, Electrical & Plumbing',
        'ACMV': 'HVAC (Air Conditioning & Mechanical Ventilation)',
        'PP': 'Plumbing',
        'ELEC': 'Electrical',
        'FIRE': 'Fire Protection',
        'STRUCT': 'Structural',
        'ARCH': 'Architecture',
        'SP': 'Sanitary/Plumbing',
    }

    return DISCIPLINE_LABELS.get(discipline_code, discipline_code)


# Export public API
__all__ = [
    'get_friendly_label',
    'get_element_display_name',
    'get_discipline_label',
]
