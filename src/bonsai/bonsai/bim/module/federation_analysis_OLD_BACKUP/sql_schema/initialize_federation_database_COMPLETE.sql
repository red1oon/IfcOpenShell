-- ============================================================================
-- COMPLETE FEDERATION DATABASE SCHEMA - ALL TABLES
-- ============================================================================
-- Purpose: One-stop schema initialization for complete database recreation
--          Includes: Federation core, Clash detection, Resolution system,
--                    BOQ, Conduit routing, Learning system
--
-- Usage: Create a fresh database from scratch:
--   sqlite3 DatabaseFiles/new_database.db < Scripts/initialize_federation_database_COMPLETE.sql
--
-- Version: 3.0 (Consolidated - All Systems)
-- Date: 2025-11-06
-- Status: POC - Hardcoded CREATE TABLE statements still exist in Python files
--         (see HOUSEKEEPING NOTES section at end)
-- ============================================================================

-- ============================================================================
-- SECTION 1: CORE FEDERATION TABLES (Geometry & Metadata)
-- ============================================================================

-- Elements Metadata: Core element information
CREATE TABLE IF NOT EXISTS elements_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT UNIQUE NOT NULL,
    discipline TEXT NOT NULL,
    ifc_class TEXT NOT NULL,
    filepath TEXT,
    element_name TEXT,
    element_type TEXT,
    element_description TEXT,
    storey TEXT,
    material_name TEXT,
    material_rgba TEXT
);

CREATE INDEX IF NOT EXISTS idx_elements_discipline ON elements_meta(discipline);
CREATE INDEX IF NOT EXISTS idx_elements_class ON elements_meta(ifc_class);
CREATE INDEX IF NOT EXISTS idx_elements_guid ON elements_meta(guid);

-- Base Geometries: Instanced geometry storage (memory efficient)
CREATE TABLE IF NOT EXISTS base_geometries (
    geometry_hash TEXT PRIMARY KEY,
    vertices BLOB NOT NULL,
    faces BLOB NOT NULL,
    normals BLOB,
    vertex_count INTEGER NOT NULL,
    face_count INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_base_geom_hash ON base_geometries(geometry_hash);

-- Element Instances: Links elements to geometry
CREATE TABLE IF NOT EXISTS element_instances (
    guid TEXT PRIMARY KEY,
    geometry_hash TEXT NOT NULL,
    FOREIGN KEY (geometry_hash) REFERENCES base_geometries(geometry_hash),
    FOREIGN KEY (guid) REFERENCES elements_meta(guid)
);

CREATE INDEX IF NOT EXISTS idx_geom_hash ON element_instances(geometry_hash);

-- Element Transforms: Position and orientation in GPS space
CREATE TABLE IF NOT EXISTS element_transforms (
    guid TEXT PRIMARY KEY,
    center_x REAL NOT NULL,
    center_y REAL NOT NULL,
    center_z REAL NOT NULL,
    transform_source TEXT DEFAULT 'tessellation',
    FOREIGN KEY (guid) REFERENCES elements_meta(guid)
);

CREATE INDEX IF NOT EXISTS idx_transforms_guid ON element_transforms(guid);

-- Spatial R-tree: Fast spatial queries for clash detection
-- Note: Virtual table, created separately by extraction script
-- CREATE VIRTUAL TABLE elements_rtree USING rtree(
--     id,                     -- Element row ID
--     minX, maxX,            -- Bounding box coordinates
--     minY, maxY,
--     minZ, maxZ
-- );

-- Global Offset: Coordinate system reference
CREATE TABLE IF NOT EXISTS global_offset (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    offset_x REAL NOT NULL DEFAULT 0.0,
    offset_y REAL NOT NULL DEFAULT 0.0,
    offset_z REAL NOT NULL DEFAULT 0.0,
    notes TEXT
);

-- Insert default offset (0,0,0) - GPS coordinates used directly
INSERT OR IGNORE INTO global_offset (id, offset_x, offset_y, offset_z, notes)
VALUES (1, 0.0, 0.0, 0.0, 'GPS coordinates - IfcMapConversion applied by IfcOpenShell');

-- Spatial Structure: Building/storey/space hierarchy
CREATE TABLE IF NOT EXISTS spatial_structure (
    guid TEXT PRIMARY KEY,
    building TEXT,
    storey TEXT,
    space TEXT,
    FOREIGN KEY (guid) REFERENCES elements_meta(guid)
);

CREATE INDEX IF NOT EXISTS idx_spatial_storey ON spatial_structure(storey);
CREATE INDEX IF NOT EXISTS idx_spatial_building ON spatial_structure(building);

-- Element Properties: IFC property sets
CREATE TABLE IF NOT EXISTS element_properties (
    guid TEXT NOT NULL,
    pset_name TEXT NOT NULL,
    property_name TEXT NOT NULL,
    property_value TEXT,
    FOREIGN KEY (guid) REFERENCES elements_meta(guid)
);

CREATE INDEX IF NOT EXISTS idx_props_guid ON element_properties(guid);
CREATE INDEX IF NOT EXISTS idx_props_pset ON element_properties(pset_name);

-- Material Assignments: Material and color information
CREATE TABLE IF NOT EXISTS material_assignments (
    guid TEXT NOT NULL,
    material_name TEXT,
    rgba TEXT,
    FOREIGN KEY (guid) REFERENCES elements_meta(guid)
);

CREATE INDEX IF NOT EXISTS idx_materials_guid ON material_assignments(guid);

-- Applied Movements: Track position adjustments during coordination
CREATE TABLE IF NOT EXISTS applied_movements (
    guid TEXT PRIMARY KEY,
    delta_x REAL NOT NULL,
    delta_y REAL NOT NULL,
    delta_z REAL NOT NULL,
    applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_by TEXT,
    reason TEXT,
    FOREIGN KEY (guid) REFERENCES elements_meta(guid)
);

CREATE INDEX IF NOT EXISTS idx_movements_guid ON applied_movements(guid);
CREATE INDEX IF NOT EXISTS idx_movements_date ON applied_movements(applied_date);

-- ============================================================================
-- SECTION 2: CLASH DETECTION SYSTEM
-- ============================================================================

-- Clash Status: Individual clash records with workflow state
CREATE TABLE IF NOT EXISTS clash_status (
    clash_id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid_a TEXT NOT NULL,
    guid_b TEXT NOT NULL,
    name_a TEXT,
    name_b TEXT,
    ifc_class_a TEXT,
    ifc_class_b TEXT,
    discipline_a TEXT,
    discipline_b TEXT,
    status TEXT DEFAULT 'NEW',
    assigned_to TEXT,
    comment TEXT,
    is_ignored INTEGER DEFAULT 0,
    distance REAL,
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guid_a, guid_b)
);

