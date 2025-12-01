# Digital Twin - Database Schema

**Complete database design for Asset Management, Maintenance, and IoT Integration**

Version: 2.1 (Federation Integrated)
Database: enhanced_federation.db (SQLite/PostgreSQL)
Time-Series: InfluxDB / TimescaleDB (optional for Phase 5)

---

## Federation Integration Architecture

**Key Change:** Digital Twin tables now reside in `enhanced_federation.db` alongside 3D/4D/5D BIM data.

```
enhanced_federation.db
│
├── [EXISTING] elements - IFC geometry, 4D schedule, 5D cost
│   ├── id (PK)
│   ├── GlobalId
│   ├── ifc_class
│   ├── schedule_start_date (4D)
│   ├── cost_total (5D)
│   └── ...
│
└── [NEW] Digital Twin Tables (6D/7D)
    │
    ├── ASSET LAYER (6D)
    │   ├── assets → FK to elements.id ⭐
    │   ├── asset_properties
    │   ├── asset_documents
    │   └── asset_history
    │
    ├── MAINTENANCE LAYER (6D)
    │   ├── pm_templates
    │   ├── work_orders → FK to assets.guid
    │   ├── maintenance_log
    │   ├── technicians
    │   └── pm_schedule_state
    │
    └── IoT LAYER (7D)
        ├── sensors → FK to assets.guid
        ├── sensor_readings (time-series)
        ├── alert_rules
        └── alerts → FK to sensors.sensor_id + assets.guid
```

## Schema Overview

```
┌─────────────────────────┐
│  FEDERATION (3D/4D/5D)  │
│  - elements (EXISTING)  │──┐
└─────────────────────────┘  │
                             │ FK: federation_element_id
┌─────────────────┐          │
│  ASSET LAYER    │          │
│  - assets       │◄─────────┘
│  - properties   │
│  - documents    │
│  - history      │
└─────────────────┘
        │
        │ FK: asset_guid
        │
┌─────────────────┐
│ MAINTENANCE     │
│  - pm_templates │
│  - work_orders  │◄─┐
│  - maint_log    │  │
│  - technicians  │  │
└─────────────────┘  │
                     │
┌─────────────────┐  │
│  IoT LAYER      │  │
│  - sensors      │◄─┘
│  - readings     │ (time-series)
│  - alert_rules  │
│  - alerts       │
└─────────────────┘
```

---

## ASSET LAYER

### Table: `assets`
**Purpose:** Core asset registry with federation integration

```sql
CREATE TABLE assets (
    -- Identity
    guid TEXT PRIMARY KEY,              -- IFC GUID (from IFC model)
    federation_element_id INTEGER,      -- ⭐ NEW: FK to elements table
    asset_tag TEXT UNIQUE,              -- Facility barcode/QR code
    name TEXT NOT NULL,                 -- Human-readable name

    -- IFC Properties (denormalized from elements for performance)
    ifc_class TEXT NOT NULL,            -- IfcAirTerminal, IfcChiller, etc.
    ifc_type TEXT,                      -- Type name
    discipline TEXT,                    -- ACMV, ELEC, FP, STR, ARC
    storey TEXT,                        -- Level 0, Level 1, etc.
    space TEXT,                         -- Room/zone location

    -- Equipment Details
    manufacturer TEXT,                  -- Trane, Carrier, etc.
    model TEXT,                         -- Model number
    serial_number TEXT,                 -- Serial number
    capacity TEXT,                      -- 500 CFM, 100 kW, etc.

    -- Lifecycle
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

    -- ⭐ NEW: Foreign key to federation elements table
    FOREIGN KEY (federation_element_id) REFERENCES elements(id) ON DELETE CASCADE
);

CREATE INDEX idx_assets_guid ON assets(guid);
CREATE INDEX idx_assets_federation_element ON assets(federation_element_id);  -- ⭐ NEW
CREATE INDEX idx_assets_ifc_class ON assets(ifc_class);
CREATE INDEX idx_assets_discipline ON assets(discipline);
CREATE INDEX idx_assets_storey ON assets(storey);
CREATE INDEX idx_assets_status ON assets(status);
CREATE INDEX idx_assets_warranty_end ON assets(warranty_start, warranty_duration_months);
```

