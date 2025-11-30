# Digital Twin (Tandem Alternative) - Implementation Specification

**Open-Source Facilities Management & IoT Integration for IFC Buildings**

Version: 1.0
Date: 2025-11-30
Status: Design Phase

---

## 🎯 Executive Summary

**Goal:** Build an open-source alternative to Autodesk Tandem for digital twin facilities management, integrating asset tracking, maintenance scheduling, and IoT sensor monitoring with existing Bonsai Federation 4D/5D BIM system.

**Scope:**
- **Asset Management (6D)** - Equipment registry, warranties, manuals, lifecycle tracking
- **Maintenance Scheduling (6D)** - Preventive maintenance, work orders, service history
- **IoT Integration (7D)** - Real-time sensor data, performance monitoring, alerts

**Target Users:**
- Facility managers
- Building operators
- Maintenance teams
- Property owners
- IoT engineers

**Business Case:**
- Autodesk Tandem: $360-$720/year per user
- Our solution: Free, open-source, IFC-native
- Democratizes digital twin technology for global AEC industry

---

## 📋 System Requirements

### Functional Requirements

#### FR-1: Asset Management
- **FR-1.1** - Import equipment data from IFC models (IfcEquipment, IfcDistributionElement)
- **FR-1.2** - Track asset metadata (manufacturer, model, serial number, install date)
- **FR-1.3** - Store warranty information (start date, duration, vendor contact)
- **FR-1.4** - Attach documents (manuals, specifications, photos)
- **FR-1.5** - Calculate lifecycle status (age, expected replacement date)
- **FR-1.6** - Visual asset location in 3D model (Blender integration)

#### FR-2: Maintenance Scheduling
- **FR-2.1** - Define preventive maintenance (PM) tasks per asset type
- **FR-2.2** - Auto-generate PM schedule based on intervals (daily/weekly/monthly/yearly)
- **FR-2.3** - Create work orders (scheduled, urgent, on-demand)
- **FR-2.4** - Track work order status (open, in-progress, completed, deferred)
- **FR-2.5** - Log maintenance history (date, technician, actions, parts used)
- **FR-2.6** - Calculate MTBF (Mean Time Between Failures) from history

#### FR-3: IoT Integration
- **FR-3.1** - Link sensors to IFC elements (via GUID mapping)
- **FR-3.2** - Ingest real-time sensor data (temperature, humidity, flow, pressure)
- **FR-3.3** - Store time-series data efficiently (InfluxDB or TimescaleDB)
- **FR-3.4** - Generate alerts based on thresholds (high temp, low pressure)
- **FR-3.5** - Visualize sensor readings in 3D (color-coded equipment)
- **FR-3.6** - Historical trend analysis (energy consumption, performance degradation)

### Non-Functional Requirements

#### NFR-1: Performance
- Support 50,000+ assets (Terminal 1 scale)
- Real-time sensor updates (<1 second latency)
- Dashboard load time <3 seconds
- Historical queries respond in <5 seconds

#### NFR-2: Scalability
- Multi-building support (campus, portfolio)
- Handle 10,000+ sensors per building
- Time-series data retention: 5 years minimum

#### NFR-3: Interoperability
- IFC 2x3, IFC4, IFC4.3 support
- Standard IoT protocols (MQTT, HTTP REST, OPC UA)
- Export to CSV, Excel, JSON
- API for third-party integrations

#### NFR-4: Security
- Role-based access control (admin, operator, viewer)
- Sensor data encryption in transit (TLS)
- Audit log for all changes

---

## 🏗️ System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACES                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Blender    │  │  Web Dashboard│  │  Mobile App  │  │
│  │  (3D Visual) │  │  (Analytics)  │  │ (Field Tech) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
└─────────┼──────────────────┼──────────────────┼─────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
┌─────────────────────────────┴──────────────────────────────┐
│                     API LAYER                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  FastAPI / Flask REST API                            │  │
│  │  - Asset Management Endpoints                        │  │
│  │  - Maintenance Scheduling Endpoints                  │  │
│  │  - IoT Data Ingestion Endpoints                      │  │
│  │  - Authentication & Authorization                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────┬──────────────────────┬───────────────────────┘
              │                      │
