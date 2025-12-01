-- Digital Twin - Federation Integrated Schema
-- Integrates with enhanced_federation.db (3D/4D/5D)
-- Adds 6D/7D capabilities on top of existing federation
-- Version: 2.0 (Federation Integrated)

-- =============================================================================
-- PREREQUISITES
-- This schema assumes enhanced_federation.db exists with:
-- - elements table (IFC geometry and properties)
-- - Spatial indexing
-- - 4D schedule data
-- - 5D BOQ/cost data
-- =============================================================================

-- =============================================================================
-- ASSET LAYER (6D) - Integrated with Federation
-- =============================================================================

CREATE TABLE IF NOT EXISTS assets (
    -- Identity
    guid TEXT PRIMARY KEY,              -- IFC GUID (links to elements.GlobalId)
    federation_element_id INTEGER,      -- FK to elements table
    asset_tag TEXT UNIQUE,              -- Facility barcode/QR code
    name TEXT NOT NULL,                 -- Human-readable name

    -- IFC Properties (denormalized for performance)
    ifc_class TEXT NOT NULL,            -- IfcAirTerminal, IfcChiller, etc.
    ifc_type TEXT,                      -- Type name
    discipline TEXT,                    -- ACMV, ELEC, FP, STR, ARC
    storey TEXT,                        -- Level 0, Level 1, etc.
    space TEXT,                         -- Room/zone location

    -- Equipment Details (6D - Lifecycle)
    manufacturer TEXT,                  -- Trane, Carrier, etc.
    model TEXT,                         -- Model number
    serial_number TEXT,                 -- Serial number
    capacity TEXT,                      -- 500 CFM, 100 kW, etc.

    -- Lifecycle (6D)
    install_date DATE,                  -- Installation date
    warranty_start DATE,                -- Warranty start
    warranty_duration_months INTEGER,   -- Warranty period
    expected_lifespan_years INTEGER,    -- Design life (e.g., 15 years)
    replacement_cost REAL,              -- Estimated replacement cost

    -- Status
    status TEXT DEFAULT 'Active',       -- Active, Inactive, Decommissioned
    condition TEXT DEFAULT 'Good',      -- Excellent, Good, Fair, Poor, Failed

    -- Vendor
    vendor_name TEXT,                   -- Supplier/installer
    vendor_contact TEXT,                -- Phone/email
    vendor_contract_number TEXT,        -- Service contract ref

    -- Metadata
    notes TEXT,                         -- Free-form notes
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_date TEXT DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key to federation elements table
    FOREIGN KEY (federation_element_id) REFERENCES elements(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_assets_guid ON assets(guid);
CREATE INDEX IF NOT EXISTS idx_assets_federation_element ON assets(federation_element_id);
CREATE INDEX IF NOT EXISTS idx_assets_ifc_class ON assets(ifc_class);
CREATE INDEX IF NOT EXISTS idx_assets_discipline ON assets(discipline);
CREATE INDEX IF NOT EXISTS idx_assets_storey ON assets(storey);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);

-- =============================================================================

CREATE TABLE IF NOT EXISTS asset_properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_guid TEXT NOT NULL,
    property_name TEXT NOT NULL,
    property_value TEXT,
    property_type TEXT DEFAULT 'string',  -- string, number, boolean, date
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_asset_props_guid ON asset_properties(asset_guid);
CREATE INDEX IF NOT EXISTS idx_asset_props_name ON asset_properties(property_name);

-- =============================================================================

CREATE TABLE IF NOT EXISTS asset_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_guid TEXT NOT NULL,
    document_type TEXT NOT NULL,      -- Manual, Photo, Warranty, Certificate, Drawing
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,          -- Relative or absolute path
    file_size_kb INTEGER,
    mime_type TEXT,                   -- application/pdf, image/jpeg, etc.
    description TEXT,
    uploaded_by TEXT,
    uploaded_date TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_asset_docs_guid ON asset_documents(asset_guid);
CREATE INDEX IF NOT EXISTS idx_asset_docs_type ON asset_documents(document_type);

-- =============================================================================

CREATE TABLE IF NOT EXISTS asset_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_guid TEXT NOT NULL,
    change_type TEXT NOT NULL,        -- Created, Updated, StatusChange, Decommissioned
    field_name TEXT,                  -- Which field changed
    old_value TEXT,
    new_value TEXT,
    changed_by TEXT,
    changed_date TEXT DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_asset_history_guid ON asset_history(asset_guid);
CREATE INDEX IF NOT EXISTS idx_asset_history_date ON asset_history(changed_date);

-- =============================================================================
-- MAINTENANCE LAYER (6D) - Same as before
-- =============================================================================

CREATE TABLE IF NOT EXISTS pm_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL UNIQUE,
    ifc_class TEXT,                   -- Apply to all of this type
    discipline TEXT,
    description TEXT,
    interval_type TEXT NOT NULL,      -- Daily, Weekly, Monthly, Quarterly, Annually
    interval_value INTEGER DEFAULT 1,
    estimated_hours REAL,
    required_skills TEXT,
    tasks TEXT NOT NULL,              -- JSON array
    parts_list TEXT,                  -- JSON array
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_pm_templates_class ON pm_templates(ifc_class);
CREATE INDEX IF NOT EXISTS idx_pm_templates_discipline ON pm_templates(discipline);
CREATE INDEX IF NOT EXISTS idx_pm_templates_active ON pm_templates(is_active);

-- =============================================================================

CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_number TEXT UNIQUE NOT NULL,
    asset_guid TEXT NOT NULL,

    work_type TEXT NOT NULL,          -- PM, Corrective, Emergency, Inspection
    priority TEXT DEFAULT 'Medium',   -- Low, Medium, High, Critical

    title TEXT NOT NULL,
    description TEXT,
    pm_template_id INTEGER,

    scheduled_date DATE,
    due_date DATE,
    estimated_hours REAL,

    assigned_to TEXT,
    team TEXT,

    status TEXT DEFAULT 'Open',       -- Open, InProgress, Completed, Deferred, Cancelled
    completion_date DATE,
    actual_hours REAL,

    labor_cost REAL,
    parts_cost REAL,
    total_cost REAL,

    created_by TEXT,
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_date TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE,
    FOREIGN KEY (pm_template_id) REFERENCES pm_templates(id)
);

