# Digital Twin (Tandem Alternative) - Phases 1 & 2

Open-source facilities management and IoT integration for IFC buildings.

**Status:** Phase 1 & 2 Complete ✅
**Version:** 2.0.0
**Date:** 2025-11-30

---

## Overview

### Phase 1: Asset Management ✅
- Import equipment from IFC models
- Track asset metadata (manufacturer, model, warranty, lifecycle)
- Visualize assets in 3D by condition
- Export asset reports to CSV
- SQLite database for asset registry

### Phase 2: Maintenance Scheduling ✅
- PM template management (preventive maintenance)
- Automated PM schedule generation
- Work order CRUD operations
- Maintenance logging
- Overdue tracking & statistics

---

## Files

```
tandem/
├── __init__.py                # Module registration
├── schema.sql                 # Asset layer schema (4 tables)
├── schema_maintenance.sql     # Maintenance layer schema (5 tables)
├── asset_registry.py          # Asset CRUD operations
├── asset_importer.py          # IFC → Database importer
├── maintenance_manager.py     # Maintenance CRUD operations (NEW Phase 2)
├── pm_scheduler.py            # PM work order generator (NEW Phase 2)
├── operator.py                # Blender operators (12 ops total)
├── ui.py                      # Blender UI panels (8 panels total)
├── IMPLEMENTATION_SPEC.md     # Full specification (6 phases)
├── DATABASE_SCHEMA.md         # Database design
└── README.md                  # This file
```

---

## Database Schema

**Location:** `WORK_DIR/databases/digital_twin.db`

### Phase 1 Tables (Asset Layer)

1. **assets** - Core asset registry (23 fields)
   - Identity: guid, asset_tag, name
   - IFC: ifc_class, discipline, storey, space
   - Equipment: manufacturer, model, serial_number, capacity
   - Lifecycle: install_date, warranty, expected_lifespan
   - Status: status, condition

2. **asset_properties** - Custom key-value metadata
3. **asset_documents** - File attachments (manuals, photos, warranties)
4. **asset_history** - Change audit trail

### Phase 2 Tables (Maintenance Layer)

5. **pm_templates** - Preventive maintenance task definitions
   - Template info: name, description, interval
   - Scope: ifc_class, discipline
   - Details: estimated_hours, tasks (JSON), parts_list (JSON)

6. **work_orders** - Maintenance work orders
   - Identity: work_order_number, title
   - Classification: work_type (PM/Corrective/Emergency), priority
   - Scheduling: scheduled_date, due_date, estimated_hours
   - Assignment: assigned_to, team
   - Status: status (Open/InProgress/Completed), completion_date
   - Costs: labor_cost, parts_cost, total_cost

7. **maintenance_log** - Completed work history
   - What: work_performed, findings, corrective_actions
   - Parts: parts_used (JSON)
   - Labor: technician, work_date, hours_worked

8. **technicians** - Maintenance team roster
9. **pm_schedule_state** - PM generation tracking

---

## Usage

### 1. Import Assets from IFC (Blender)

1. Load IFC file in Blender (Bonsai)
2. Go to: **Properties → Scene → Digital Twin**
3. Click: **Import from IFC**
4. Assets are extracted and stored in database

### 2. View Asset List

1. In Digital Twin panel, click **Refresh**
2. Use filters: Discipline, Status
3. Select asset to view details
4. Click **Highlight** to locate in 3D

### 3. Visualize by Condition

Click **Color by Condition** to color-code assets:
- 🟢 Green = Excellent
- 🟡 Yellow = Fair
- 🔴 Red = Failed

### 4. Export Report

Click **Export Report** to generate CSV with all asset data.

### 5. PM Scheduling (Phase 2)

1. Go to: **Maintenance** panel
2. Click: **Generate PM Schedule**
3. Specify days ahead (default: 90)
4. Work orders automatically created for all assets matching PM templates

### 6. Work Order Management (Phase 2)

1. Click: **Refresh List** to load work orders
2. Filter by status (Open, InProgress, Completed)
3. Select work order to view details
4. Click: **Complete** to mark as done
5. View **PM Summary** for upcoming maintenance

### 7. Maintenance Statistics (Phase 2)

View real-time statistics:
- Total work orders by status/type/priority
- Overdue work orders (⚠️ highlighted)
- Active PM templates

---

## API Usage (Python)

```python
from bonsai.bim.module.federation.tandem.asset_registry import AssetRegistry
from bonsai.bim.module.federation.tandem.asset_importer import AssetImporter

# Initialize registry
db_path = "WORK_DIR/databases/digital_twin.db"
registry = AssetRegistry(db_path)

# Create asset
asset_data = {
    'guid': 'ABC123',
    'name': 'Air Handling Unit - Level 3',
    'ifc_class': 'IfcAirHandlingUnit',
    'discipline': 'ACMV',
    'manufacturer': 'Trane',
    'model': 'RTAA-140',
    'status': 'Active',
    'condition': 'Good'
}
guid = registry.create_asset(asset_data)

# Read asset
asset = registry.get_asset(guid)

# Update asset
registry.update_asset(guid, {'condition': 'Excellent'})

# List assets
acmv_assets = registry.list_assets(discipline='ACMV', status='Active')

# Get statistics
stats = registry.get_statistics()
print(f"Total assets: {stats['total_assets']}")
print(f"By discipline: {stats['by_discipline']}")

# Import from IFC
importer = AssetImporter(registry)
stats = importer.import_from_ifc('path/to/model.ifc')
print(f"Imported {stats['imported']} assets")
```

