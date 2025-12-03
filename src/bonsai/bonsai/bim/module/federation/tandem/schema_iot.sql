-- Digital Twin - IoT Layer Database Schema
-- Phase 3: IoT Integration with Mock Data
-- Version: 1.1
--
-- VIRTUAL SENSOR PATTERN:
-- Sensors without IFC geometry can be visualized using virtual assets.
-- The sensor overlay queries 3D positions from element_transforms via asset_guid.
--
-- To add a virtual sensor:
-- 1. Insert virtual asset in element_transforms (guid, center_x/y/z, transform_source='virtual_sensor')
-- 2. Insert virtual asset in elements_meta (guid, element_name, ifc_class='IfcSensor', discipline)
-- 3. Insert sensor with asset_guid pointing to virtual asset
--
-- See: tandem/add_virtual_sensors.py for example implementation
--
-- =============================================================================
-- IoT LAYER
-- =============================================================================

CREATE TABLE IF NOT EXISTS sensors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT UNIQUE NOT NULL,   -- Unique sensor identifier
    asset_guid TEXT NOT NULL,         -- Which asset this monitors

    -- Sensor Type
    sensor_type TEXT NOT NULL,        -- Temperature, Pressure, Flow, Humidity, CO2, etc.
    measurement_unit TEXT NOT NULL,   -- °C, bar, m³/h, %, ppm

    -- IoT Details
    protocol TEXT,                    -- MQTT, BACnet, OPC UA, HTTP
    topic TEXT,                       -- MQTT topic or BACnet object ID
    update_interval_seconds INTEGER DEFAULT 60,

    -- Status
    is_active BOOLEAN DEFAULT 1,
    last_reading_date TEXT,
    last_reading_value REAL,

    -- Thresholds
    min_threshold REAL,               -- Alert if below
    max_threshold REAL,               -- Alert if above
    critical_min REAL,                -- Critical alert
    critical_max REAL,                -- Critical alert

    -- Metadata
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

-- Simplified time-series table for mock data (SQLite)
-- In production, use InfluxDB
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,          -- ISO format
    value REAL NOT NULL,
    quality TEXT DEFAULT 'good',      -- good, uncertain, bad

    FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_readings_sensor ON sensor_readings(sensor_id);
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON sensor_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_readings_sensor_time ON sensor_readings(sensor_id, timestamp);

-- =============================================================================

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    sensor_id TEXT,                   -- NULL = applies to all sensors of type
    sensor_type TEXT,                 -- Temperature, Pressure, etc.

    -- Condition
    condition_type TEXT NOT NULL,     -- Above, Below, OutOfRange, NoData
    threshold_value REAL,
    threshold_min REAL,
    threshold_max REAL,
    duration_seconds INTEGER DEFAULT 0, -- Alert only if condition persists

    -- Severity
    severity TEXT DEFAULT 'Warning',  -- Info, Warning, Critical

    -- Notification
    notify_email TEXT,                -- Comma-separated emails
    notify_sms TEXT,
    auto_create_work_order BOOLEAN DEFAULT 0,

    -- Status
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

    -- Alert Details
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    trigger_value REAL,

    -- Timeline
    triggered_date TEXT NOT NULL,
    acknowledged_date TEXT,
    acknowledged_by TEXT,
    resolved_date TEXT,
    resolved_by TEXT,

    -- Actions
    work_order_id INTEGER,            -- If WO created
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