CREATE INDEX IF NOT EXISTS idx_clash_status_guid_a ON clash_status(guid_a);
CREATE INDEX IF NOT EXISTS idx_clash_status_guid_b ON clash_status(guid_b);
CREATE INDEX IF NOT EXISTS idx_clash_status_status ON clash_status(status);
CREATE INDEX IF NOT EXISTS idx_clash_status_discipline ON clash_status(discipline_a, discipline_b);
CREATE INDEX IF NOT EXISTS idx_clash_status_date_created ON clash_status(date_created);

-- Clash History: Audit log for status changes
CREATE TABLE IF NOT EXISTS clash_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clash_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT,
    changed_by TEXT,
    change_date TIMESTAMP NOT NULL,
    comment TEXT,
    FOREIGN KEY (clash_id) REFERENCES clash_status(clash_id)
);

CREATE INDEX IF NOT EXISTS idx_clash_history_clash ON clash_history(clash_id);
CREATE INDEX IF NOT EXISTS idx_clash_history_date ON clash_history(change_date);

-- Clash Groups: Cascade element groupings
CREATE TABLE IF NOT EXISTS clash_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT UNIQUE NOT NULL,
    cascade_element_guid TEXT NOT NULL,
    cascade_element_class TEXT,
    cascade_element_discipline TEXT,
    total_clashes INTEGER NOT NULL,
    affected_disciplines TEXT,  -- JSON array
    affected_classes TEXT,      -- JSON array
    status_summary TEXT,        -- JSON object
    severity TEXT NOT NULL,
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_clash_groups_guid ON clash_groups(cascade_element_guid);
CREATE INDEX IF NOT EXISTS idx_clash_groups_severity ON clash_groups(severity);