**Example Data:**
```sql
INSERT INTO assets VALUES (
    '2O2Fr$t4X7Zf8NOew3FNr2',          -- guid
    'AHU-01',                            -- asset_tag
    'Air Handling Unit - Level 3 East', -- name
    'IfcAirHandlingUnit',                -- ifc_class
    'AHU-RTAA',                          -- ifc_type
    'ACMV',                              -- discipline
    'Level 3',                           -- storey
    'Mechanical Room 3E',                -- space
    'Trane',                             -- manufacturer
    'RTAA-140',                          -- model
    'SN-2024-001234',                    -- serial_number
    '14,000 CFM',                        -- capacity
    '2024-03-15',                        -- install_date
    '2024-03-15',                        -- warranty_start
    12,                                  -- warranty_duration_months
    15,                                  -- expected_lifespan_years
    85000.00,                            -- replacement_cost
    'Active',                            -- status
    'Good',                              -- condition
    'ACME HVAC Services',                -- vendor_name
    'service@acmehvac.com',              -- vendor_contact
    'CONTRACT-2024-789',                 -- vendor_contract_number
    'Commissioned 2024-04-01',           -- notes
    '2024-03-15 10:30:00',               -- created_date
    '2025-11-30 14:00:00'                -- updated_date
);
```

---

### Table: `asset_properties`
**Purpose:** Flexible key-value metadata

```sql
CREATE TABLE asset_properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_guid TEXT NOT NULL,
    property_name TEXT NOT NULL,
    property_value TEXT,
    property_type TEXT DEFAULT 'string',  -- string, number, boolean, date
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
);

CREATE INDEX idx_asset_props_guid ON asset_properties(asset_guid);
CREATE INDEX idx_asset_props_name ON asset_properties(property_name);
```

**Example Data:**
```sql
-- Custom properties not in main table
INSERT INTO asset_properties VALUES
    (1, '2O2Fr$t4X7Zf8NOew3FNr2', 'filter_type', 'MERV 13', 'string', '2024-03-15'),
    (2, '2O2Fr$t4X7Zf8NOew3FNr2', 'voltage', '480V 3-phase', 'string', '2024-03-15'),
    (3, '2O2Fr$t4X7Zf8NOew3FNr2', 'motor_hp', '25', 'number', '2024-03-15'),
    (4, '2O2Fr$t4X7Zf8NOew3FNr2', 'vfd_enabled', 'true', 'boolean', '2024-03-15');
```

---

### Table: `asset_documents`
**Purpose:** File attachments (manuals, photos, certificates)

```sql
CREATE TABLE asset_documents (
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

CREATE INDEX idx_asset_docs_guid ON asset_documents(asset_guid);
CREATE INDEX idx_asset_docs_type ON asset_documents(document_type);
```

**Example Data:**
```sql
INSERT INTO asset_documents VALUES
    (1, '2O2Fr$t4X7Zf8NOew3FNr2', 'Manual', 'Trane_RTAA140_Manual.pdf',
     '/documents/manuals/AHU-01_manual.pdf', 2048, 'application/pdf',
     'Installation and Operation Manual', 'admin', '2024-03-15'),
    (2, '2O2Fr$t4X7Zf8NOew3FNr2', 'Photo', 'AHU-01_installed.jpg',
     '/documents/photos/AHU-01_20240315.jpg', 512, 'image/jpeg',
     'After installation photo', 'tech_john', '2024-03-15'),
    (3, '2O2Fr$t4X7Zf8NOew3FNr2', 'Warranty', 'Trane_Warranty_2024.pdf',
     '/documents/warranties/AHU-01_warranty.pdf', 128, 'application/pdf',
     '1-year parts and labor warranty', 'admin', '2024-03-15');
```

---

### Table: `asset_history`
**Purpose:** Audit trail of changes

```sql
CREATE TABLE asset_history (
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

CREATE INDEX idx_asset_history_guid ON asset_history(asset_guid);
CREATE INDEX idx_asset_history_date ON asset_history(changed_date);
```

**Example Data:**
```sql
INSERT INTO asset_history VALUES
    (1, '2O2Fr$t4X7Zf8NOew3FNr2', 'Created', NULL, NULL, NULL,
     'admin', '2024-03-15 10:30:00', 'Asset imported from IFC model'),
    (2, '2O2Fr$t4X7Zf8NOew3FNr2', 'Updated', 'condition', 'Excellent', 'Good',
     'tech_john', '2024-09-15 14:20:00', 'Routine inspection - minor wear on bearings'),
    (3, '2O2Fr$t4X7Zf8NOew3FNr2', 'StatusChange', 'status', 'Active', 'Active',
     'operator_jane', '2025-11-30 08:00:00', 'High temperature alert triggered');
```