┌─────────────┴──────────┐  ┌────────┴──────────────────────┐
│  BUSINESS LOGIC LAYER  │  │   DATA PROCESSING LAYER       │
│  ┌──────────────────┐  │  │  ┌─────────────────────────┐  │
│  │ Asset Manager    │  │  │  │ Sensor Data Processor   │  │
│  │ Maintenance Sched│  │  │  │ Alert Engine            │  │
│  │ Work Order Mgr   │  │  │  │ Analytics Calculator    │  │
│  │ Lifecycle Tracker│  │  │  │ Predictive Maintenance  │  │
│  └──────────────────┘  │  │  └─────────────────────────┘  │
└─────────────┬──────────┘  └────────┬──────────────────────┘
              │                      │
┌─────────────┴──────────────────────┴───────────────────────┐
│                     DATA LAYER                              │
│  ┌──────────────────┐  ┌──────────────────────────────┐   │
│  │  SQLite/Postgres │  │  InfluxDB / TimescaleDB      │   │
│  │  (Assets, Work   │  │  (Time-series sensor data)   │   │
│  │   Orders, Maint) │  │                               │   │
│  └──────────────────┘  └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                             │
┌─────────────────────────────┴──────────────────────────────┐
│                  INTEGRATION LAYER                          │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │  MQTT Broker │  │  BACnet/      │  │  HTTP/REST      │  │
│  │  (IoT Msgs)  │  │  OPC UA       │  │  (API Sensors)  │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                             │
                   ┌─────────┴─────────┐
                   │   PHYSICAL LAYER   │
                   │  Sensors, BMS,     │
                   │  IoT Devices       │
                   └────────────────────┘
```

### Component Descriptions

#### 1. Asset Management Module
**Purpose:** Track building equipment throughout lifecycle

**Components:**
- `asset_registry.py` - CRUD operations for assets
- `asset_importer.py` - Extract equipment from IFC models
- `document_manager.py` - Attach PDFs, photos, manuals
- `lifecycle_calculator.py` - Age tracking, replacement predictions

**Database Tables:**
- `assets` - Core asset registry
- `asset_documents` - File attachments
- `asset_properties` - Flexible key-value metadata
- `asset_history` - Change tracking

#### 2. Maintenance Scheduling Module
**Purpose:** Plan and execute preventive/corrective maintenance

**Components:**
- `pm_scheduler.py` - Generate recurring PM tasks
- `work_order_manager.py` - Create, assign, track work orders
- `maintenance_logger.py` - Record completed work
- `mtbf_calculator.py` - Failure analysis

**Database Tables:**
- `pm_templates` - Maintenance task templates
- `work_orders` - Active and historical work orders
- `maintenance_log` - Service history
- `technicians` - Maintenance team roster

#### 3. IoT Integration Module
**Purpose:** Connect physical sensors to digital model

**Components:**
- `sensor_registry.py` - Map sensors to IFC elements
- `mqtt_listener.py` - Subscribe to MQTT topics
- `data_ingester.py` - Parse and store sensor data
- `alert_engine.py` - Threshold monitoring, notifications
- `trend_analyzer.py` - Historical data analysis

**Database Tables:**
- `sensors` - Sensor registry (ID, type, IFC GUID mapping)
- `sensor_readings` - Time-series data (InfluxDB)
- `alert_rules` - Threshold configurations
- `alerts` - Triggered alerts

#### 4. Visualization Module (Blender Integration)
**Purpose:** 3D visualization of asset status and sensor data

**Components:**
- `asset_visualizer.py` - Color-code equipment by status
- `sensor_heatmap.py` - Show temperature/pressure gradients
- `work_order_overlay.py` - Highlight assets with open WOs
- `timeline_player.py` - Replay historical sensor data

**Status Colors:**
- 🟢 Green - Normal operation
- 🟡 Yellow - Warning (approaching threshold)
- 🔴 Red - Critical (threshold exceeded or failure)
- ⚫ Gray - No data / Offline

---

## 📊 Database Schema

See **DATABASE_SCHEMA.md** for detailed table definitions.

**Summary:**
- **Relational DB (SQLite/Postgres):** Assets, work orders, maintenance logs
- **Time-series DB (InfluxDB):** Sensor readings (high-frequency data)
- **Document Storage (Filesystem):** Manuals, photos, warranties

**Key Relationships:**
```
assets (1) ─── (N) work_orders
assets (1) ─── (N) maintenance_log
assets (1) ─── (N) sensors
sensors (1) ─── (N) sensor_readings (time-series)
sensors (1) ─── (N) alerts
```

---

## 🔌 API Design

See **API_DESIGN.md** for complete endpoint specifications.

**Base URL:** `http://localhost:5000/api/v1`