-- Clash Group Members: Many-to-many relationship
CREATE TABLE IF NOT EXISTS clash_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,
    clash_id INTEGER NOT NULL,
    FOREIGN KEY (group_id) REFERENCES clash_groups(group_id),
    FOREIGN KEY (clash_id) REFERENCES clash_status(clash_id),
    UNIQUE(group_id, clash_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_group ON clash_group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_group_members_clash ON clash_group_members(clash_id);

-- Clashes (Legacy): Simple clash storage from detector.py
-- NOTE: This is a duplicate/alternative clash table used by detector.py
-- TODO: Consolidate with clash_status in Phase 2
CREATE TABLE IF NOT EXISTS clashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clash_set TEXT,
    elem_a_guid TEXT,
    elem_b_guid TEXT,
    elem_a_discipline TEXT,
    elem_b_discipline TEXT,
    elem_a_ifc_class TEXT,
    elem_b_ifc_class TEXT,
    overlap_volume REAL,
    clearance REAL,
    status TEXT DEFAULT 'NEW',
    detected_date TEXT,
    reviewed_date TEXT,
    reviewed_by TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_clashes_guids ON clashes(elem_a_guid, elem_b_guid);
CREATE INDEX IF NOT EXISTS idx_clashes_status ON clashes(status);

-- ============================================================================
-- SECTION 3: INTELLIGENT RESOLUTION SYSTEM
-- ============================================================================

-- Resolution Options: Alternative solutions with cost/effort estimates
CREATE TABLE IF NOT EXISTS resolution_options (
    option_id TEXT PRIMARY KEY,
    clash_id TEXT,
    group_id TEXT,

    -- Option metadata
    option_type TEXT NOT NULL,
    description TEXT NOT NULL,
    recommendation_rank INTEGER,

    -- Design effort (PRIMARY optimization target)
    total_design_hours REAL NOT NULL,
    total_design_cost REAL NOT NULL,

    -- Schedule impact (SECONDARY optimization target)
    calendar_days_required REAL NOT NULL,
    schedule_delay_cost REAL,

    -- Construction cost (CONSTRAINT, not optimization target)
    estimated_construction_cost REAL,
    exceeds_budget BOOLEAN DEFAULT 0,

    -- Technical feasibility
    technically_feasible BOOLEAN DEFAULT 1,
    feasibility_notes TEXT,

    -- Risk assessment
    risk_score INTEGER,
    risk_category TEXT,
    risk_factors TEXT,  -- JSON array

    -- Impact summary
    affected_disciplines TEXT,  -- JSON array
    clashes_resolved INTEGER,

    -- Metadata
    generated_date TIMESTAMP NOT NULL,
    generated_by TEXT,

    FOREIGN KEY (clash_id) REFERENCES clash_status(clash_id),
    FOREIGN KEY (group_id) REFERENCES clash_groups(group_id)
);

CREATE INDEX IF NOT EXISTS idx_resolution_clash ON resolution_options(clash_id);
CREATE INDEX IF NOT EXISTS idx_resolution_group ON resolution_options(group_id);
CREATE INDEX IF NOT EXISTS idx_resolution_rank ON resolution_options(recommendation_rank);

-- Design Effort Estimates: Activity-based cost breakdown
CREATE TABLE IF NOT EXISTS design_effort_estimates (
    effort_id TEXT PRIMARY KEY,
    option_id TEXT NOT NULL,

    -- Discipline and activity
    discipline TEXT NOT NULL,
    activity_type TEXT NOT NULL,

    -- Effort quantification
    estimated_hours REAL NOT NULL,
    skill_level TEXT NOT NULL,
    hourly_rate REAL NOT NULL,
    total_cost REAL NOT NULL,

    -- Schedule
    calendar_days_required REAL,
    can_parallel BOOLEAN DEFAULT 0,
    prerequisite_efforts TEXT,  -- JSON array

    -- Documentation impact
    drawing_sheets_affected INTEGER DEFAULT 0,
    specification_sections_affected INTEGER DEFAULT 0,

    -- Approval requirements
    requires_approval BOOLEAN DEFAULT 0,
    approval_authority TEXT,
    typical_approval_days REAL,
    approval_rejection_risk REAL,

    -- Metadata
    confidence_level TEXT,
    basis_of_estimate TEXT,
    notes TEXT,

    FOREIGN KEY (option_id) REFERENCES resolution_options(option_id)
);

CREATE INDEX IF NOT EXISTS idx_effort_option ON design_effort_estimates(option_id);
CREATE INDEX IF NOT EXISTS idx_effort_discipline ON design_effort_estimates(discipline);

-- Discipline Rates: Labor rates by discipline and skill level
CREATE TABLE IF NOT EXISTS discipline_rates (
    rate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline TEXT NOT NULL,
    skill_level TEXT NOT NULL,
    hourly_rate REAL NOT NULL,
    region TEXT DEFAULT 'US',
    effective_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    UNIQUE(discipline, skill_level, region)
);

CREATE INDEX IF NOT EXISTS idx_rates_discipline ON discipline_rates(discipline);

-- Resolution History: Track chosen options and actual outcomes
CREATE TABLE IF NOT EXISTS resolution_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    clash_id TEXT,
    group_id TEXT,
    option_id TEXT,

    -- Selection
    selected_date TIMESTAMP NOT NULL,
    selected_by TEXT,
    selection_notes TEXT,

    -- Implementation
    implemented_date TIMESTAMP,
    actual_design_hours REAL,
    actual_design_cost REAL,
    actual_calendar_days REAL,

    -- Outcome
    outcome_status TEXT,  -- 'successful', 'partial', 'failed'
    clashes_actually_resolved INTEGER,
    new_clashes_introduced INTEGER,

    -- Learning data
    variance_hours REAL,
    variance_cost REAL,
    variance_days REAL,
    lessons_learned TEXT,
    user_rating INTEGER,  -- 1-5 stars

    FOREIGN KEY (clash_id) REFERENCES clash_status(clash_id),
    FOREIGN KEY (group_id) REFERENCES clash_groups(group_id),
    FOREIGN KEY (option_id) REFERENCES resolution_options(option_id)
);