---

## MAINTENANCE LAYER

### Table: `pm_templates`
**Purpose:** Preventive maintenance task definitions

```sql
CREATE TABLE pm_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL UNIQUE,
    ifc_class TEXT,                   -- Apply to all of this type
    discipline TEXT,
    description TEXT,
    interval_type TEXT NOT NULL,      -- Daily, Weekly, Monthly, Quarterly, Annually
    interval_value INTEGER DEFAULT 1, -- Every X intervals
    estimated_hours REAL,             -- Estimated time to complete
    required_skills TEXT,             -- Comma-separated skills needed
    tasks TEXT NOT NULL,              -- JSON array or checklist
    parts_list TEXT,                  -- JSON array of typical parts
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

CREATE INDEX idx_pm_templates_class ON pm_templates(ifc_class);
```

**Example Data:**
```sql
INSERT INTO pm_templates VALUES (
    1,
    'AHU Filter Replacement',
    'IfcAirHandlingUnit',
    'ACMV',
    'Replace air filters and inspect coils',
    'Quarterly',
    1,
    2.5,
    'HVAC Tech Level 2',
    '["Check filter condition", "Remove old filters", "Install new MERV 13 filters", "Inspect coils for dirt/damage", "Check belt tension", "Verify airflow"]',
    '[{"part": "MERV 13 Filter 24x24x4", "qty": 4}, {"part": "Coil cleaner", "qty": 1}]',
    '2024-01-01',
    1
);
```

---

### Table: `work_orders`
**Purpose:** Maintenance tasks (PM and corrective)

```sql
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_number TEXT UNIQUE NOT NULL,
    asset_guid TEXT NOT NULL,

    -- Type and Priority
    work_type TEXT NOT NULL,          -- PM, Corrective, Emergency, Inspection
    priority TEXT DEFAULT 'Medium',   -- Low, Medium, High, Critical

    -- Description
    title TEXT NOT NULL,
    description TEXT,
    pm_template_id INTEGER,           -- If generated from PM template

    -- Scheduling
    scheduled_date DATE,
    due_date DATE,
    estimated_hours REAL,

    -- Assignment
    assigned_to TEXT,                 -- Technician ID/name
    team TEXT,                        -- HVAC, Electrical, Plumbing, etc.

    -- Status
    status TEXT DEFAULT 'Open',       -- Open, InProgress, Completed, Deferred, Cancelled
    completion_date DATE,
    actual_hours REAL,

    -- Costs
    labor_cost REAL,
    parts_cost REAL,
    total_cost REAL,

    -- Metadata
    created_by TEXT,
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_date TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE,
    FOREIGN KEY (pm_template_id) REFERENCES pm_templates(id)
);

CREATE INDEX idx_wo_asset ON work_orders(asset_guid);
CREATE INDEX idx_wo_status ON work_orders(status);
CREATE INDEX idx_wo_due_date ON work_orders(due_date);
CREATE INDEX idx_wo_assigned ON work_orders(assigned_to);
```

**Example Data:**
```sql
INSERT INTO work_orders VALUES (
    1,
    'WO-2025-001234',
    '2O2Fr$t4X7Zf8NOew3FNr2',
    'PM',
    'Medium',
    'Quarterly Filter Replacement - AHU-01',
    'Replace air filters and inspect coils as per PM schedule',
    1,                                -- pm_template_id
    '2025-12-15',                     -- scheduled_date
    '2025-12-15',                     -- due_date
    2.5,                              -- estimated_hours
    'tech_john',                      -- assigned_to
    'HVAC',                           -- team
    'Open',                           -- status
    NULL,                             -- completion_date
    NULL,                             -- actual_hours
    NULL,                             -- labor_cost
    NULL,                             -- parts_cost
    NULL,                             -- total_cost
    'system',                         -- created_by (auto-generated)
    '2025-11-30 00:00:00',
    '2025-11-30 00:00:00'
);
```

---

### Table: `maintenance_log`
**Purpose:** Completed maintenance history

