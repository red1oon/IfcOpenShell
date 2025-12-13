# Bonsai - OpenBIM Blender Add-on
# River Equipment Placement - Configuration Module

"""
Equipment Configuration
========================
Equipment types, sensor icons/colors, and global state.
Centralized configuration for river monitoring equipment.
"""

# =============================================================================
# EQUIPMENT TYPES
# =============================================================================

EQUIPMENT_TYPES = {
    'boom_trap': {
        'name': 'Boom Trap Station',
        'color': (1.0, 0.42, 0.21),  # Orange #FF6B35
        'icon': 'MESH_CIRCLE',
        'radius': 3.0
    },
    'water_quality': {
        'name': 'Water Quality Station',
        'color': (0.31, 0.80, 0.77),  # Turquoise #4ECDC4
        'icon': 'MATFLUID',
        'radius': 3.0
    },
    'biodiversity': {
        'name': 'Biodiversity Monitor',
        'color': (0.0, 1.0, 0.0),  # Green
        'icon': 'ORPHAN_DATA',
        'radius': 3.0
    },
    'wildlife_camera': {
        'name': 'Wildlife Camera',
        'color': (0.0, 1.0, 0.0),  # Green (alias for biodiversity)
        'icon': 'CAMERA_DATA',
        'radius': 3.0
    },
    'biochar': {
        'name': 'Biochar Facility',
        'color': (0.60, 0.93, 0.85),  # Mint #99EDD9
        'icon': 'EXPERIMENTAL',
        'radius': 3.0
    },
    'mrf': {
        'name': 'MRF Site',
        'color': (1.0, 0.75, 0.80),  # Pink #FFBFCC
        'icon': 'PREFERENCES',
        'radius': 3.0
    },
    'pollutant_sensor': {
        'name': 'Pollutant Sensor',
        'color': (0.67, 0.59, 0.85),  # Purple #AA96DA
        'icon': 'EXPERIMENTAL',
        'radius': 3.0
    },
    'flood_monitor': {
        'name': 'Flood Monitor',
        'color': (0.36, 0.61, 0.84),  # Blue #5B9BD5
        'icon': 'MOD_FLUIDSIM',
        'radius': 3.0
    },
    'mangrove_islet': {
        'name': 'Mangrove Islet',
        'color': (0.13, 0.77, 0.37),  # Green #22c55e
        'icon': 'WORLD',
        'radius': 3.0
    },
}

# =============================================================================
# SENSOR TYPE ICON & COLOR MAPPINGS (Centralized)
# =============================================================================

# Sensor emoji icons - used in dashboard GPU overlay and popup displays
SENSOR_TYPE_ICONS = {
    # Boom Trap sensors
    'loadcell': '⚖️',
    'integrity': '🔧',
    'waterlevel': '🌊',
    'flowvelocity': '💨',
    'camera': '📹',
    'vibration': '📳',
    'gps_drift': '🛰️',
    'powerusage': '🔋',

    # Water Quality sensors
    'turbidity': '☁️',
    'heavymetals': '☢️',
    'ph': '🧪',
    'ph_sensor': '🧪',  # Alias for database naming
    'dissolvedoxygen': '💧',
    'dissolved_oxygen': '💧',  # Alias for database naming
    'temperature': '🌡️',
    'conductivity': '⚡',
    'nitrate': '🧬',
    'phosphate': '💎',
    'depth_gauge': '📏',  # Alias for database naming
    'flow_meter': '🌊',  # Alias for database naming
    'water_quality': '💧',  # Alias for database naming

    # Biodiversity sensors
    'aicamera': '📷',
    'pirmotion': '👁️',
    'thermalcamera': '🔥',
    'audiorecorder': '🎤',
    'ultrasonic': '🦇',
    'ndvi': '🌿',
    'soilmoisture': '🌱',
    'canopy_height': '🌳',

    # Biochar Facility sensors
    'feedstock_mass': '🪵',
    'biochar_yield': '⚫',
    'pyrolysis_temp': '🔥',
    'carbon_content': '💨',
    'co2_emissions': '🌫️',
    'particulate': '💨',
    'reactor_pressure': '🔩',
    'energy_consumption': '⚡',

    # MRF Site sensors
    'conveyor_load': '📦',
    'pet_stream': '♻️',
    'hdpe_stream': '🥤',
    'organic_stream': '🍃',
    'contamination': '⚠️',
    'ai_sorter_accuracy': '🤖',
    'throughput': '📊',
    'power_usage': '🔌',

    # Flood Monitor sensors
    'flowrate': '🌊',
    'rainfall': '🌧️',
    'barometric': '🌐',
    'velocity_spike': '⚡',
    'debris_radar': '📡',
    'bridge_clearance': '🌉',
    'siren_status': '🚨',

    # Mangrove Islet sensors
    'tide_level': '🌊',
    'salinity': '🧂',
    'water_temp': '🌡️',
    'co2_atmospheric': '🌫️',
    'dissolved_oxygen': '💧',
    'soil_moisture': '🌱',
    'turbidity': '☁️',
    'sediment_accret': '🏖️',

    # Pollutant Sensor sensors
    'voc': '💨',
    'cod': '🧪',
    'bod': '🦠',
    'tss': '🌫️',
    'oil_grease': '🛢️',
    'cyanide': '☠️',
    'phenols': '⚗️',
}

