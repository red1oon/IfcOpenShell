-- Digital Twin - Asset Management Database Schema
-- Phase 1: Asset Layer
-- Version: 1.0

-- =============================================================================
-- ASSET LAYER
-- =============================================================================

CREATE TABLE IF NOT EXISTS assets (
    -- Identity
    guid TEXT PRIMARY KEY,              -- IFC GUID (from IFC model)
    asset_tag TEXT UNIQUE,              -- Facility barcode/QR code
    name TEXT NOT NULL,                 -- Human-readable name

    -- IFC Properties
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
    updated_date TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_assets_ifc_class ON assets(ifc_class);
CREATE INDEX IF NOT EXISTS idx_assets_discipline ON assets(discipline);
CREATE INDEX IF NOT EXISTS idx_assets_storey ON assets(storey);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_warranty_end ON assets(warranty_start, warranty_duration_months);

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