CREATE INDEX IF NOT EXISTS idx_wo_asset ON work_orders(asset_guid);
CREATE INDEX IF NOT EXISTS idx_wo_status ON work_orders(status);
CREATE INDEX IF NOT EXISTS idx_wo_due_date ON work_orders(due_date);
CREATE INDEX IF NOT EXISTS idx_wo_assigned ON work_orders(assigned_to);
CREATE INDEX IF NOT EXISTS idx_wo_type ON work_orders(work_type);

-- =============================================================================

CREATE TABLE IF NOT EXISTS maintenance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL,
    asset_guid TEXT NOT NULL,

    work_performed TEXT NOT NULL,
    findings TEXT,
    corrective_actions TEXT,

    parts_used TEXT,                  -- JSON array

    technician TEXT NOT NULL,
    work_date DATE NOT NULL,
    hours_worked REAL,

    follow_up_required BOOLEAN DEFAULT 0,
    follow_up_notes TEXT,

    logged_by TEXT,
    logged_date TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (work_order_id) REFERENCES work_orders(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_maint_log_asset ON maintenance_log(asset_guid);
CREATE INDEX IF NOT EXISTS idx_maint_log_date ON maintenance_log(work_date);
CREATE INDEX IF NOT EXISTS idx_maint_log_wo ON maintenance_log(work_order_id);

-- =============================================================================

CREATE TABLE IF NOT EXISTS technicians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    skills TEXT,                      -- JSON array
    certifications TEXT,              -- JSON array
    is_active BOOLEAN DEFAULT 1,
    created_date TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_technicians_active ON technicians(is_active);
CREATE INDEX IF NOT EXISTS idx_technicians_employee_id ON technicians(employee_id);

-- =============================================================================

CREATE TABLE IF NOT EXISTS pm_schedule_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_guid TEXT NOT NULL,
    pm_template_id INTEGER NOT NULL,
    last_generated_date DATE,
    next_due_date DATE,
    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE,
    FOREIGN KEY (pm_template_id) REFERENCES pm_templates(id) ON DELETE CASCADE,
    UNIQUE(asset_guid, pm_template_id)
);

CREATE INDEX IF NOT EXISTS idx_pm_state_asset ON pm_schedule_state(asset_guid);
CREATE INDEX IF NOT EXISTS idx_pm_state_next_due ON pm_schedule_state(next_due_date);

-- =============================================================================
-- IoT LAYER (7D) - Same as before
-- =============================================================================