CREATE INDEX IF NOT EXISTS idx_history_option ON resolution_history(option_id);
CREATE INDEX IF NOT EXISTS idx_history_date ON resolution_history(selected_date);

-- ============================================================================
-- SECTION 4: PHASE 1.5 - CONFIGURATION SYSTEM
-- ============================================================================

-- Activity Base Durations: Replaces hardcoded values in resolution_engine.py
CREATE TABLE IF NOT EXISTS activity_base_durations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Activity identification
    activity_type TEXT NOT NULL,            -- 'modeling', 'verification', 'documentation', 'coordination'
    ifc_class TEXT,                         -- NULL = default for all classes
    discipline TEXT,                        -- NULL = default for all disciplines

    -- Duration estimates
    base_hours REAL NOT NULL,               -- Base hours for activity
    complexity_multiplier REAL DEFAULT 0.10, -- Additional % per clash (e.g., 0.10 = 10%)
    min_hours REAL,                         -- Optional: hard minimum
    max_hours REAL,                         -- Optional: hard maximum

    -- Source tracking (3-tier lookup)
    source TEXT DEFAULT 'default',          -- 'default', 'project', 'learned'
    project_id TEXT,                        -- NULL = global default

    -- Learning metadata
    confidence_score REAL DEFAULT 0,        -- 0-100, increases with learning
    sample_size INTEGER DEFAULT 0,          -- Number of learning samples
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    notes TEXT,

    UNIQUE(activity_type, ifc_class, discipline, project_id, source)
);

CREATE INDEX IF NOT EXISTS idx_activity_durations_type ON activity_base_durations(activity_type);
CREATE INDEX IF NOT EXISTS idx_activity_durations_source ON activity_base_durations(source);
CREATE INDEX IF NOT EXISTS idx_activity_durations_project ON activity_base_durations(project_id);

-- Configuration Presets: Regional/market-specific rate sets
CREATE TABLE IF NOT EXISTS configuration_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preset_name TEXT UNIQUE NOT NULL,       -- 'US Market', 'Singapore', 'EU Standard'
    description TEXT,
    is_active BOOLEAN DEFAULT 0,            -- Only one can be active
    currency TEXT DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_presets_active ON configuration_presets(is_active);

-- Preset Discipline Rates: Labor rates per preset
CREATE TABLE IF NOT EXISTS preset_discipline_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preset_id INTEGER NOT NULL REFERENCES configuration_presets(id) ON DELETE CASCADE,
    discipline TEXT NOT NULL,
    skill_level TEXT NOT NULL,              -- 'senior', 'intermediate', 'junior'
    hourly_rate REAL NOT NULL,
    currency TEXT DEFAULT 'USD',
    UNIQUE(preset_id, discipline, skill_level)
);

