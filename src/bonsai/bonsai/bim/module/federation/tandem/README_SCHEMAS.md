# Digital Twin Database Schemas

This folder contains all database schema definitions and migration scripts for the Digital Twin (6D/7D BIM) module.

## Schema Files

### Core Schemas

1. **`schema.sql`** - Base Digital Twin schema (Asset Management)
   - `assets` table - Physical building assets
   - `asset_metadata` - Custom properties
   - Asset lifecycle tracking

2. **`schema_maintenance.sql`** - Maintenance & Work Orders (6D)
   - `work_orders` table - Maintenance tasks
   - `maintenance_schedules` - Preventive maintenance
   - Work order lifecycle and assignment

3. **`schema_iot.sql`** - IoT & Sensor Integration (7D) ⭐ **Latest: v1.1**
   - `sensors` table - IoT sensor registry
   - `sensor_readings` - Time-series sensor data
   - `alert_rules` - Threshold-based alerting
   - `alerts` - Active/historical alerts
   - **Virtual Sensor Pattern** documented

4. **`schema_federation_integrated.sql`** - Complete integrated schema
   - Combines all above schemas
   - Federation integration (links to `element_transforms`, `elements_meta`)
   - Use this for new database creation

## Migration Scripts

### Sensor Management

- **`add_virtual_sensors.py`** - Add virtual IoT sensors with 3D visualization
  - Creates virtual assets in `element_transforms` + `elements_meta`
  - Links sensors to virtual assets via `asset_guid`
  - Generates mock sensor readings for testing
  - Example: Main hall fire safety sensors

## Virtual Sensor Pattern

Sensors that don't have corresponding IFC geometry can be visualized using "virtual assets":

```python
# 1. Create virtual asset with 3D position
cursor.execute("""
    INSERT INTO element_transforms (guid, center_x, center_y, center_z, transform_source)
    VALUES ('VIRTUAL_SENSOR_001', 10.0, 20.0, 3.0, 'virtual_sensor')
""")

# 2. Add metadata
cursor.execute("""
    INSERT INTO elements_meta (guid, element_name, ifc_class, discipline)
    VALUES ('VIRTUAL_SENSOR_001', 'Temperature Sensor Room 101', 'IfcSensor', 'ACMV')
""")

# 3. Create sensor linked to virtual asset
cursor.execute("""
    INSERT INTO sensors (sensor_id, asset_guid, sensor_type, measurement_unit, ...)
    VALUES ('TEMP-101', 'VIRTUAL_SENSOR_001', 'Temperature', '°C', ...)
""")
```

The sensor overlay (`sensor_overlay.py`) queries 3D positions by joining:
```sql
SELECT s.*, t.center_x, t.center_y, t.center_z
FROM sensors s
LEFT JOIN element_transforms t ON s.asset_guid = t.guid
```

## Schema Versioning

| File | Version | Date | Changes |
|------|---------|------|---------|
| `schema_iot.sql` | 1.1 | 2025-12-02 | Added virtual sensor pattern docs |
| `schema_iot.sql` | 1.0 | 2025-11-30 | Initial IoT schema |
| `schema_maintenance.sql` | 1.0 | 2025-11-28 | Initial maintenance schema |
| `schema.sql` | 1.0 | 2025-11-25 | Initial asset schema |

## Usage Examples

### Initialize New Database

```bash
# Create complete Digital Twin database
sqlite3 my_digital_twin.db < schema_federation_integrated.sql
```

### Add Virtual Sensors

```bash
# Add example sensors to main hall
python3 add_virtual_sensors.py ~/WORK_DIR/databases/enhanced_federation.db
```

### Query Sensor Locations

```sql
-- Get all sensors with 3D positions
SELECT
    s.sensor_id,
    s.sensor_type,
    t.center_x, t.center_y, t.center_z,
    m.element_name as asset_name
FROM sensors s
LEFT JOIN element_transforms t ON s.asset_guid = t.guid
LEFT JOIN elements_meta m ON s.asset_guid = m.guid
WHERE s.is_active = 1;
```

## Integration Points

### Federation Database
- `element_transforms` - 3D bounding boxes and centers for all IFC elements
- `elements_meta` - IFC metadata (GUID, name, class, discipline)
- `geometry_cache` - Tessellated geometry for visualization

### Blender Visualization
- `sensor_overlay.py` - GPU-based 3D sensor overlay in viewport
- `operator.py` - Sensor interaction operators (view history, create work orders)
- `ui.py` - IoT Command Center UI panels

### Analytics
- `mock_data_generator.py` - Generate test data for development
- `analytics.py` - Time-series analytics and reporting

## Notes

- **SQLite** is used for development/testing. Production should use:
  - InfluxDB/TimescaleDB for sensor readings (time-series)
  - PostgreSQL for asset/maintenance tables (relational)

- **Foreign Keys**: Sensors → Assets via `asset_guid`
  - Real IFC assets: `asset_guid` matches `element_transforms.guid`
  - Virtual sensors: `asset_guid` points to synthetic GUID in `element_transforms`

- **Sensor IDs**: Use hierarchical naming convention:
  - `{TYPE}-{LOCATION}-{SEQUENCE}`
  - Example: `TEMP-ROOM101-01`, `SPRINKLER-HALL-CENTER`

## Related Documentation

- `/WORK_DIR/docs/6d_7d_digital_twin/` - Digital Twin feature docs
- `/WORK_DIR/docs/6d_7d_digital_twin/IoT_COMMAND_CENTER_USAGE.md` - User guide
- `sensor_overlay.py` - Implementation details for 3D visualization