**Core Endpoints:**

### Assets
```
GET    /assets                      # List all assets
GET    /assets/{guid}               # Get asset details
POST   /assets                      # Create asset
PUT    /assets/{guid}               # Update asset
DELETE /assets/{guid}               # Delete asset
GET    /assets/{guid}/sensors       # Get asset's sensors
GET    /assets/{guid}/workorders    # Get asset's work orders
GET    /assets/{guid}/maintenance   # Get maintenance history
```

### Work Orders
```
GET    /workorders                  # List work orders
POST   /workorders                  # Create work order
PUT    /workorders/{id}/status      # Update status
POST   /workorders/{id}/complete    # Mark complete (with log entry)
```

### Sensors
```
GET    /sensors                     # List sensors
POST   /sensors/readings            # Ingest sensor data (batch)
GET    /sensors/{id}/latest         # Get latest reading
GET    /sensors/{id}/history        # Get historical readings
GET    /sensors/{id}/alerts         # Get active alerts
```

### Dashboard
```
GET    /dashboard/summary           # Building overview stats
GET    /dashboard/alerts            # Active alerts
GET    /dashboard/workorders/open   # Open work orders count
GET    /dashboard/energy            # Energy consumption trends
```

---

## 🎨 User Interfaces

### 1. Blender Add-on Panel

**Location:** Properties → Scene → Digital Twin

```
┌─────────────────────────────────────────────┐
│  DIGITAL TWIN - Facilities Management       │
├─────────────────────────────────────────────┤
│                                              │
│  📊 Building Status:                         │
│     Total Assets: 1,247                      │
│     Active Sensors: 342                      │
│     Open Work Orders: 12                     │
│     Alerts: 3 🔴                             │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │ [🔄 Sync from Database]              │    │
│  │ [📍 Highlight Alerts in 3D]          │    │
│  │ [📅 Open Maintenance Dashboard]      │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  🎨 Visualization Mode:                      │
│     ( ) Asset Status (Green/Yellow/Red)      │
│     ( ) Sensor Heatmap (Temperature)         │
│     (•) Work Orders (Highlight Equipment)    │
│                                              │
│  🔍 Filter:                                  │
│     [x] ACMV   [ ] ELEC   [x] FP             │
│     [ ] Show Offline Sensors Only            │
│                                              │
│  📱 Selected Asset: AHU-01                   │
│     Manufacturer: Trane                      │
│     Model: RTAA-140                          │
│     Status: 🔴 Critical (High Temp)          │
│     Last PM: 2025-10-15                      │
│     Next PM: 2025-12-15 (overdue!)           │
│                                              │
│     [📋 View Work Orders]                    │
│     [📈 View Sensor History]                 │
│     [🔧 Create Work Order]                   │
│                                              │
└─────────────────────────────────────────────┘
```

### 2. Web Dashboard (Flask/FastAPI + React)