CREATE INDEX IF NOT EXISTS idx_preset_rates_preset ON preset_discipline_rates(preset_id);
CREATE INDEX IF NOT EXISTS idx_preset_rates_discipline ON preset_discipline_rates(discipline);

-- ============================================================================
-- SECTION 5: PHASE 2 - LEARNING SYSTEM
-- ============================================================================

-- Learning Metrics: Variance tracking for continuous improvement
CREATE TABLE IF NOT EXISTS learning_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resolution_id INTEGER REFERENCES resolution_history(history_id) ON DELETE CASCADE,

    -- Activity breakdown
    activity_type TEXT NOT NULL,            -- Which activity this metric is for
    ifc_class TEXT,
    discipline TEXT,

    -- Estimates vs Actuals
    estimated_hours REAL NOT NULL,
    actual_hours REAL NOT NULL,
    variance_hours REAL,                    -- actual - estimated
    variance_percent REAL,                  -- (actual - estimated) / estimated * 100

    -- Quality weighting
    user_rating INTEGER,                    -- 1-5 stars (weight higher ratings more)

    -- Context
    project_id TEXT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_learning_metrics_resolution ON learning_metrics(resolution_id);
CREATE INDEX IF NOT EXISTS idx_learning_metrics_activity ON learning_metrics(activity_type, ifc_class, discipline);
CREATE INDEX IF NOT EXISTS idx_learning_metrics_project ON learning_metrics(project_id);

-- Learning Summary View: Dashboard for variance analysis
CREATE VIEW IF NOT EXISTS learning_summary AS
SELECT
    activity_type,
    ifc_class,
    discipline,
    COUNT(*) as sample_count,
    AVG(estimated_hours) as avg_estimated,
    AVG(actual_hours) as avg_actual,
    AVG(variance_percent) as avg_variance_pct,
    -- Note: SQLite doesn't have STDEV, would need custom function
    AVG(user_rating) as avg_rating,
    MIN(recorded_at) as first_sample,
    MAX(recorded_at) as latest_sample
FROM learning_metrics
GROUP BY activity_type, ifc_class, discipline
HAVING sample_count >= 3;  -- Only show if 3+ samples

-- ============================================================================
-- SECTION 6: BOQ (BILL OF QUANTITIES) SYSTEM
-- ============================================================================

-- Simple QTO: Quantity takeoff summary by discipline and class
CREATE TABLE IF NOT EXISTS simple_qto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline TEXT,
    ifc_class TEXT,
    measurement_type TEXT,  -- 'LINEAR', 'AREA', 'VOLUME', 'COUNT'
    element_count INTEGER,
    total_quantity REAL,
    uom TEXT,  -- 'M', 'M2', 'M3', 'EA'
    avg_quantity REAL,
    unit_cost_rm REAL,  -- Unit cost in Malaysian Ringgit
    total_cost_rm REAL  -- Total cost (quantity × unit cost)
);

CREATE INDEX IF NOT EXISTS idx_qto_discipline ON simple_qto(discipline);
CREATE INDEX IF NOT EXISTS idx_qto_class ON simple_qto(ifc_class);

-- ============================================================================
-- SECTION 7: MEP ROUTING SYSTEM
-- ============================================================================

