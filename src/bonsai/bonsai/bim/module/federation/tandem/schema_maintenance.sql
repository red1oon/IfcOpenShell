-- Digital Twin - Maintenance Layer Database Schema
-- Phase 2: Preventive Maintenance & Work Order Management
-- Version: 1.0

-- =============================================================================
-- MAINTENANCE LAYER
-- =============================================================================

CREATE TABLE IF NOT EXISTS pm_templates (
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

CREATE INDEX IF NOT EXISTS idx_pm_templates_class ON pm_templates(ifc_class);
CREATE INDEX IF NOT EXISTS idx_pm_templates_discipline ON pm_templates(discipline);
CREATE INDEX IF NOT EXISTS idx_pm_templates_active ON pm_templates(is_active);

-- =============================================================================

CREATE TABLE IF NOT EXISTS work_orders (
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

CREATE INDEX IF NOT EXISTS idx_wo_asset ON work_orders(asset_guid);
CREATE INDEX IF NOT EXISTS idx_wo_status ON work_orders(status);
CREATE INDEX IF NOT EXISTS idx_wo_due_date ON work_orders(due_date);
CREATE INDEX IF NOT EXISTS idx_wo_assigned ON work_orders(assigned_to);
CREATE INDEX IF NOT EXISTS idx_wo_type ON work_orders(work_type);
CREATE INDEX IF NOT EXISTS idx_wo_priority ON work_orders(priority);

-- =============================================================================

CREATE TABLE IF NOT EXISTS maintenance_log (
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
    skills TEXT,                      -- JSON array: ["HVAC", "Electrical", "Plumbing"]
    certifications TEXT,              -- JSON array
    is_active BOOLEAN DEFAULT 1,
    created_date TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_technicians_active ON technicians(is_active);
CREATE INDEX IF NOT EXISTS idx_technicians_employee_id ON technicians(employee_id);

-- =============================================================================

-- Table for tracking PM schedule state
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