CREATE TABLE IF NOT EXISTS sensors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT UNIQUE NOT NULL,
    asset_guid TEXT NOT NULL,

    sensor_type TEXT NOT NULL,        -- Temperature, Pressure, Flow, etc.
    measurement_unit TEXT NOT NULL,   -- °C, bar, m³/h, etc.

    protocol TEXT,                    -- MQTT, BACnet, OPC UA, HTTP
    topic TEXT,
    update_interval_seconds INTEGER DEFAULT 60,

    is_active BOOLEAN DEFAULT 1,
    last_reading_date TEXT,
    last_reading_value REAL,

    min_threshold REAL,
    max_threshold REAL,
    critical_min REAL,
    critical_max REAL,

    location_description TEXT,
    calibration_date DATE,
    calibration_due_date DATE,
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sensors_asset ON sensors(asset_guid);
CREATE INDEX IF NOT EXISTS idx_sensors_type ON sensors(sensor_type);
CREATE INDEX IF NOT EXISTS idx_sensors_active ON sensors(is_active);
CREATE INDEX IF NOT EXISTS idx_sensors_sensor_id ON sensors(sensor_id);

-- =============================================================================

CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    value REAL NOT NULL,
    quality TEXT DEFAULT 'good',

    FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_readings_sensor ON sensor_readings(sensor_id);
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON sensor_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_readings_sensor_time ON sensor_readings(sensor_id, timestamp);

-- =============================================================================

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    sensor_id TEXT,
    sensor_type TEXT,

    condition_type TEXT NOT NULL,     -- Above, Below, OutOfRange, NoData
    threshold_value REAL,
    threshold_min REAL,
    threshold_max REAL,
    duration_seconds INTEGER DEFAULT 0,

    severity TEXT DEFAULT 'Warning',  -- Info, Warning, Critical

    notify_email TEXT,
    notify_sms TEXT,
    auto_create_work_order BOOLEAN DEFAULT 0,

    is_active BOOLEAN DEFAULT 1,
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_sensor ON alert_rules(sensor_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_type ON alert_rules(sensor_type);
CREATE INDEX IF NOT EXISTS idx_alert_rules_active ON alert_rules(is_active);

-- =============================================================================

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_rule_id INTEGER NOT NULL,
    sensor_id TEXT NOT NULL,
    asset_guid TEXT NOT NULL,

    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    trigger_value REAL,

    triggered_date TEXT NOT NULL,
    acknowledged_date TEXT,
    acknowledged_by TEXT,
    resolved_date TEXT,
    resolved_by TEXT,

    work_order_id INTEGER,
    notes TEXT,

    FOREIGN KEY (alert_rule_id) REFERENCES alert_rules(id),
    FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id),
    FOREIGN KEY (asset_guid) REFERENCES assets(guid),
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_alerts_sensor ON alerts(sensor_id);
CREATE INDEX IF NOT EXISTS idx_alerts_asset ON alerts(asset_guid);
CREATE INDEX IF NOT EXISTS idx_alerts_triggered ON alerts(triggered_date);
CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON alerts(resolved_date) WHERE resolved_date IS NULL;

-- =============================================================================
-- CROSS-DIMENSIONAL VIEWS
-- Useful queries combining 4D/5D/6D/7D data
-- =============================================================================

-- View: Assets with 4D Schedule Info
CREATE VIEW IF NOT EXISTS v_assets_with_schedule AS
SELECT
    a.guid,
    a.name,
    a.ifc_class,
    a.discipline,
    a.condition,
    e.schedule_start_date,
    e.schedule_end_date,
    e.construction_phase
FROM assets a
LEFT JOIN elements e ON a.federation_element_id = e.id;

-- View: Equipment Needing Maintenance (6D)
CREATE VIEW IF NOT EXISTS v_maintenance_due AS
SELECT
    a.guid,
    a.name,
    a.discipline,
    wo.work_order_number,
    wo.due_date,
    wo.priority,
    CASE
        WHEN wo.due_date < DATE('now') THEN 'Overdue'
        WHEN wo.due_date < DATE('now', '+7 days') THEN 'Due This Week'
        ELSE 'Upcoming'
    END as urgency
FROM assets a
JOIN work_orders wo ON a.guid = wo.asset_guid
WHERE wo.status = 'Open'
ORDER BY wo.due_date;

-- View: Assets with Active Alerts (7D)
CREATE VIEW IF NOT EXISTS v_assets_with_alerts AS
SELECT
    a.guid,
    a.name,
    a.discipline,
    COUNT(al.id) as active_alert_count,
    MAX(al.severity) as highest_severity
FROM assets a
JOIN alerts al ON a.guid = al.asset_guid
WHERE al.resolved_date IS NULL
GROUP BY a.guid, a.name, a.discipline;
