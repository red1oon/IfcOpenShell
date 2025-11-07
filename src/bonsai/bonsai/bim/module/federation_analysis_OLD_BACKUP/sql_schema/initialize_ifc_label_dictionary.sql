-- IFC Label Dictionary Database Schema
--
-- Standard mapping of cryptic IFC class names to human-readable labels
-- for reports, UI, and user-facing documentation.
--
-- This table can be customized per-project or organization.
--
-- Usage:
--   sqlite3 database.db < Scripts/initialize_ifc_label_dictionary.sql

-- Create IFC labels table
CREATE TABLE IF NOT EXISTS ifc_labels (
    ifc_class TEXT PRIMARY KEY,
    friendly_label TEXT NOT NULL,
    category TEXT,  -- 'HVAC', 'Plumbing', 'Electrical', 'Structural', 'Architecture'
    description TEXT,
    is_custom BOOLEAN DEFAULT 0,  -- User-defined vs standard
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ifc_labels_category ON ifc_labels(category);

-- Discipline labels
CREATE TABLE IF NOT EXISTS discipline_labels (
    discipline_code TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    description TEXT,
    is_custom BOOLEAN DEFAULT 0,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ========================================
-- Standard IFC Class Labels (MEP - HVAC)
-- ========================================
INSERT OR IGNORE INTO ifc_labels (ifc_class, friendly_label, category, description) VALUES
('IfcDuct', 'HVAC Duct', 'HVAC', 'Air distribution ductwork'),
('IfcDuctSegment', 'HVAC Duct Segment', 'HVAC', 'Straight duct segment'),
('IfcDuctFitting', 'HVAC Duct Fitting', 'HVAC', 'Duct elbow, tee, or reducer'),
('IfcAirTerminal', 'Air Terminal', 'HVAC', 'Diffuser, grille, or register'),
('IfcFlowTerminal', 'HVAC Terminal', 'HVAC', 'Generic HVAC terminal device'),
('IfcAirToAirHeatRecovery', 'Heat Recovery Unit', 'HVAC', 'Energy recovery ventilator'),
('IfcBoiler', 'Boiler', 'HVAC', 'Hot water or steam boiler'),
('IfcChiller', 'Chiller', 'HVAC', 'Chilled water plant equipment'),
('IfcCoil', 'HVAC Coil', 'HVAC', 'Heating or cooling coil'),
('IfcCompressor', 'Compressor', 'HVAC', 'Refrigeration compressor'),
('IfcCondenser', 'Condenser', 'HVAC', 'Refrigeration condenser'),
('IfcCooledBeam', 'Cooled Beam', 'HVAC', 'Passive or active chilled beam'),
('IfcCoolingTower', 'Cooling Tower', 'HVAC', 'Heat rejection equipment'),
('IfcDamper', 'Damper', 'HVAC', 'Air flow control device'),
('IfcFan', 'Fan', 'HVAC', 'Air moving equipment'),
('IfcFilter', 'Air Filter', 'HVAC', 'Air filtration device'),
('IfcHeatExchanger', 'Heat Exchanger', 'HVAC', 'Thermal energy transfer device'),
('IfcHumidifier', 'Humidifier', 'HVAC', 'Air moisture control'),
('IfcUnitaryEquipment', 'Unitary HVAC Equipment', 'HVAC', 'Packaged HVAC unit');

-- ========================================
-- Standard IFC Class Labels (MEP - Plumbing)
-- ========================================
INSERT OR IGNORE INTO ifc_labels (ifc_class, friendly_label, category, description) VALUES
('IfcPipe', 'Pipe', 'Plumbing', 'Water, gas, or drain pipe'),
('IfcPipeSegment', 'Pipe Segment', 'Plumbing', 'Straight pipe run'),
('IfcPipeFitting', 'Pipe Fitting', 'Plumbing', 'Pipe elbow, tee, or coupling'),
('IfcValve', 'Valve', 'Plumbing', 'Flow control valve'),
('IfcPump', 'Pump', 'Plumbing', 'Water circulation pump'),
('IfcTank', 'Tank', 'Plumbing', 'Water storage tank'),
('IfcSanitaryTerminal', 'Sanitary Fixture', 'Plumbing', 'Toilet, sink, or urinal'),
('IfcWasteTerminal', 'Waste Terminal', 'Plumbing', 'Drain or waste outlet'),
('IfcFireSuppressionTerminal', 'Fire Suppression Terminal', 'Fire Protection', 'Sprinkler head'),
('IfcSpaceHeater', 'Space Heater', 'Plumbing', 'Radiator or convector'),
('IfcTubeBundle', 'Tube Bundle', 'Plumbing', 'Heat exchanger component');

-- ========================================
-- Standard IFC Class Labels (MEP - Electrical)
-- ========================================
INSERT OR IGNORE INTO ifc_labels (ifc_class, friendly_label, category, description) VALUES
('IfcCableCarrierSegment', 'Cable Tray', 'Electrical', 'Cable support system'),
('IfcCableCarrierFitting', 'Cable Tray Fitting', 'Electrical', 'Cable tray bend or junction'),
('IfcCableSegment', 'Cable', 'Electrical', 'Electrical cable or wire'),
('IfcElectricAppliance', 'Electrical Equipment', 'Electrical', 'Generic electrical device'),
('IfcElectricDistributionBoard', 'Distribution Board', 'Electrical', 'Electrical panel'),
('IfcElectricFlowStorageDevice', 'Battery/UPS', 'Electrical', 'Energy storage device'),
('IfcElectricGenerator', 'Generator', 'Electrical', 'Power generation equipment'),
('IfcElectricMotor', 'Electric Motor', 'Electrical', 'Motorized equipment'),
('IfcElectricTimeControl', 'Timer Control', 'Electrical', 'Time-based control device'),
('IfcJunctionBox', 'Junction Box', 'Electrical', 'Wire connection box'),
('IfcLamp', 'Lamp', 'Electrical', 'Light bulb or tube'),
('IfcLightFixture', 'Light Fixture', 'Electrical', 'Lighting luminaire'),
('IfcMotorConnection', 'Motor Connection', 'Electrical', 'Motor control starter'),
('IfcOutlet', 'Electrical Outlet', 'Electrical', 'Power receptacle'),
('IfcProtectiveDevice', 'Protective Device', 'Electrical', 'Circuit breaker or fuse'),
('IfcSwitchingDevice', 'Switch', 'Electrical', 'Light or power switch'),
('IfcTransformer', 'Transformer', 'Electrical', 'Voltage transformer');

-- ========================================
-- Standard IFC Class Labels (Structural)
-- ========================================
INSERT OR IGNORE INTO ifc_labels (ifc_class, friendly_label, category, description) VALUES
('IfcBeam', 'Structural Beam', 'Structural', 'Load-bearing beam'),
('IfcColumn', 'Structural Column', 'Structural', 'Vertical support column'),
('IfcFooting', 'Foundation', 'Structural', 'Foundation footing'),
('IfcPile', 'Pile', 'Structural', 'Deep foundation pile'),
('IfcReinforcingBar', 'Rebar', 'Structural', 'Reinforcing steel bar'),
('IfcReinforcingMesh', 'Mesh Reinforcement', 'Structural', 'Welded wire mesh'),
('IfcSlab', 'Slab', 'Structural', 'Floor or roof slab'),
('IfcStair', 'Stair', 'Architecture', 'Staircase'),
('IfcRailing', 'Railing', 'Architecture', 'Guard rail or handrail'),
('IfcRamp', 'Ramp', 'Architecture', 'Accessible ramp'),
('IfcRoof', 'Roof', 'Architecture', 'Roof structure'),
('IfcMember', 'Structural Member', 'Structural', 'Generic structural member'),
('IfcPlate', 'Plate', 'Structural', 'Steel plate'),
('IfcBearing', 'Bearing', 'Structural', 'Structural bearing');

-- ========================================
-- Standard IFC Class Labels (Architecture)
-- ========================================
INSERT OR IGNORE INTO ifc_labels (ifc_class, friendly_label, category, description) VALUES
('IfcWall', 'Wall', 'Architecture', 'Interior or exterior wall'),
('IfcDoor', 'Door', 'Architecture', 'Door assembly'),
('IfcWindow', 'Window', 'Architecture', 'Window assembly'),
('IfcCurtainWall', 'Curtain Wall', 'Architecture', 'Glazed facade system'),
('IfcOpeningElement', 'Opening', 'Architecture', 'Wall or slab opening'),
('IfcSpace', 'Space', 'Architecture', 'Defined room or area'),
('IfcCovering', 'Ceiling/Floor Covering', 'Architecture', 'Finish material'),
('IfcFurnishingElement', 'Furniture', 'Architecture', 'Furniture element'),
('IfcFurniture', 'Furniture', 'Architecture', 'Furniture object'),
('IfcBuildingElementProxy', 'Generic Building Element', 'Architecture', 'Uncategorized element'),
('IfcChimney', 'Chimney', 'Architecture', 'Chimney or flue');

-- ========================================
-- Discipline Labels
-- ========================================
INSERT OR IGNORE INTO discipline_labels (discipline_code, full_name, description) VALUES
('STR', 'Structural', 'Structural engineering discipline'),
('STRUCT', 'Structural', 'Structural engineering (alternate code)'),
('ARC', 'Architecture', 'Architectural design discipline'),
('ARCH', 'Architecture', 'Architecture (alternate code)'),
('MEP', 'Mechanical, Electrical & Plumbing', 'Combined MEP discipline'),
('ACMV', 'HVAC (Air Conditioning & Mechanical Ventilation)', 'HVAC specialty'),
('PP', 'Plumbing', 'Plumbing and piping discipline'),
('SP', 'Sanitary/Plumbing', 'Sanitary and plumbing systems'),
('ELEC', 'Electrical', 'Electrical systems discipline'),
('FIRE', 'Fire Protection', 'Fire suppression and alarm systems'),
('CIVIL', 'Civil', 'Civil engineering discipline'),
('LANDSCAPE', 'Landscape', 'Landscape architecture');

-- ========================================
-- Metadata
-- ========================================
PRAGMA user_version = 1;

-- Print summary
SELECT
    'IFC Label Dictionary initialized: ' ||
    (SELECT COUNT(*) FROM ifc_labels) || ' IFC classes, ' ||
    (SELECT COUNT(*) FROM discipline_labels) || ' disciplines' AS summary;
