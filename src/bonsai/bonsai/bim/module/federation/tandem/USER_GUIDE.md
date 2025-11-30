# Digital Twin User Guide
## Facilities Management for IFC Buildings

**Version:** 2.0 (Phases 1-3 Complete)
**Last Updated:** 2025-11-30

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Asset Management](#asset-management)
4. [Maintenance Scheduling](#maintenance-scheduling)
5. [IoT Monitoring](#iot-monitoring)
6. [Common Workflows](#common-workflows)
7. [Troubleshooting](#troubleshooting)

---

## Introduction

### What is Digital Twin?

Digital Twin is an open-source facilities management system integrated with Blender/Bonsai. It provides:

- **Asset Management (6D)** - Track equipment, warranties, and lifecycle
- **Maintenance Scheduling (6D)** - Preventive maintenance and work orders
- **IoT Integration (7D)** - Sensor monitoring and alerts

### Who is it for?

- **Facility Managers** - Building operations oversight
- **Maintenance Teams** - Work order management
- **Building Operators** - Daily monitoring and alerts
- **Asset Managers** - Lifecycle and cost tracking

### Why Digital Twin?

**vs. Commercial Alternatives (Autodesk Tandem):**
- ✅ Free & Open Source (GPL-3.0)
- ✅ No subscription fees ($360-$720/year saved per user)
- ✅ Full IFC integration
- ✅ Customizable for your needs
- ✅ Works offline

---

## Getting Started

### System Requirements

- **Blender:** 4.2+ with Bonsai add-on installed
- **Database:** SQLite (included) or PostgreSQL (optional)
- **Python:** 3.11+ (included with Blender)

### Installation

Digital Twin is included with Bonsai. No additional installation needed.

### First Launch

1. Open Blender with Bonsai
2. Load your IFC model (File → Import → IFC)
3. Navigate to: **Properties → Scene → Digital Twin**
4. You should see the Digital Twin panel

### Database Setup

**Default Location:** `~/Projects/IfcOpenShell/WORK_DIR/databases/digital_twin.db`

The database is created automatically on first use. You can specify a custom location in the panel.

---

## Asset Management

### Importing Assets from IFC

**Goal:** Extract all equipment from your IFC model into the asset database.

**Steps:**

1. **Load IFC Model**
   - File → Import → IFC
   - Select your building model (e.g., `Terminal_1.ifc`)

2. **Open Digital Twin Panel**
   - Properties → Scene → Digital Twin

3. **Import Assets**
   - Click: **Import from IFC**
   - Wait for import to complete (progress shown in console)
   - Success message will show number of assets imported

**What gets imported?**
- All MEP equipment (HVAC, Electrical, Plumbing, Fire Protection)
- 36+ IFC classes supported (see README.md for full list)
- Automatically extracts: name, type, manufacturer, model, location

**Example Results:**
```
Import complete: 1,247 assets imported
  ACMV: 542 assets
  ELEC: 312 assets
  FP: 195 assets
  PLB: 198 assets
```

### Viewing Asset List

**Steps:**

1. Click: **Refresh** (in Assets panel)
2. Use filters:
   - **Discipline:** ACMV, ELEC, FP, PLB, Other
   - **Status:** Active, Inactive, Decommissioned
3. Assets appear in list with:
   - ✓ Condition indicator (Green = Good, Yellow = Fair, Red = Failed)
   - Asset name
   - Discipline

### Viewing Asset Details

**Steps:**

1. Select asset from list
2. Click: **Details**
3. View information:
   - GUID (unique identifier)
   - Manufacturer & Model
   - Status & Condition
   - Custom properties

### Finding Asset in 3D Model

**Steps:**

1. Select asset from list
2. Click: **Highlight in 3D**
3. Blender will:
   - Select the object
   - Frame it in the viewport
   - Make it active

### Updating Asset Status

**Example:** Mark equipment as "Fair" condition after inspection

**Steps:**

1. Select asset from list
2. Click: **Details**
3. Scroll to "Update Status" section
4. Click condition button: **Excellent** | **Good** | **Fair** | **Poor** | **Failed**
5. Asset is updated immediately

### Color-Coding Assets by Condition

**Goal:** Visualize all equipment condition in 3D

**Steps:**

1. Click: **Color by Condition** (in Visualization section)
2. All assets color-coded:
   - 🟢 Green = Excellent/Good
   - 🟡 Yellow = Fair
   - 🔴 Red = Poor/Failed
   - ⚫ Gray = Unknown
3. Blender viewport automatically switches to Object Color mode

### Exporting Asset Report

**Steps:**

1. Click: **Export Report**
2. Choose save location (default: `WORK_DIR/asset_report.csv`)
3. Open in Excel/LibreOffice for analysis

**CSV Contains:**
- All asset fields (GUID, name, manufacturer, model, etc.)
- Status and condition
- Lifecycle data (warranty, install date)
- Location (storey, space)

---

## Maintenance Scheduling

### Creating PM Templates

**Goal:** Define recurring maintenance tasks for equipment types

**Example:** Quarterly filter replacement for all Air Handling Units

**Via Python/Script:**
```python
from bonsai.bim.module.federation.tandem.maintenance_manager import MaintenanceManager
import json

maintenance = MaintenanceManager("path/to/digital_twin.db")

pm_template = {
    'template_name': 'AHU Filter Replacement',
    'ifc_class': 'IfcAirHandlingUnit',  # Apply to all AHUs
    'discipline': 'ACMV',
    'description': 'Replace air filters and inspect coils',
    'interval_type': 'Quarterly',  # Daily, Weekly, Monthly, Quarterly, Annually
    'interval_value': 1,  # Every 1 quarter
    'estimated_hours': 2.5,
    'required_skills': 'HVAC Level 2',
    'tasks': json.dumps([
        'Check filter condition',
        'Remove old filters',
        'Install new MERV 13 filters',
        'Inspect coils for dirt/damage',
        'Check belt tension',
        'Verify airflow'
    ]),
    'parts_list': json.dumps([
        {'part': 'MERV 13 Filter 24x24x4', 'qty': 4, 'unit_cost': 60.00},
        {'part': 'Coil cleaner', 'qty': 1, 'unit_cost': 25.00}
    ])
}

template_id = maintenance.create_pm_template(pm_template)
print(f"Created template ID: {template_id}")
```

### Generating PM Schedule

**Goal:** Auto-create work orders for next 90 days based on PM templates

**Steps:**

1. Go to: **Maintenance** panel
2. Click: **Generate PM Schedule**
3. Dialog appears - set **Days Ahead:** 90 (default)
4. Click: **OK**
5. System processes:
   - Finds all PM templates
   - Matches templates to assets by IFC class/discipline
   - Calculates due dates based on intervals
   - Creates work orders for upcoming period
6. Success message shows work orders created

**Example Output:**
```
PM Schedule generated: 24 work orders created, 8 skipped
  Templates processed: 3
  Assets scanned: 542
```

### Viewing Work Orders

**Steps:**

1. Go to: **Maintenance → Work Orders** panel
2. Click: **Refresh List**
3. Filter by status:
   - All
   - Open
   - InProgress
   - Completed
4. Work orders appear with:
   - Priority indicator (🔴 Critical, 🟡 High, ⚪ Medium, ⚫ Low)
   - Type icon (⏰ PM, 🔧 Corrective, 🚨 Emergency)
   - WO Number
   - Title
   - Status checkmark

### Creating Manual Work Order

**Example:** Equipment reported making unusual noise

**Via Python/Script:**
```python
from bonsai.bim.module.federation.tandem.maintenance_manager import MaintenanceManager
from datetime import datetime, timedelta

maintenance = MaintenanceManager("path/to/digital_twin.db")

wo_data = {
    'work_order_number': maintenance._generate_wo_number(),  # Auto-generates
    'asset_guid': 'ABC123',  # Get from asset list
    'work_type': 'Corrective',
    'priority': 'High',
    'title': 'Investigate unusual noise in AHU-01',
    'description': 'Operator reported rattling noise during operation',
    'due_date': (datetime.now() + timedelta(days=2)).date().isoformat(),
    'assigned_to': 'tech_john',
    'team': 'HVAC',
    'created_by': 'operator_jane',
}

wo_id = maintenance.create_work_order(wo_data)
print(f"Work order {wo_data['work_order_number']} created")
```

### Completing Work Order

**Steps:**

1. Select work order from list
2. Work order details appear below
3. Click: **Complete**
4. Dialog appears - enter **Actual Hours:** (e.g., 2.5)
5. Click: **OK**
6. Work order status changes to "Completed"

### Viewing PM Summary

**Goal:** See upcoming maintenance for next 30 days

**Steps:**

1. Click: **Summary** (in Maintenance panel)
2. Console shows:
   - Total upcoming PM work
   - Overdue count
   - Due this week / next week
   - Breakdown by discipline

**Example Output:**
```
=== PM Schedule Summary (Next 30 Days) ===
Total upcoming: 12
Overdue: 2
Due this week: 4
Due next week: 3

By Discipline:
  ACMV: 8
  ELEC: 3
  FP: 1
```

### Maintenance Statistics

**View in UI:**

1. Go to: **Maintenance → Statistics** panel
2. See real-time counts:
   - Total work orders
   - By status (Open, InProgress, Completed)
   - By type (PM, Corrective, Emergency)
   - ⚠️ Overdue work orders (highlighted in red)
   - Active PM templates

---

## IoT Monitoring

### Creating Sensors for Assets

**Goal:** Link IoT sensors to equipment for monitoring

**Via Python/Script:**
```python
from bonsai.bim.module.federation.tandem.sensor_registry import SensorRegistry

sensor_registry = SensorRegistry("path/to/digital_twin.db")

# Create temperature sensor for AHU
sensor_data = {
    'sensor_id': 'TEMP-AHU01-SUPPLY',
    'asset_guid': 'ABC123',  # AHU GUID
    'sensor_type': 'Temperature',
    'measurement_unit': '°C',
    'protocol': 'MQTT',
    'topic': 'building/level3/ahu01/supply_temp',
    'update_interval_seconds': 60,
    'min_threshold': 10.0,  # Alert if below
    'max_threshold': 25.0,  # Alert if above
    'critical_max': 30.0,   # Critical alert
    'location_description': 'Supply air temperature - AHU-01'
}

sensor_id = sensor_registry.create_sensor(sensor_data)
print(f"Created sensor: {sensor_data['sensor_id']}")
```

### Auto-Creating Mock Sensors

**Goal:** Test system with simulated data

**Via Python/Script:**
```python
from bonsai.bim.module.federation.tandem.mock_data_generator import MockDataGenerator

generator = MockDataGenerator(sensor_registry)

# Auto-create sensors based on asset type
asset = asset_registry.get_asset('AHU-01-GUID')
created_sensors = generator.create_mock_sensors_for_asset(asset)

# Result: 4 sensors created for AHU
# - Supply temperature
# - Return temperature
# - Static pressure
# - Airflow

print(f"Created {len(created_sensors)} sensors")
```

**Supported Sensor Types:**
- Temperature (°C)
- Pressure (bar)
- Flow (m³/h)
- Humidity (%)
- CO2 (ppm)
- Power (kW)

### Generating Mock Data

**Goal:** Populate system with 24 hours of realistic sensor readings

**Via Python/Script:**
```python
# Generate historical data
stats = generator.generate_batch(
    hours=24,              # 24 hours of history
    interval_minutes=5,    # Reading every 5 minutes
    anomaly_probability=0.05  # 5% chance of anomalies
)

print(f"Generated {stats['readings_generated']} readings")
# Result: 288 readings per sensor (24h × 12 readings/hour)
```

**Data Characteristics:**
- Realistic variation around baseline
- Gradual drift back to normal
- Occasional anomalies (triggers alerts)
- Continuous from last value (smooth trends)

### Monitoring for Alerts

**Goal:** Check all sensors and create alerts for threshold violations

**Via Python/Script:**
```python
from bonsai.bim.module.federation.tandem.alert_engine import AlertEngine

alert_engine = AlertEngine(sensor_registry)

# Check all sensors
stats = alert_engine.check_all_sensors()

print(f"Checked {stats['sensors_checked']} sensors")
print(f"Created {stats['alerts_created']} alerts")
print(f"By severity: {stats['by_severity']}")
```

**Alert Triggers:**
- Value > `max_threshold` → Warning
- Value < `min_threshold` → Warning
- Value > `critical_max` → Critical
- Value < `critical_min` → Critical

### Viewing Active Alerts

**Via Python/Script:**
```python
# Get all unresolved alerts
active_alerts = sensor_registry.get_active_alerts()

for alert in active_alerts:
    print(f"[{alert['severity']}] {alert['message']}")
    print(f"  Asset: {alert['asset_guid']}")
    print(f"  Triggered: {alert['triggered_date']}")
```

**Example Output:**
```
[Critical] Temperature critical high: 31.2°C > 30.0°C
  Asset: AHU-01-GUID
  Triggered: 2025-11-30 14:23:00

[Warning] Pressure below threshold: 2.8bar < 3.0bar
  Asset: AHU-01-GUID
  Triggered: 2025-11-30 15:10:00
```

### Acknowledging Alerts

**Goal:** Mark alert as seen by operator

**Via Python/Script:**
```python
alert_id = 1
sensor_registry.acknowledge_alert(alert_id, acknowledged_by='operator_jane')
```

### Resolving Alerts

**Goal:** Close alert after action taken

**Via Python/Script:**
```python
sensor_registry.resolve_alert(
    alert_id=1,
    resolved_by='tech_john',
    notes='Replaced faulty temperature sensor. Readings now normal.'
)
```

### Sensor Statistics

**Via Python/Script:**
```python
# Get reading statistics for sensor
stats = sensor_registry.get_reading_statistics('TEMP-AHU01-SUPPLY')

print(f"Count: {stats['count']}")
print(f"Min: {stats['min']:.2f}°C")
print(f"Max: {stats['max']:.2f}°C")
print(f"Avg: {stats['avg']:.2f}°C")
```

### IoT System Overview

**Via Python/Script:**
```python
iot_stats = sensor_registry.get_iot_statistics()

print(f"Total sensors: {iot_stats['total_sensors']}")
print(f"Total readings: {iot_stats['total_readings']}")
print(f"Active alerts: {iot_stats['active_alerts']}")
print(f"\nSensors by type: {iot_stats['by_type']}")
print(f"Alerts by severity: {iot_stats['alerts_by_severity']}")
```

---

## Common Workflows

### Daily Operator Workflow

**Morning Routine:**

1. ✅ **Check Alerts**
   - View active alerts
   - Acknowledge all
   - Create work orders for critical issues

2. ✅ **Review Work Orders**
   - Check overdue list (⚠️ highlighted)
   - Assign urgent work
   - Follow up on in-progress work

3. ✅ **Monitor Equipment**
   - Check sensor readings for critical assets
   - Look for abnormal trends
   - Color-code visualization in 3D

### Weekly Facility Manager Workflow

**Monday:**

1. ✅ **PM Schedule Review**
   - View PM Summary (next 30 days)
   - Ensure technicians assigned
   - Check for resource conflicts

2. ✅ **Work Order Status**
   - Review completion rate
   - Check overdue work orders
   - Reassign if needed

3. ✅ **Equipment Condition**
   - View assets by condition
   - Identify Fair/Poor equipment
   - Plan replacements

### Quarterly Maintenance Planning

**Every 3 Months:**

1. ✅ **Update PM Templates**
   - Review existing templates
   - Add new equipment types
   - Adjust intervals based on experience

2. ✅ **Generate Schedule**
   - Run PM Schedule for next 90 days
   - Review and adjust priorities
   - Allocate budget for parts

3. ✅ **Asset Lifecycle Review**
   - Check warranty expirations
   - Identify aging equipment (nearing expected lifespan)
   - Budget for replacements

### Emergency Response Workflow

**Critical Alert Received:**

1. 🚨 **Immediate Actions**
   - View alert details
   - Locate asset in 3D model
   - Check sensor history (is this sudden or trending?)

2. 🚨 **Create Work Order**
   - Type: Emergency
   - Priority: Critical
   - Assign immediately
   - Set due date: Today

3. 🚨 **Monitor Resolution**
   - Track work order progress
   - Verify sensor readings return to normal
   - Resolve alert when complete

4. 🚨 **Post-Incident**
   - Log maintenance details
   - Update asset condition if needed
   - Review if PM interval should change

---

## Troubleshooting

### Database Issues

**Problem:** "Database locked" error

**Solution:**
- Close other programs accessing the database
- Ensure only one Blender instance is open
- Restart Blender

**Problem:** Database file not found

**Solution:**
- Check database path in panel settings
- Ensure `WORK_DIR/databases/` folder exists
- Create folder if missing: `mkdir -p ~/Projects/IfcOpenShell/WORK_DIR/databases`

### Import Issues

**Problem:** "No assets imported"

**Solution:**
- Verify IFC file is loaded in Blender
- Check IFC file contains equipment (not just architecture)
- Look in console for detailed error messages

**Problem:** Some assets missing after import

**Solution:**
- Check if IFC class is supported (see README.md for full list)
- Custom equipment may need discipline mapping added
- Re-import with verbose logging enabled

### Performance Issues

**Problem:** Import is very slow

**Solution:**
- Large models (5000+ elements) take time
- Run in background without UI updates
- Consider importing by discipline separately

**Problem:** 3D visualization lag

**Solution:**
- Too many assets color-coded
- Filter by discipline first
- Close other heavy applications

### Data Issues

**Problem:** PM schedule not creating work orders

**Solution:**
- Check PM templates are active (`is_active = 1`)
- Verify assets match template criteria (ifc_class/discipline)
- Check if work orders already exist for those assets

**Problem:** Alerts not triggering

**Solution:**
- Verify sensors have thresholds set
- Check if alerts already exist (no duplicates)
- Run `check_all_sensors()` manually

### Getting Help

**Resources:**
- README.md - Feature documentation
- IMPLEMENTATION_SPEC.md - Technical details
- DATABASE_SCHEMA.md - Database structure
- Test scripts in `WORK_DIR/` for examples

**Support:**
- GitHub Issues: https://github.com/red1oon/IfcOpenShell/issues
- OSArch Forum: Community support

---

## Appendix

### Database Location

Default: `~/Projects/IfcOpenShell/WORK_DIR/databases/digital_twin.db`

Can be changed in panel settings.

### Backup Recommendations

**Daily:**
- Automated SQLite backup: `cp digital_twin.db digital_twin_backup_$(date +%Y%m%d).db`

**Weekly:**
- Export asset report to CSV (archival)
- Export work order list

**Monthly:**
- Full database backup to external storage
- Verify backup restoration

### Data Retention

**Sensor Readings:**
- Keep 5 years minimum
- Consider InfluxDB for production (time-series optimized)

**Work Orders:**
- Keep completed WOs for 2 years
- Archive older to separate table

**Alerts:**
- Resolved alerts can be archived after 90 days

### Performance Tuning

**For Large Installations (10,000+ assets):**
- Use PostgreSQL instead of SQLite
- Add database indexes for common queries
- Batch sensor readings (commit every 100 readings)
- Consider separating databases (assets vs. IoT)

---

**End of User Guide**

For developers: See `README.md` and `IMPLEMENTATION_SPEC.md`