**Homepage:**
```
┌────────────────────────────────────────────────────────────┐
│  🏢 Terminal 1 - Digital Twin Dashboard                    │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  📊 Overview (Last 24 Hours)                                │
│  ┌──────────────┬──────────────┬──────────────┬─────────┐  │
│  │ Assets       │ Work Orders  │ Alerts       │ Energy  │  │
│  │ 1,247        │ 12 Open      │ 3 Critical   │ 2.4 MWh │  │
│  │ 🟢 98% OK    │ 45 Completed │ 8 Warning    │ ↓ 5%    │  │
│  └──────────────┴──────────────┴──────────────┴─────────┘  │
│                                                             │
│  🚨 Active Alerts                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🔴 AHU-01 | High Temperature (28°C > 25°C limit)    │   │
│  │    Location: Level 3 East                           │   │
│  │    Since: 2025-11-30 14:23                          │   │
│  │    [View Details] [Create Work Order] [Acknowledge] │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ 🔴 Chiller-02 | Low Pressure (3.2 bar < 4.0 min)   │   │
│  │    Location: Basement Mechanical Room               │   │
│  │    Since: 2025-11-30 13:45                          │   │
│  │    [View Details] [Create Work Order] [Acknowledge] │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ 🟡 Pump-05 | Approaching PM Date (Due in 3 days)   │   │
│  │    [Schedule Maintenance]                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  📈 Energy Consumption (Past 7 Days)                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │     3.0 MWh │              ▄                         │   │
│  │     2.5     │         ▄   ▄█▄  ▄                     │   │
│  │     2.0     │    ▄   ▄█▄ ▄███▄▄█▄  ▄                 │   │
│  │     1.5     │───▄█▄─▄███─█████████─▄█────────────────│   │
│  │     1.0     │  ████████████████████████              │   │
│  │             └────────────────────────────            │   │
│  │              Mon Tue Wed Thu Fri Sat Sun             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [View All Assets] [Work Order Calendar] [Sensor Map]      │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### 3. Mobile App (React Native / Progressive Web App)

**Field Technician View:**
```
┌──────────────────────────┐
│  🔧 Work Order #1247     │
├──────────────────────────┤
│                          │
│  Asset: AHU-01           │
│  Location: Level 3 East  │
│                          │
│  Task: Replace air filter│
│  Priority: High          │
│  Due: Today 16:00        │
│                          │
│  ┌────────────────────┐  │
│  │ [📷 Take Photo]    │  │
│  │ [📝 Add Notes]     │  │
│  │ [✓ Mark Complete]  │  │
│  └────────────────────┘  │
│                          │
│  📍 Navigate to Asset    │
│  📞 Call Supervisor      │
│                          │
└──────────────────────────┘
```

---

## 🚀 Implementation Roadmap

See **ROADMAP.md** for detailed phase breakdown.

### Phase 1: Asset Management (2-3 weeks)
**Goal:** Basic asset registry and IFC import

**Deliverables:**
- Database schema (assets, properties, documents)
- IFC equipment importer
- Blender UI panel (asset list, details)
- Basic asset CRUD operations

**Success Metrics:**
- Import 1,247 assets from Terminal 1 IFC
- View asset details in Blender
- Color-code assets by lifecycle stage

### Phase 2: Maintenance Scheduling (3-4 weeks)
**Goal:** Work order management and PM scheduling

**Deliverables:**
- Work order database tables
- PM template system
- Work order calendar
- Maintenance logging

**Success Metrics:**
- Create PM schedule for 100 critical assets
- Generate work orders automatically
- Track completion rate

### Phase 3: IoT Integration (Mock Data) (2-3 weeks)
**Goal:** Sensor registry and simulated data

**Deliverables:**
- Sensor database tables
- Mock data generator (temperature, pressure)
- Alert engine (threshold monitoring)
- Sensor heatmap visualization in Blender

**Success Metrics:**
- Link 342 mock sensors to IFC elements
- Generate alerts when thresholds exceeded
- Visualize temperature gradient in 3D

### Phase 4: Web Dashboard (3-4 weeks)
**Goal:** Standalone web interface

**Deliverables:**
- FastAPI backend
- React frontend
- Dashboard with charts (Chart.js)
- REST API for all operations

**Success Metrics:**
- Dashboard loads in <3 seconds
- Real-time alert updates
- Export data to CSV/Excel

### Phase 5: Real IoT Integration (4-6 weeks)
**Goal:** Connect to actual BMS/sensors

**Deliverables:**
- MQTT client (subscribe to topics)
- BACnet integration (if needed)
- InfluxDB time-series storage
- Historical trend analysis

**Success Metrics:**
- Ingest 10,000 sensor readings/minute
- Store 5 years of historical data
- Query performance <5 seconds

### Phase 6: Advanced Features (Ongoing)
**Goal:** Predictive maintenance, mobile app

**Deliverables:**
- ML model for failure prediction
- Mobile PWA for field technicians
- QR code scanner for asset lookup
- Energy analytics dashboard

---

## 🧪 Testing Strategy

### Unit Tests
- pytest for Python modules
- Mock database fixtures
- Test IFC importer with sample files

### Integration Tests
- End-to-end API tests
- Database transaction tests
- MQTT message handling

### Performance Tests
- Load testing (10,000 concurrent sensor writes)
- Query optimization (complex joins)
- 3D visualization performance (50k assets)

### User Acceptance Testing
- Test with facility managers
- Field technician workflow validation
- Dashboard usability testing

---

## 📈 Success Metrics

### Key Performance Indicators (KPIs)

**Technical:**
- API response time: <500ms (p95)
- Sensor data latency: <1 second
- Dashboard load time: <3 seconds
- Database query time: <5 seconds

**Business:**
- User adoption: 20+ facility managers in first year
- Asset coverage: 90%+ of equipment tracked
- Work order completion rate: >95%
- Preventive maintenance compliance: >80%

**Community:**
- GitHub stars: 100+ in first 6 months
- Active contributors: 5+
- Adoption by 3+ organizations

---

## 💰 Cost Comparison

### Autodesk Tandem (Commercial)
- **License:** $360-$720/year per user
- **10 users:** $3,600-$7,200/year
- **5 years:** $18,000-$36,000
- **Vendor lock-in:** Yes
- **Customization:** Limited

### Our Solution (Open Source)
- **License:** Free (GPL-3.0)
- **10 users:** $0/year
- **5 years:** $0
- **Vendor lock-in:** No
- **Customization:** Full control

**ROI:** Immediate, infinite return for organizations

---

## 🔐 Security Considerations

### Access Control
- Role-based permissions (admin, operator, viewer)
- API authentication (JWT tokens)
- Audit logging for all changes

### Data Protection
- TLS encryption for sensor data
- Database encryption at rest (optional)
- Regular backups (automated)

### IoT Security
- MQTT over TLS
- Sensor authentication (client certificates)
- Network segmentation (IoT VLAN)

---

## 📚 Technology Stack

**Backend:**
- Python 3.11+
- FastAPI (REST API)
- SQLite (development), PostgreSQL (production)
- InfluxDB (time-series data)
- Paho MQTT (IoT messaging)

**Frontend:**
- React 18+
- Chart.js (visualizations)
- Material-UI (components)
- Socket.IO (real-time updates)

**3D Visualization:**
- Blender 4.2+
- Bonsai add-on
- Python API

**Infrastructure:**
- Docker (containerization)
- nginx (reverse proxy)
- Redis (caching)

---

## 🤝 Open Source Strategy

### License
GPL-3.0-or-later (same as Bonsai/IfcOpenShell)

### Community Engagement
- OSArch forum announcements
- GitHub Discussions for feedback
- Monthly development updates
- Annual community roadmap review

### Contribution Guidelines
- Code review process
- Unit test requirements
- Documentation standards
- IFC compliance validation

---

## 📞 Support & Resources

**Documentation:**
- User guide for facility managers
- API documentation (Swagger/OpenAPI)
- Developer guide for contributors
- Video tutorials

**Training:**
- Webinars for new users
- Case studies from pilot projects
- Best practices guide

**Community:**
- GitHub Issues for bug reports
- Discussions for feature requests
- Discord/Slack for real-time help

---

## ✅ Next Steps

1. **Review this spec** with stakeholders
2. **Validate database schema** with facility managers
3. **Create Phase 1 prototype** (asset management)
4. **Test with Terminal 1 data**
5. **Iterate based on feedback**

---

**Status:** Ready for Implementation
**Est. Phase 1 Start:** December 2025
**Est. Production Release:** Q2 2026

**Contact:** red1oon@github
**Project:** [Bonsai Federation - Digital Twin Module](https://github.com/red1oon/IfcOpenShell)
