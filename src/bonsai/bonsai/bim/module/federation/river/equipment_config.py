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
    'wave_breaker': {
        'name': 'Wave Breaker',
        'color': (0.055, 0.647, 0.914),  # Sky Blue #0ea5e9
        'icon': 'MOD_WAVE',
        'radius': 3.0
    },
    'erosion_control': {
        'name': 'Erosion Control',
        'color': (0.635, 0.384, 0.027),  # Amber/Brown #a16207
        'icon': 'MESH_GRID',
        'radius': 3.0
    },
    'floating_wetland': {
        'name': 'Floating Wetland',
        'color': (0.086, 0.639, 0.290),  # Dark Green #16a34a
        'icon': 'FORCE_TURBULENCE',
        'radius': 3.0
    },
    'biochar_barrier': {
        'name': 'Biochar Barrier',
        'color': (0.216, 0.255, 0.318),  # Dark Gray #374151
        'icon': 'MESH_PLANE',
        'radius': 3.0
    },
    'drone_base': {
        'name': 'Drone Base',
        'color': (0.486, 0.227, 0.929),  # Violet #7c3aed
        'icon': 'OUTLINER_OB_FORCE_FIELD',
        'radius': 3.0
    },
    'environmental_station': {
        'name': 'Environmental Station',
        'color': (0.031, 0.569, 0.698),  # Cyan #0891b2
        'icon': 'OUTLINER_DATA_LIGHTPROBE',
        'radius': 3.0
    },
    'pir_security': {
        'name': 'PIR Security',
        'color': (0.863, 0.149, 0.149),  # Red #dc2626
        'icon': 'OUTLINER_DATA_CAMERA',
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
    'sediment_accretion': '🏖️',  # Full name

    # Pollutant Sensor sensors
    'voc': '💨',
    'cod': '🧪',
    'bod': '🦠',
    'tss': '🌫️',
    'oil_grease': '🛢️',
    'cyanide': '☠️',
    'phenols': '⚗️',

    # Wave Breaker sensors
    'wave_height': '🌊',
    'wave_period': '⏱️',
    'wave_direction': '🧭',
    'structural_stress': '⚙️',
    'water_level': '📏',
    'current_velocity': '💨',
    'sediment_transport': '🏖️',
    'structural_integrity': '🏗️',

    # Erosion Control sensors
    'soil_movement': '⛰️',
    'bank_stability': '🏔️',
    'pore_pressure': '💧',
    'inclinometer': '📐',
    'groundwater': '💦',
    'crack_width': '📏',

    # Floating Wetland sensors
    'nutrient_uptake': '🌿',
    'plant_health': '🌱',
    'turbidity_reduction': '✨',
    'buoyancy': '🎈',
    'root_depth': '🌿',

    # Biochar Barrier sensors
    'filtration_rate': '💧',
    'biochar_saturation': '⚫',
    'heavy_metal_capture': '☢️',
    'organic_removal': '♻️',
    'pressure_differential': '📊',
    'gabion_integrity': '🧱',
    'submerged_fence_status': '🚧',

    # Drone Base sensors
    'drone_battery': '🔋',
    'flights_today': '✈️',
    'thermal_camera': '🔥',
    'rgb_camera': '📷',
    'gps_satellites': '🛰️',
    'data_storage': '💾',

    # Environmental Station sensors
    'air_temperature': '🌡️',
    'humidity': '💧',
    'co2_level': '🌫️',
    'air_quality_index': '🌫️',
    'barometric_pressure': '🌐',

    # PIR Security sensors
    'pir_motion': '👁️',
    'edge_ai_alert': '🚨',
    'intrusion_count': '⚠️',
    'thermal_anomaly': '🔥',
    'camera_status': '📹',
    'night_vision': '🌙',
    'alert_response_time': '⏱️',
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

    # Wave Breaker sensors
    'wave_height': (0.0, 0.6, 0.9),        # Deep Blue
    'wave_period': (0.3, 0.7, 0.95),       # Light Blue
    'wave_direction': (0.2, 0.5, 0.8),     # Ocean Blue
    'structural_stress': (1.0, 0.5, 0.0),  # Orange Alert
    'water_level': (0.4, 0.7, 0.95),       # Sky Blue
    'current_velocity': (0.0, 0.8, 0.9),   # Cyan
    'sediment_transport': (0.8, 0.7, 0.5), # Sand
    'structural_integrity': (0.2, 0.8, 0.2), # Green Status

    # Erosion Control sensors
    'soil_movement': (0.6, 0.4, 0.2),      # Soil Brown
    'bank_stability': (0.4, 0.7, 0.3),     # Earth Green
    'pore_pressure': (0.5, 0.6, 0.8),      # Steel Blue
    'inclinometer': (0.9, 0.6, 0.2),       # Orange
    'groundwater': (0.2, 0.5, 0.7),        # Water Blue
    'crack_width': (0.9, 0.3, 0.2),        # Warning Red

    # Floating Wetland sensors
    'nutrient_uptake': (0.3, 0.8, 0.4),    # Lime Green
    'plant_health': (0.2, 0.9, 0.3),       # Bright Green
    'turbidity_reduction': (0.6, 0.8, 0.95), # Clean Blue
    'buoyancy': (0.9, 0.7, 0.2),           # Buoy Yellow
    'root_depth': (0.5, 0.4, 0.2),         # Root Brown

    # Mangrove Islet sensors
    'tide_level': (0.2, 0.6, 0.9),         # Tidal Blue
    'salinity': (0.3, 0.7, 0.8),           # Saline Cyan
    'water_temp': (1.0, 0.5, 0.2),         # Warm Orange
    'co2_atmospheric': (0.5, 0.5, 0.5),    # CO2 Grey
    'sediment_accretion': (0.7, 0.6, 0.4), # Sediment Tan
    'soil_moisture': (0.6, 0.4, 0.2),      # Soil Brown (alias)

    # Biochar Barrier sensors
    'filtration_rate': (0.3, 0.6, 0.9),    # Flow Blue
    'biochar_saturation': (0.2, 0.2, 0.2), # Charcoal
    'heavy_metal_capture': (0.8, 0.2, 0.2), # Alert Red
    'organic_removal': (0.4, 0.8, 0.4),    # Success Green
    'pressure_differential': (0.7, 0.5, 0.3), # Pressure Tan
    'gabion_integrity': (0.5, 0.5, 0.5),   # Stone Grey
    'submerged_fence_status': (0.3, 0.5, 0.7), # Underwater Blue

    # Drone Base sensors
    'drone_battery': (0.2, 0.9, 0.2),      # Charge Green
    'flights_today': (0.4, 0.6, 0.9),      # Sky Blue
    'thermal_camera': (1.0, 0.3, 0.2),     # Heat Red
    'rgb_camera': (0.6, 0.4, 0.9),         # Camera Purple
    'gps_satellites': (0.9, 0.8, 0.2),     # Satellite Gold
    'data_storage': (0.3, 0.7, 0.9),       # Data Blue
    'visibility': (0.8, 0.9, 0.95),        # Clear White

    # Environmental Station sensors
    'air_temperature': (1.0, 0.5, 0.2),    # Warm Orange
    'humidity': (0.4, 0.7, 0.9),           # Humid Blue
    'co2_level': (0.6, 0.6, 0.6),          # CO2 Grey
    'air_quality_index': (0.7, 0.8, 0.3),  # AQI Yellow-Green
    'barometric_pressure': (0.7, 0.7, 0.8), # Pressure Grey
    'wind_direction': (0.5, 0.8, 0.95),    # Wind Cyan
    'wind_speed': (0.3, 0.7, 0.9),         # Breeze Blue

    # PIR Security sensors
    'pir_motion': (1.0, 0.8, 0.2),         # Motion Yellow
    'edge_ai_alert': (1.0, 0.2, 0.2),      # AI Alert Red
    'intrusion_count': (0.9, 0.4, 0.1),    # Warning Orange
    'thermal_anomaly': (1.0, 0.1, 0.4),    # Thermal Magenta
    'fence_integrity': (0.4, 0.8, 0.4),    # Fence Green
    'camera_status': (0.6, 0.5, 0.9),      # Camera Purple
    'night_vision': (0.3, 0.2, 0.5),       # Night Purple
    'alert_response_time': (0.9, 0.6, 0.1), # Response Amber
}

# =============================================================================
# GLOBAL STATE
# =============================================================================

# Global storage for placed equipment
PLACED_EQUIPMENT = {key: [] for key in EQUIPMENT_TYPES.keys()}