```sql
CREATE TABLE maintenance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL,
    asset_guid TEXT NOT NULL,

    -- What was done
    work_performed TEXT NOT NULL,
    findings TEXT,                    -- Issues found during work
    corrective_actions TEXT,          -- Actions taken

    -- Parts used
    parts_used TEXT,                  -- JSON array

    -- Time and Labor
    technician TEXT NOT NULL,
    work_date DATE NOT NULL,
    hours_worked REAL,

    -- Follow-up
    follow_up_required BOOLEAN DEFAULT 0,
    follow_up_notes TEXT,

    -- Metadata
    logged_by TEXT,
    logged_date TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (work_order_id) REFERENCES work_orders(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
);

CREATE INDEX idx_maint_log_asset ON maintenance_log(asset_guid);
CREATE INDEX idx_maint_log_date ON maintenance_log(work_date);
```

**Example Data:**
```sql
INSERT INTO maintenance_log VALUES (
    1,
    1,                                -- work_order_id
    '2O2Fr$t4X7Zf8NOew3FNr2',
    'Replaced all 4 air filters with MERV 13. Inspected coils - found minor dirt buildup. Cleaned coils with approved cleaner. Checked belt tension - OK.',
    'Filters were 80% clogged. Coils had light dust accumulation.',
    'Installed new filters. Cleaned coils. Verified airflow restored to normal (13,800 CFM measured vs 14,000 CFM design).',
    '[{"part": "MERV 13 Filter 24x24x4", "qty": 4, "cost": 240.00}, {"part": "Coil cleaner", "qty": 1, "cost": 25.00}]',
    'tech_john',
    '2025-12-15',
    2.25,                             -- actual hours
    0,                                -- no follow-up needed
    NULL,
    'tech_john',
    '2025-12-15 16:30:00'
);
```

---

### Table: `technicians`
**Purpose:** Maintenance team roster

```sql
CREATE TABLE technicians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    skills TEXT,                      -- JSON array: ["HVAC", "Electrical", "Plumbing"]
    certifications TEXT,              -- JSON array
    is_active BOOLEAN DEFAULT 1,
    created_date TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_technicians_active ON technicians(is_active);
```

**Example Data:**
```sql
INSERT INTO technicians VALUES
    (1, 'TECH001', 'John Smith', 'john.smith@facility.com', '+1-555-0123',
     '["HVAC Level 2", "Refrigeration", "BMS"]',
     '["EPA 608 Universal", "NATE Certified"]', 1, '2024-01-01'),
    (2, 'TECH002', 'Jane Doe', 'jane.doe@facility.com', '+1-555-0124',
     '["Electrical", "Fire Alarm", "Emergency Lighting"]',
     '["Master Electrician", "NICET Level II"]', 1, '2024-01-01');
```

---

## IoT LAYER

### Table: `sensors`
**Purpose:** Sensor registry and IFC mapping

```sql
CREATE TABLE sensors (
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

CREATE INDEX idx_sensors_asset ON sensors(asset_guid);
CREATE INDEX idx_sensors_type ON sensors(sensor_type);
CREATE INDEX idx_sensors_active ON sensors(is_active);
```

**Example Data:**
```sql
INSERT INTO sensors VALUES (
    1,
    'TEMP-AHU01-SUPPLY',
    '2O2Fr$t4X7Zf8NOew3FNr2',
    'Temperature',
    '°C',
    'MQTT',
    'building/level3/ahu01/supply_temp',
    30,                               -- update every 30 seconds
    1,                                -- active
    '2025-11-30 14:35:00',
    22.5,                             -- last reading
    10.0,                             -- min_threshold
    25.0,                             -- max_threshold
    5.0,                              -- critical_min
    30.0,                             -- critical_max
    'Supply air temperature sensor - AHU-01 discharge',
    '2024-03-15',
    '2025-03-15',
    '2024-03-15 10:30:00'
);
```

---

### Time-Series: `sensor_readings` (InfluxDB)
**Purpose:** High-frequency sensor data

**InfluxDB Schema:**
```
measurement: sensor_readings
tags:
  - sensor_id
  - sensor_type
  - asset_guid
  - location

fields:
  - value (float)
  - quality (string) - "good", "uncertain", "bad"

timestamp: nanosecond precision
```

**Example Query (InfluxQL):**
```sql
-- Get last 1 hour of temperature readings for AHU-01
SELECT value
FROM sensor_readings
WHERE sensor_id = 'TEMP-AHU01-SUPPLY'
  AND time > now() - 1h

-- Get average hourly temperature for past 7 days
SELECT MEAN(value)
FROM sensor_readings
WHERE sensor_id = 'TEMP-AHU01-SUPPLY'
  AND time > now() - 7d
GROUP BY time(1h)
```

---

### Table: `alert_rules`
**Purpose:** Configure alert conditions