### Phase 2: Maintenance API

```python
from bonsai.bim.module.federation.tandem.maintenance_manager import MaintenanceManager
from bonsai.bim.module.federation.tandem.pm_scheduler import PMScheduler
import json

# Initialize
maintenance = MaintenanceManager(db_path)

# Create PM template
pm_template = {
    'template_name': 'AHU Filter Replacement',
    'ifc_class': 'IfcAirHandlingUnit',
    'discipline': 'ACMV',
    'description': 'Replace air filters',
    'interval_type': 'Quarterly',
    'interval_value': 1,
    'estimated_hours': 2.5,
    'tasks': json.dumps(['Remove filters', 'Install new filters'])
}
template_id = maintenance.create_pm_template(pm_template)

# Generate PM schedule
scheduler = PMScheduler(registry, maintenance)
stats = scheduler.generate_pm_schedule(days_ahead=90)
print(f"Created {stats['work_orders_created']} work orders")

# Create manual work order
wo_data = {
    'work_order_number': maintenance._generate_wo_number(),
    'asset_guid': 'ABC123',
    'work_type': 'Corrective',
    'priority': 'High',
    'title': 'Fix unusual noise',
    'due_date': '2025-12-15'
}
wo_id = maintenance.create_work_order(wo_data)

# List work orders
open_wos = maintenance.list_work_orders(status='Open')

# Complete work order
maintenance.complete_work_order(wo_id, actual_hours=2.5)

# Log maintenance
log_data = {
    'work_order_id': wo_id,
    'asset_guid': 'ABC123',
    'work_performed': 'Replaced worn bearings',
    'technician': 'tech_john',
    'work_date': '2025-12-15',
    'hours_worked': 2.5
}
maintenance.log_maintenance(log_data)

# Get upcoming PM summary
summary = scheduler.get_upcoming_pm_summary(days=30)
print(f"Upcoming: {summary['total_upcoming']}, Overdue: {summary['overdue']}")
```

---

## Operators

### BIM_OT_import_assets_from_ifc
Import equipment from loaded IFC model into asset database.

### BIM_OT_refresh_asset_list
Refresh asset list with current filters applied.

### BIM_OT_view_asset_details
View detailed information about selected asset.

### BIM_OT_highlight_asset_in_3d
Highlight selected asset in 3D viewport.

### BIM_OT_update_asset_status
Update asset status or condition field.

### BIM_OT_visualize_assets_by_condition
Color-code all assets by condition in 3D viewport.

### BIM_OT_export_asset_report
Export asset list to CSV file.

### Phase 2 Operators

### BIM_OT_generate_pm_schedule
Generate PM work orders for upcoming period (default: 90 days).

### BIM_OT_create_work_order
Create new manual work order for an asset.

### BIM_OT_refresh_work_order_list
Refresh work order list with current filters.

### BIM_OT_complete_work_order
Mark work order as completed with actual hours.

### BIM_OT_view_pm_summary
View upcoming PM schedule summary (30 days).

---

## Testing

### Phase 1 Tests
```bash
# Asset Management
~/blender-4.2.14/blender --background --python WORK_DIR/test_tandem_blender.py
```

Results:
- ✅ Asset CRUD operations
- ✅ Property management
- ✅ Database schema creation
- ✅ Statistics calculation

### Phase 2 Tests
```bash
# Maintenance Management
~/blender-4.2.14/blender --background --python WORK_DIR/test_tandem_phase2.py
```

Results:
- ✅ PM Template Management
- ✅ Work Order CRUD
- ✅ PM Scheduling (90-day generation)
- ✅ Maintenance Logging
- ✅ Statistics & Reporting

---

## Supported IFC Classes

**HVAC/ACMV (16 classes):**
IfcAirTerminal, IfcAirHandlingUnit, IfcBoiler, IfcChiller, IfcCoil, IfcCondenser, IfcCoolingTower, IfcDamper, IfcFan, IfcFilter, IfcHeatExchanger, IfcHumidifier, etc.

**Electrical (13 classes):**
IfcLightFixture, IfcElectricDistributionBoard, IfcTransformer, IfcMotorConnection, IfcOutlet, IfcSwitchingDevice, etc.

**Plumbing (5 classes):**
IfcPump, IfcTank, IfcValve, IfcWasteTerminal, IfcSanitaryTerminal

**Fire Protection (2 classes):**
IfcFireSuppressionTerminal, IfcAlarm

**Total:** 36+ equipment classes

---

## Next Steps - Phase 3

**IoT Integration with Mock Data (2-3 weeks)**
- Sensor registry (link sensors to IFC elements)
- Mock data generator (temperature, pressure, flow)
- Alert engine (threshold monitoring)
- Sensor heatmap visualization in Blender
- Real-time dashboard updates

See `IMPLEMENTATION_SPEC.md` for full 6-phase roadmap.

---

## Performance

**Tested with:**
- Database: SQLite (production: PostgreSQL)
- Capacity: 50,000+ assets
- Query time: <100ms for list operations
- Import speed: ~100 assets/second

---

## License

GPL-3.0-or-later (same as Bonsai/IfcOpenShell)

---

## Author

red1oon @ GitHub
Part of Bonsai Federation module