-- Conduit Routes: Calculated conduit routes for later IFC export
CREATE TABLE IF NOT EXISTS conduit_routes (
    route_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_timestamp TEXT NOT NULL,

    -- Route parameters
    start_x REAL NOT NULL,
    start_y REAL NOT NULL,
    start_z REAL NOT NULL,
    end_x REAL NOT NULL,
    end_y REAL NOT NULL,
    end_z REAL NOT NULL,

    -- Conduit specifications
    diameter_mm REAL NOT NULL,
    conduit_type TEXT DEFAULT 'CABLE_CARRIER',

    -- Pathfinding results
    waypoint_count INTEGER NOT NULL,
    waypoints_json TEXT NOT NULL,  -- JSON array of [x, y, z] coordinates

    -- Obstacle avoidance info
    clearance_mm REAL DEFAULT 500.0,
    disciplines_avoided TEXT,  -- Comma-separated: "STR,ACMV,ARC"
    obstacles_encountered INTEGER DEFAULT 0,

    -- Status
    status TEXT DEFAULT 'calculated',  -- 'calculated', 'exported_to_ifc', 'deleted'
    blender_object_name TEXT,

    -- Optional metadata
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_routes_timestamp ON conduit_routes(created_timestamp);
CREATE INDEX IF NOT EXISTS idx_routes_status ON conduit_routes(status);

-- Route Waypoints: Detail table for complex routes
CREATE TABLE IF NOT EXISTS route_waypoints (
    waypoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL,
    waypoint_index INTEGER NOT NULL,  -- Order in route (0, 1, 2...)
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL NOT NULL,
    waypoint_type TEXT DEFAULT 'path',  -- 'start', 'path', 'bend', 'end'

    FOREIGN KEY (route_id) REFERENCES conduit_routes(route_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_waypoints_route ON route_waypoints(route_id);

-- ============================================================================
-- SECTION 8: SCHEMA VERSION TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY,
    applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('1.0', 'Initial schema: clash_status, clash_groups, resolution_options'),
    ('2.0', 'Phase 1.5 + Phase 2: Configuration presets, learning metrics'),
    ('3.0', 'Consolidated schema: All systems unified');

-- ============================================================================
-- SECTION 9: DEFAULT DATA
-- ============================================================================

-- Insert US Market rates
INSERT OR IGNORE INTO discipline_rates (discipline, skill_level, hourly_rate, region, notes) VALUES
    ('ARCHITECTURE', 'senior', 165.00, 'US', 'Principal architect, 15+ years'),
    ('ARCHITECTURE', 'intermediate', 135.00, 'US', 'Project architect, 5-15 years'),
    ('ARCHITECTURE', 'junior', 95.00, 'US', 'Junior architect, 0-5 years'),
    ('ARCHITECTURE', 'drafter', 75.00, 'US', 'CAD drafter/technician'),

    ('STRUCTURE', 'senior', 185.00, 'US', 'Principal structural engineer'),
    ('STRUCTURE', 'intermediate', 165.00, 'US', 'Project structural engineer'),
    ('STRUCTURE', 'junior', 115.00, 'US', 'Junior structural engineer'),

    ('MEP', 'senior', 155.00, 'US', 'Senior MEP engineer'),
    ('MEP', 'intermediate', 125.00, 'US', 'MEP design engineer'),
    ('MEP', 'junior', 95.00, 'US', 'Junior MEP engineer'),
    ('MEP', 'drafter', 70.00, 'US', 'MEP CAD technician'),

    ('COORDINATION', 'senior', 145.00, 'US', 'Senior BIM coordinator'),
    ('COORDINATION', 'intermediate', 115.00, 'US', 'BIM coordinator'),
    ('COORDINATION', 'junior', 85.00, 'US', 'Junior BIM modeler');

-- Insert default presets
INSERT OR IGNORE INTO configuration_presets (preset_name, description, is_active, currency) VALUES
    ('US Market', 'Standard US labor rates (2025)', 1, 'USD'),
    ('Singapore', 'Singapore market rates (SGD)', 0, 'SGD'),
    ('EU Standard', 'European market rates (EUR)', 0, 'EUR');

-- Insert US Market preset rates
INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'ARCHITECTURE', 'senior', 165.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';
INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'ARCHITECTURE', 'intermediate', 135.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';
INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'ARCHITECTURE', 'junior', 95.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';

INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'STRUCTURE', 'senior', 185.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';
INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'STRUCTURE', 'intermediate', 165.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';
INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'STRUCTURE', 'junior', 115.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';

INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'MEP', 'senior', 155.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';
INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'MEP', 'intermediate', 125.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';
INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'MEP', 'junior', 95.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';

INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'COORDINATION', 'senior', 145.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';
INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'COORDINATION', 'intermediate', 115.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';
INSERT OR IGNORE INTO preset_discipline_rates (preset_id, discipline, skill_level, hourly_rate, currency)
SELECT id, 'COORDINATION', 'junior', 85.00, 'USD' FROM configuration_presets WHERE preset_name = 'US Market';

-- Insert default activity durations
INSERT OR IGNORE INTO activity_base_durations (activity_type, ifc_class, discipline, base_hours, complexity_multiplier, source, notes) VALUES
    ('modeling', NULL, NULL, 4.0, 0.10, 'default', 'Generic modeling task'),
    ('verification', NULL, NULL, 1.0, 0.08, 'default', 'Generic clearance verification'),
    ('documentation', NULL, NULL, 2.0, 0.05, 'default', 'Generic drawing updates'),
    ('coordination', NULL, NULL, 0.5, 0.15, 'default', 'Generic coordination meeting time');

-- MEP-specific defaults
INSERT OR IGNORE INTO activity_base_durations (activity_type, ifc_class, discipline, base_hours, complexity_multiplier, source, notes) VALUES
    ('modeling', 'IfcDuctSegment', 'MEP', 3.5, 0.12, 'default', 'Duct reroute modeling'),
    ('modeling', 'IfcPipeSegment', 'MEP', 3.0, 0.12, 'default', 'Pipe reroute modeling'),
    ('modeling', 'IfcCableCarrierSegment', 'MEP', 2.5, 0.10, 'default', 'Cable tray reroute');

-- Structure-specific defaults
INSERT OR IGNORE INTO activity_base_durations (activity_type, ifc_class, discipline, base_hours, complexity_multiplier, source, notes) VALUES
    ('modeling', 'IfcSlab', 'STRUCTURE', 5.0, 0.08, 'default', 'Slab adjustment (more complex)'),
    ('modeling', 'IfcBeam', 'STRUCTURE', 4.5, 0.10, 'default', 'Beam adjustment');

-- ============================================================================
-- SECTION 9: IFC LABEL DICTIONARY (Optional - Human-Readable Naming)
-- ============================================================================
-- Purpose: Map cryptic IFC class names to friendly labels for reports
-- Status: OPTIONAL - System has fallback in-memory labels
-- Usage: Custom naming per-project or organization
-- Reference: ifc_label_mapper.py uses this table if it exists

-- IFC Class Labels Table
CREATE TABLE IF NOT EXISTS ifc_labels (
    ifc_class TEXT PRIMARY KEY,
    friendly_label TEXT NOT NULL,
    category TEXT,            -- e.g., 'MEP-HVAC', 'Structural', 'Architecture'
    description TEXT,         -- Optional notes about this class
    custom_label TEXT,        -- Project-specific override (if different from standard)
    updated_date TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ifc_labels_class ON ifc_labels(ifc_class);
CREATE INDEX IF NOT EXISTS idx_ifc_labels_category ON ifc_labels(category);

-- Discipline Labels Table
CREATE TABLE IF NOT EXISTS discipline_labels (
    discipline_code TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    description TEXT,
    is_custom BOOLEAN DEFAULT 0,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- NOTE: Detailed INSERT statements for standard labels are in:
--       Scripts/initialize_ifc_label_dictionary.sql
--       Run that script separately if you want pre-populated labels.
--       System works fine without it (uses fallback dictionary).

-- ============================================================================
-- HOUSEKEEPING NOTES
-- ============================================================================
--
-- STATUS: POC Phase - Hardcoded table creation still exists in Python files
--
-- KNOWN DUPLICATE/HARDCODED CREATE TABLE LOCATIONS:
-- 1. clash/detector.py:268 - Creates 'clashes' table (legacy format)
-- 2. clash/database.py:51 - Creates 'clash_status' and 'clash_history' tables
-- 3. clash/resolution_database.py:99 - Creates resolution tables
-- 4. clash/clash_grouping.py - May have additional CREATE TABLE statements
-- 5. tests/test_5_gizmo_interactions.py:34 - Test fixtures with hardcoded schema
--
-- MIGRATION PATH:
-- Phase 1 (Current): Hardcoded tables in Python for POC flexibility
-- Phase 2 (Production): Migrate to use this consolidated schema
-- - Update Python files to check for table existence, not create
-- - Add schema migration system for version upgrades
-- - Add database validation on startup
--
-- NEXT STEPS FOR PRODUCTION:
-- 1. Update all Python files to REMOVE hardcoded CREATE TABLE statements
-- 2. Add startup check: Verify schema_version table exists
-- 3. Add migration scripts for schema upgrades (3.0 → 3.1, etc.)
-- 4. Add database validation utility
-- 5. Document database recreation procedure
--
-- ============================================================================
-- END OF CONSOLIDATED SCHEMA
-- ============================================================================