```sql
CREATE TABLE alert_rules (
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

CREATE INDEX idx_alert_rules_sensor ON alert_rules(sensor_id);
CREATE INDEX idx_alert_rules_type ON alert_rules(sensor_type);
```

**Example Data:**
```sql
INSERT INTO alert_rules VALUES (
    1,
    'AHU Supply Temp - High',
    'TEMP-AHU01-SUPPLY',
    'Temperature',
    'Above',
    25.0,                             -- threshold_value
    NULL,                             -- threshold_min
    NULL,                             -- threshold_max
    300,                              -- 5 minutes duration
    'Warning',
    'operator@facility.com',
    NULL,
    0,                                -- don't auto-create WO
    1,
    '2024-03-15'
);
```

---

### Table: `alerts`
**Purpose:** Active and historical alerts

```sql
CREATE TABLE alerts (
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

CREATE INDEX idx_alerts_sensor ON alerts(sensor_id);
CREATE INDEX idx_alerts_asset ON alerts(asset_guid);
CREATE INDEX idx_alerts_triggered ON alerts(triggered_date);
CREATE INDEX idx_alerts_unresolved ON alerts(resolved_date) WHERE resolved_date IS NULL;
```

**Example Data:**
```sql
INSERT INTO alerts VALUES (
    1,
    1,                                -- alert_rule_id
    'TEMP-AHU01-SUPPLY',
    '2O2Fr$t4X7Zf8NOew3FNr2',
    'Warning',
    'Supply air temperature exceeds 25°C threshold',
    27.3,                             -- trigger_value
    '2025-11-30 14:23:00',            -- triggered
    '2025-11-30 14:30:00',            -- acknowledged
    'operator_jane',
    NULL,                             -- not resolved yet
    NULL,
    NULL,                             -- no WO yet
    'Investigating root cause - ambient temp spike'
);
```

---

## Migration Scripts

### Initial Setup
```sql
-- Run in order:
-- 1. Create tables (asset layer)
-- 2. Create tables (maintenance layer)
-- 3. Create tables (IoT layer)
-- 4. Create indexes
-- 5. Insert sample data (optional)

-- Example migration:
BEGIN TRANSACTION;

-- Asset layer
-- (paste CREATE TABLE statements above)

-- Maintenance layer
-- (paste CREATE TABLE statements above)

-- IoT layer
-- (paste CREATE TABLE statements above)

COMMIT;
```

### Data Import from IFC
```python
# Import assets from IFC model
import ifcopenshell
import sqlite3

ifc_file = ifcopenshell.open('Terminal1.ifc')
conn = sqlite3.connect('digital_twin.db')

for element in ifc_file.by_type('IfcDistributionElement'):
    guid = element.GlobalId
    name = element.Name or ''
    ifc_class = element.is_a()

    # Extract properties
    for rel in element.IsDefinedBy:
        if rel.is_a('IfcRelDefinesByProperties'):
            pset = rel.RelatingPropertyDefinition
            # ... extract manufacturer, model, etc.

    # Insert into database
    conn.execute("""
        INSERT INTO assets (guid, name, ifc_class, discipline)
        VALUES (?, ?, ?, ?)
    """, (guid, name, ifc_class, 'ACMV'))  # Determine discipline logic

conn.commit()
```

---

## Backup and Maintenance

### Automated Backups
```bash
#!/bin/bash
# daily_backup.sh

DB_FILE="/path/to/digital_twin.db"
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d)

# SQLite backup
sqlite3 $DB_FILE ".backup ${BACKUP_DIR}/digital_twin_${DATE}.db"

# InfluxDB backup
influxd backup -portable ${BACKUP_DIR}/influxdb_${DATE}

# Keep last 30 days
find ${BACKUP_DIR} -name "digital_twin_*.db" -mtime +30 -delete
```

### Data Retention
```sql
-- Delete old sensor readings (keep 5 years)
-- Run via InfluxDB retention policy:
CREATE RETENTION POLICY "five_years" ON "building_iot" DURATION 1825d REPLICATION 1 DEFAULT

-- Archive old work orders (move to archive table)
INSERT INTO work_orders_archive SELECT * FROM work_orders WHERE completion_date < DATE('now', '-2 years');
DELETE FROM work_orders WHERE completion_date < DATE('now', '-2 years');
```

---

**Status:** Schema Complete
**Next Steps:** Implement Python data access layer (DAL)
**See:** API_DESIGN.md for endpoint specifications