# Sensor color mappings - RGB tuples for dashboard visualization
SENSOR_TYPE_COLORS = {
    # Boom Trap sensors
    'loadcell': (0.0, 0.5, 1.0),           # Blue
    'integrity': (1.0, 0.6, 0.0),          # Orange
    'waterlevel': (0.53, 0.81, 0.92),      # Light Blue
    'flowvelocity': (0.0, 0.8, 0.8),       # Teal
    'camera': (0.6, 0.4, 0.8),             # Purple
    'vibration': (1.0, 0.75, 0.0),         # Amber
    'gps_drift': (0.68, 0.85, 0.68),       # Light Green
    'powerusage': (1.0, 1.0, 0.0),         # Yellow

    # Water Quality sensors
    'turbidity': (0.6, 0.4, 0.2),          # Brown
    'heavymetals': (1.0, 0.0, 0.0),        # Red
    'ph': (0.75, 1.0, 0.0),                # Lime
    'ph_sensor': (0.75, 1.0, 0.0),         # Alias for database naming
    'dissolvedoxygen': (0.0, 1.0, 1.0),    # Cyan
    'dissolved_oxygen': (0.0, 1.0, 1.0),   # Alias for database naming
    'temperature': (1.0, 0.27, 0.0),       # Orange-Red
    'conductivity': (0.93, 0.51, 0.93),    # Violet
    'nitrate': (0.0, 0.8, 0.0),            # Green
    'phosphate': (0.8, 1.0, 0.0),          # Yellow-Green
    'depth_gauge': (0.53, 0.81, 0.92),     # Light Blue
    'flow_meter': (0.0, 0.8, 0.8),         # Teal
    'water_quality': (0.0, 1.0, 1.0),      # Cyan

    # Biodiversity sensors
    'aicamera': (0.90, 0.70, 1.0),         # Lavender
    'pirmotion': (1.0, 1.0, 0.4),          # Bright Yellow
    'thermalcamera': (1.0, 0.1, 0.1),      # Bright Red
    'audiorecorder': (1.0, 0.0, 1.0),      # Magenta
    'ultrasonic': (0.53, 0.81, 0.98),      # Sky Blue
    'ndvi': (0.13, 0.55, 0.13),            # Forest Green
    'soilmoisture': (0.6, 0.4, 0.2),       # Soil Brown
    'canopy_height': (0.5, 1.0, 0.0),      # Bright Green

    # Biochar Facility sensors
    'feedstock_mass': (0.82, 0.71, 0.55),  # Tan
    'biochar_yield': (0.33, 0.33, 0.33),   # Dark Grey
    'pyrolysis_temp': (1.0, 0.15, 0.0),    # Fire Red
    'carbon_content': (0.18, 0.18, 0.18),  # Charcoal
    'co2_emissions': (0.5, 0.5, 0.5),      # Grey
    'particulate': (0.75, 0.75, 0.75),     # Light Grey
    'reactor_pressure': (1.0, 0.84, 0.0),  # Gold
    'energy_consumption': (1.0, 1.0, 0.2), # Bright Yellow

    # MRF Site sensors
    'conveyor_load': (0.42, 0.56, 0.64),   # Blue-Grey
    'pet_stream': (0.68, 0.85, 0.90),      # Light Blue
    'hdpe_stream': (0.96, 0.96, 0.96),     # White
    'organic_stream': (0.5, 0.5, 0.0),     # Olive
    'contamination': (1.0, 0.6, 0.0),      # Orange
    'ai_sorter_accuracy': (0.0, 1.0, 1.0), # Bright Cyan
    'throughput': (0.8, 0.8, 1.0),         # Periwinkle
    'power_usage': (1.0, 1.0, 0.2),        # Bright Yellow

    # Flood Monitor sensors
    'flowrate': (0.0, 0.4, 0.8),           # Ocean Blue
    'rainfall': (0.4, 0.6, 0.8),           # Rain Blue
    'barometric': (0.7, 0.75, 0.78),       # Light Blue-Grey
    'velocity_spike': (1.0, 0.2, 0.2),     # Alert Red
    'debris_radar': (1.0, 0.75, 0.0),      # Amber
    'bridge_clearance': (0.6, 0.98, 0.6),  # Mint
    'siren_status': (1.0, 0.0, 0.0),       # Alarm Red

    # Pollutant Sensor sensors
    'voc': (1.0, 0.75, 0.80),              # Pink
    'cod': (0.6, 0.4, 0.2),                # Brown
    'bod': (0.4, 0.3, 0.2),                # Mud
    'tss': (0.96, 0.96, 0.86),             # Beige
    'oil_grease': (0.1, 0.1, 0.1),         # Oil Black
    'cyanide': (1.0, 1.0, 0.5),            # Toxic Yellow
    'phenols': (1.0, 0.4, 0.6),            # Rose
}

# =============================================================================
# GLOBAL STATE
# =============================================================================

# Global storage for placed equipment
PLACED_EQUIPMENT = {key: [] for key in EQUIPMENT_TYPES.keys()}
