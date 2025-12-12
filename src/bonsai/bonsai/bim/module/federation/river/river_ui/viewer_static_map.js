/**
 * Klang River Real Data Viewer - STATIC MAP VERSION
 * Uses a fixed background image instead of OSM tiles
 * Much simpler, faster, works offline
 */

class RealRiverViewer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) {
            console.error('Canvas not found:', canvasId);
            return;
        }

        this.ctx = this.canvas.getContext('2d');
        this.width = this.canvas.width;
        this.height = this.canvas.height;

        // View transform (for overlays - river & sensors)
        this.offsetX = 0;
        this.offsetY = 0;
        this.scale = 1.0;
        this.isDragging = false;
        this.lastMouseX = 0;
        this.lastMouseY = 0;

        // Separate river transform (independent from markers)
        this.riverBaseOffsetX = 0;
        this.riverBaseOffsetY = 0;

        // ================================================================
        // ========== BACKGROUND IMAGE ALIGNMENT - ADJUST HERE ===========
        // ================================================================
        
        // IMAGE FILE: Put your map image in same folder or adjust path
        this.bgImageSrc = 'map_klang_valley.png';  // ← Your image file
        
        // POSITION: Move image left/right, up/down (in pixels)
        this.bgOffsetX = -10;    // ← Positive = move image RIGHT
        this.bgOffsetY = +5;    // ← Positive = move image DOWN
        
        // SCALE: Make image bigger/smaller (1.0 = original size)
        this.bgScale = 0.65;    // ← 1.2 = 20% bigger, 0.8 = 20% smaller
        
        // ================================================================
        
        this.bgImage = null;
        this.bgLoaded = false;

        // Data
        this.riverGeometry = null;
        this.markers = [];
        this.selectedMarker = null;

        // Display options
        this.showRiver = true;  // Disabled - background map shows actual river
        this.showMarkers = true;
        this.showBackground = true;

        // Overlay scale multipliers (separate control for river vs markers)
        this.overlayScale = 1.95;     // For markers
        this.riverScale = 2.3;       // For river line (adjust independently)

        // River position offset (relative to markers)
        this.riverOffsetX = 207;       // Positive = move river RIGHT
        this.riverOffsetY = -130;       // Positive = move river DOWN

        // Marker type visibility
        this.markerTypeVisibility = {
            'boom_trap': true,
            'water_quality': true,
            'pollutant_sensor': true,
            'wildlife_camera': true,
            'flood_monitor': true,
            'biochar_facility': true,
            'mrf_site': true
        };

        // Animation
        this.pulsePhase = 0;
        this.animationFrame = null;

        // Map projection bounds
        this.bounds = {
            lon_min: 180,
            lon_max: -180,
            lat_min: 90,
            lat_max: -90
        };

        // Load background image
        this.loadBackgroundImage();
        
        // Load data
        this.loadData();
    }

    loadBackgroundImage() {
        this.bgImage = new Image();
        this.bgImage.onload = () => {
            this.bgLoaded = true;
            console.log(`✓ Background image loaded: ${this.bgImage.width}x${this.bgImage.height}`);
        };
        this.bgImage.onerror = () => {
            console.warn('⚠ Background image not found:', this.bgImageSrc);
            console.warn('  Place your map image in the same folder');
        };
        this.bgImage.src = this.bgImageSrc;
    }

    async loadData() {
        try {
            console.log('🔄 Loading river data...');

            // Load river geometry from Blender database
            const riverResponse = await fetch('output/geojson/river_from_blender.geojson?v=' + Date.now());
            console.log('  River response status:', riverResponse.status);
            const riverData = await riverResponse.json();
            this.processRiverData(riverData);
            console.log('  ✓ River geometry loaded');

            // Load project markers
            console.log('🔄 Loading markers...');
            const markersResponse = await fetch('output/geojson/project_markers.geojson?v=' + Date.now());
            console.log('  Markers response status:', markersResponse.status);
            const markersData = await markersResponse.json();
            console.log('  Markers data features:', markersData.features ? markersData.features.length : 'NONE');

            this.processMarkers(markersData);
            console.log('  ✓ Processed markers:', this.markers.length);

            // Log first marker for verification
            if (this.markers.length > 0) {
                const m = this.markers[0];
                console.log('  First marker:', m.name, 'at', m.lon, m.lat, 'color:', m.color, 'sensors:', m.sensor_count);
            }

            // Calculate bounds
            this.calculateBounds();

            // Setup event listeners
            this.setupEventListeners();

            // Start rendering
            this.render();

            console.log('✓ Loaded real Klang River data');
            console.log(`  River: 1 feature`);
            console.log(`  Markers: ${this.markers.length}`);

        } catch (error) {
            console.error('❌ Error loading data:', error);
            console.error('Error stack:', error.stack);
        }
    }

    processRiverData(geojson) {
        this.riverGeometry = [];
        const features = geojson.type === 'FeatureCollection' ? geojson.features : [geojson];

        for (let feature of features) {
            if (feature.geometry.type === 'Polygon') {
                this.riverGeometry.push(feature.geometry.coordinates);
            } else if (feature.geometry.type === 'MultiPolygon') {
                for (let polygon of feature.geometry.coordinates) {
                    this.riverGeometry.push(polygon);
                }
            }
        }
        console.log('  River polygons loaded:', this.riverGeometry.length);
        if (this.riverGeometry.length > 0 && this.riverGeometry[0][0]) {
            console.log('  First river point:', this.riverGeometry[0][0][0]);
        }
    }

    processMarkers(geojson) {
        this.markers = geojson.features.map(feature => ({
            id: feature.properties.id,
            name: feature.properties.name,
            type: feature.properties.type,
            priority: feature.properties.priority,
            color: feature.properties.color,
            pulse_rate: feature.properties.pulse_rate || 3.0,
            description: feature.properties.description || '',
            sensor_count: feature.properties.sensor_count || 0,
            sensor_summary: feature.properties.sensor_summary || '',
            sensors: feature.properties.sensors || [],
            lon: feature.geometry.coordinates[0],
            lat: feature.geometry.coordinates[1]
        }));

        // Update legend counts dynamically
        this.updateLegendCounts();
    }

    updateLegendCounts() {
        // Count markers by type
        const counts = {};
        this.markers.forEach(marker => {
            counts[marker.type] = (counts[marker.type] || 0) + 1;
        });

        // Update legend labels - handle both naming conventions
        const typeMap = {
            'boom_trap': 'boom_trap',
            'water_quality': 'water_quality',
            'pollutant_sensor': 'pollutant_sensor',
            'wildlife_camera': 'wildlife_camera',
            'flood_monitor': 'flood_monitor',
            'biochar': 'biochar_facility',
            'biochar_facility': 'biochar_facility',
            'mrf': 'mrf_site',
            'mrf_site': 'mrf_site',
            'biodiversity': 'wildlife_camera'
        };

        // Update each legend item
        Object.keys(counts).forEach(type => {
            const legendType = typeMap[type] || type;
            const checkbox = document.getElementById(`toggle_${legendType}`);
            if (checkbox && checkbox.parentElement) {
                const label = checkbox.parentElement.querySelector('span:last-child');
                if (label) {
                    const name = label.textContent.split('(')[0].trim();
                    label.textContent = `${name} (${counts[type]})`;
                }
            }
        });
    }

    calculateBounds() {
        // Updated to match recalibrated GPS range (2025-12-13)
        // Actual markers range: Lon 101.376-101.762, Lat 2.976-3.231 (with 5% padding)
        this.bounds.lon_min = 101.357;
        this.bounds.lon_max = 101.781;
        this.bounds.lat_min = 2.963;
        this.bounds.lat_max = 3.244;
        this.fitToView();
    }

    fitToView() {
        const lon_range = this.bounds.lon_max - this.bounds.lon_min;
        const lat_range = this.bounds.lat_max - this.bounds.lat_min;

        const scaleX = this.width / lon_range;
        const scaleY = this.height / lat_range;
        this.scale = Math.min(scaleX, scaleY) * 0.5;  // Keep original zoom level

        // Center the river, shifted up
        const centerLon = this.bounds.lon_min + lon_range / 2;
        const centerLat = this.bounds.lat_min + lat_range / 2;
        //MARKERS LINE ONLY
        this.offsetX = this.width / 2 - centerLon * this.scale - 0; // move right
        this.offsetY = (this.height / 2 - 28) + centerLat * this.scale;  // +120 shifts up more

        // River base offset (independent - adjust these values to reposition river base)
        this.riverBaseOffsetX = this.width / 2 - centerLon * this.scale - 3.5;
        this.riverBaseOffsetY = (this.height / 2 - 11) + centerLat * this.scale;
    }

    zoomTowardsCenter(zoomFactor) {
        const centerX = this.width / 2;
        const centerY = this.height / 2;
        const [centerLon, centerLat] = this.screenToLatLon(centerX, centerY);

        const newScale = this.scale * zoomFactor;
        if (newScale >= 100 && newScale <= 100000) {
            this.scale = newScale;
            this.offsetX = centerX - centerLon * this.scale;
            this.offsetY = centerY + centerLat * this.scale;
        }
    }

    latLonToScreen(lon, lat, customScale = null, useRiverOffset = false) {
        // Choose base offset: river has independent positioning
        const baseOffsetX = useRiverOffset ? this.riverBaseOffsetX : this.offsetX;
        const baseOffsetY = useRiverOffset ? this.riverBaseOffsetY : this.offsetY;

        const x = baseOffsetX + lon * this.scale;
        const y = baseOffsetY - lat * this.scale;

        // If custom scale requested, scale around canvas center
        if (customScale !== null) {
            const centerX = this.width / 2;
            const centerY = this.height / 2;
            const additionalOffsetX = useRiverOffset ? this.riverOffsetX : 0;
            const additionalOffsetY = useRiverOffset ? this.riverOffsetY : 0;
            return [
                centerX + (x - centerX) * customScale + additionalOffsetX,
                centerY + (y - centerY) * customScale + additionalOffsetY
            ];
        }

        return [x, y];
    }

    screenToLatLon(x, y) {
        const lon = (x - this.offsetX) / this.scale;
        const lat = -(y - this.offsetY) / this.scale;
        return [lon, lat];
    }

    setupEventListeners() {
        // Mouse drag
        this.canvas.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            const rect = this.canvas.getBoundingClientRect();
            const scaleX = this.canvas.width / rect.width;
            const scaleY = this.canvas.height / rect.height;
            this.lastMouseX = (e.clientX - rect.left) * scaleX;
            this.lastMouseY = (e.clientY - rect.top) * scaleY;
        });

        this.canvas.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const scaleX = this.canvas.width / rect.width;
            const scaleY = this.canvas.height / rect.height;
            const mouseX = (e.clientX - rect.left) * scaleX;
            const mouseY = (e.clientY - rect.top) * scaleY;

            if (this.isDragging) {
                // Dragging disabled - markers stay fixed
               // const dx = mouseX - this.lastMouseX;
               // const dy = mouseY - this.lastMouseY;
               // this.offsetX += dx;
               // this.offsetY += dy;
               // this.lastMouseX = mouseX;
               // this.lastMouseY = mouseY;
            } else {
                this.checkMarkerHover(mouseX, mouseY);
            }
        });

        this.canvas.addEventListener('mouseup', () => {
            this.isDragging = false;
        });

        this.canvas.addEventListener('mouseleave', () => {
            this.isDragging = false;
        });

        // Click
        this.canvas.addEventListener('click', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const scaleX = this.canvas.width / rect.width;
            const scaleY = this.canvas.height / rect.height;
            const mouseX = (e.clientX - rect.left) * scaleX;
            const mouseY = (e.clientY - rect.top) * scaleY;
            this.handleMarkerClick(mouseX, mouseY);
        });

        // Zoom
      //  this.canvas.addEventListener('wheel', (e) => {
       //     e.preventDefault();
        //    const zoomFactor = e.deltaY > 0 ? 0.995 : 1.005;
         //   this.zoomTowardsCenter(zoomFactor);
       // });

        // Reset view button
        document.getElementById('resetView')?.addEventListener('click', () => {
            this.fitToView();
        });

        // Zoom buttons
        document.getElementById('zoomIn')?.addEventListener('click', () => {
            this.zoomTowardsCenter(1.10);
        });

        document.getElementById('zoomOut')?.addEventListener('click', () => {
            this.zoomTowardsCenter(0.90);
        });

        // Toggle river checkbox
        document.getElementById('toggleRiver')?.addEventListener('change', (e) => {
            this.showRiver = e.target.checked;
        });

        // Marker type checkboxes
        const markerTypes = ['boom_trap', 'water_quality', 'pollutant_sensor', 'wildlife_camera', 'flood_monitor', 'biochar_facility', 'mrf_site'];
        markerTypes.forEach(type => {
            const checkbox = document.getElementById(`toggle_${type}`);
            if (checkbox) {
                checkbox.addEventListener('change', (e) => {
                    this.markerTypeVisibility[type] = e.target.checked;
                });
            }
        });
    }

    checkMarkerHover(mouseX, mouseY) {
        for (let marker of this.markers) {
            if (!this.markerTypeVisibility[marker.type]) continue;
            const [x, y] = this.latLonToScreen(marker.lon, marker.lat, this.overlayScale);
            const dist = Math.sqrt((mouseX - x) ** 2 + (mouseY - y) ** 2);
            if (dist < 15) {
                this.canvas.style.cursor = 'pointer';
                return;
            }
        }
        this.canvas.style.cursor = this.isDragging ? 'grabbing' : 'grab';
    }

    handleMarkerClick(mouseX, mouseY) {
        for (let marker of this.markers) {
            if (!this.markerTypeVisibility[marker.type]) continue;
            const [x, y] = this.latLonToScreen(marker.lon, marker.lat, this.overlayScale);
            const dist = Math.sqrt((mouseX - x) ** 2 + (mouseY - y) ** 2);
            if (dist < 15) {
                this.selectedMarker = marker;
                this.showPropertyPanel(marker);
                return;
            }
        }
    }

    showPropertyPanel(marker) {
        const panel = document.getElementById('propertyPanel');
        const title = document.getElementById('propertyTitle');
        const content = document.getElementById('propertyContent');

        if (!panel) return;

        title.textContent = marker.name;

        // Build sensor details HTML with 7-day animation
        let sensorDetailsHTML = '';
        if (marker.sensor_count && marker.sensor_count > 0) {
            const sensorRows = marker.sensors.map((s, idx) => {
                const hasHistory = s.history && s.history.length > 0;
                const icon = this.getSensorIcon(s.type);
                return `
                <div class="sensor-row-animated" data-sensor-idx="${idx}" style="display: flex; align-items: center; padding: 8px; border-bottom: 1px solid #e0e0e0;">
                    <span class="sensor-icon" style="font-size: 16px; margin-right: 6px;">${icon}</span>
                    <span class="sensor-type" style="flex: 0 0 120px; font-size: 12px; color: #555;">${s.type.replace(/_/g, ' ')}</span>
                    <div class="sensor-bar-container" style="flex: 1; display: flex; align-items: center; gap: 8px; position: relative; height: 20px;">
                        <div class="sensor-bar" data-sensor="${idx}" style="position: absolute; left: 0; height: 6px; border-radius: 3px; background: #999; min-width: 2px;"></div>
                        <span class="sensor-bar-value" style="position: absolute; right: 0; font-size: 11px; font-weight: 600; color: #2196F3; font-family: 'Courier New', monospace;">${s.value !== null ? s.value + ' ' + s.unit : 'N/A'}</span>
                    </div>
                </div>
            `}).join('');

            sensorDetailsHTML = `
            <div class="result-item">
                <span class="label">Marker ID:</span>
                <span class="value">${marker.id}</span>
            </div>
            <div class="result-item">
                <span class="label">Sensors:</span>
                <span class="value">${marker.sensor_count} active (7-day history)</span>
            </div>
            <div class="sensor-summary">
                <h4 style="margin: 10px 0 5px 0; font-size: 13px; color: #666;">Sensor Readings:</h4>
                <div class="sensor-list" style="max-height: 300px; overflow-y: auto;">
                    ${sensorRows}
                </div>
            </div>
            `;
        } else {
            sensorDetailsHTML = `
            <div class="result-item">
                <span class="label">Marker ID:</span>
                <span class="value">${marker.id}</span>
            </div>
            <div class="result-item">
                <span class="label">Sensors:</span>
                <span class="value">No sensors attached</span>
            </div>
            `;
        }

        const html = `
            <div class="result-item">
                <span class="label">Type:</span>
                <span class="value">${marker.type.replace(/_/g, ' ').toUpperCase()}</span>
            </div>
            <div class="result-item">
                <span class="label">Priority:</span>
                <span class="value">${marker.priority}</span>
            </div>
            <div class="result-item">
                <span class="label">Location:</span>
                <span class="value">${marker.lat.toFixed(6)}°N, ${marker.lon.toFixed(6)}°E</span>
            </div>
            <div class="result-item">
                <span class="label">Status:</span>
                <span class="value">ACTIVE</span>
            </div>
            ${marker.description ? `
            <div class="result-item">
                <span class="label">Description:</span>
                <span class="value">${marker.description}</span>
            </div>
            ` : ''}
            ${sensorDetailsHTML}
        `;

        content.innerHTML = html;
        panel.classList.remove('hidden');

        // Start 7-day animation for sensors
        if (marker.sensor_count && marker.sensor_count > 0) {
            this.animate7DaySensors(marker.sensors);
        }
    }

    animate7DaySensors(sensors) {
        const dayDuration = 400; // ms per day
        const lastDayPause = 1000; // pause on last day

        sensors.forEach((sensor, sensorIdx) => {
            if (!sensor.history || sensor.history.length === 0) return;

            const barElement = document.querySelector(`.sensor-bar[data-sensor="${sensorIdx}"]`);
            const valueElement = barElement?.nextElementSibling;
            if (!barElement) return;

            // Get max value for scaling
            const maxVal = Math.max(...sensor.history.map(h => h.value || 0));

            let currentDay = 0;

            const animateDay = () => {
                if (currentDay >= sensor.history.length) {
                    // Loop back to day 0
                    currentDay = 0;
                    setTimeout(animateDay, lastDayPause);
                    return;
                }

                const dayData = sensor.history[currentDay];
                const value = dayData.value || 0;
                const widthPercent = maxVal > 0 ? (value / maxVal) * 100 : 0;

                // Get sensor color
                const sensorColor = this.getSensorColor(sensor.type);
                barElement.style.width = widthPercent + '%';
                barElement.style.backgroundColor = sensorColor;
                barElement.style.transition = 'width 0.3s ease';

                if (valueElement) {
                    valueElement.textContent = `${value} ${sensor.unit}`;
                }

                currentDay++;
                const delay = (currentDay === sensor.history.length) ? lastDayPause : dayDuration;
                setTimeout(animateDay, delay);
            };

            animateDay();
        });
    }

    getSensorIcon(sensorType) {
        const icons = {
            // Boom Trap sensors
            'loadcell': '⚖️',
            'integrity': '🔧',
            'waterlevel': '🌊',
            'flowvelocity': '💨',
            'camera': '📹',
            'vibration': '📳',
            'gps_drift': '🛰️',
            'powerusage': '🔋',
            // Water Quality sensors
            'turbidity': '☁️',
            'heavymetals': '☢️',
            'ph': '🧪',
            'ph_sensor': '🧪',
            'dissolvedoxygen': '💧',
            'dissolved_oxygen': '💧',
            'temperature': '🌡️',
            'conductivity': '⚡',
            'nitrate': '🧬',
            'phosphate': '💎',
            'depth_gauge': '📏',
            'flow_meter': '🌊',
            'water_quality': '💧',
            // Biodiversity sensors
            'aicamera': '📷',
            'pirmotion': '👁️',
            'thermalcamera': '🔥',
            'audiorecorder': '🎤',
            'ultrasonic': '🦇',
            'ndvi': '🌿',
            'soilmoisture': '🌱',
            'canopy_height': '🌳',
            // Biochar Facility sensors
            'feedstock_mass': '🪵',
            'biochar_yield': '⚫',
            'pyrolysis_temp': '🔥',
            'carbon_content': '💨'
        };
        return icons[sensorType] || '📊';
    }

    getSensorColor(sensorType) {
        const colors = {
            'conductivity': '#4ECDC4',
            'depth_gauge': '#4FC3F7',
            'dissolved_oxygen': '#44AAFF',
            'flow_meter': '#2196F3',
            'ph_sensor': '#FF9944',
            'temperature': '#FF6B35',
            'turbidity': '#95E1D3',
            'water_quality': '#44FF44'
        };
        return colors[sensorType] || '#999';
    }

    render() {
        // Clear canvas
        this.ctx.fillStyle = '#E8E8E8';
        this.ctx.fillRect(0, 0, this.width, this.height);

        this.ctx.save();

        // ================================================================
        // DRAW BACKGROUND IMAGE
        // ================================================================
        if (this.showBackground && this.bgLoaded) {
            this.drawBackground();
        }

        // Draw river geometry (with overlay scale applied)
        if (this.showRiver) {
            this.drawRiver();
        }

        // Draw markers (with overlay scale applied)
        if (this.showMarkers) {
            this.pulsePhase += 0.05;
            this.drawMarkers();
        }

        this.ctx.restore();

        // Draw scale indicator
       // this.drawScale();

        // Continue animation
        this.animationFrame = requestAnimationFrame(() => this.render());
    }

    // ================================================================
    // BACKGROUND IMAGE DRAWING - Uses adjustment variables from top
    // ================================================================
    drawBackground() {
        const imgWidth = this.bgImage.width * this.bgScale;
        const imgHeight = this.bgImage.height * this.bgScale;

        // Center the image on canvas
        const centerX = (this.width - imgWidth) / 2;
        const centerY = (this.height - imgHeight) / 2;

        // Draw image centered with offsets applied
        this.ctx.drawImage(
            this.bgImage,
            centerX + this.bgOffsetX,  // ← X position (centered + your offset)
            centerY + this.bgOffsetY,  // ← Y position (centered + your offset)
            imgWidth,                  // ← Width (controlled by bgScale)
            imgHeight                  // ← Height (controlled by bgScale)
        );
    }

    drawRiver() {
        if (!this.riverGeometry || this.riverGeometry.length === 0) {
            console.log('No river geometry to draw');
            return;
        }

        console.log('Drawing river, polygons:', this.riverGeometry.length);
        const centerX = this.width / 2;
        const centerY = this.height / 2;

        for (let polygon of this.riverGeometry) {
            for (let ring of polygon) {
                if (ring.length < 3) continue;

                this.ctx.beginPath();
                const [lon0, lat0] = ring[0];
                const [x0, y0] = this.latLonToScreen(lon0, lat0, this.riverScale, true);
                this.ctx.moveTo(x0, y0);

                for (let i = 1; i < ring.length; i++) {
                    const [lon, lat] = ring[i];
                    const [x, y] = this.latLonToScreen(lon, lat, this.riverScale, true);
                    this.ctx.lineTo(x, y);
                }

                this.ctx.closePath();
                this.ctx.fillStyle = '#4FC3F7AA';
                this.ctx.fill();

                this.ctx.strokeStyle = '#2196F3';
                this.ctx.lineWidth = 2;
                this.ctx.stroke();
            }
        }
    }

    drawMarkers() {
        for (let marker of this.markers) {
            if (this.markerTypeVisibility[marker.type]) {
                this.drawMarker(marker);
            }
        }
    }

    drawMarker(marker) {
        const [x, y] = this.latLonToScreen(marker.lon, marker.lat, this.overlayScale);

        let baseSize = 8;
        if (marker.priority === 'HIGH') baseSize = 10;
        if (marker.priority === 'LOW') baseSize = 6;

        const pulseSize = 2 + Math.sin(this.pulsePhase / marker.pulse_rate + marker.id * 0.3) * 1.5;

        // Outer glow
        this.ctx.beginPath();
        this.ctx.arc(x, y, baseSize + pulseSize + 4, 0, Math.PI * 2);
        this.ctx.fillStyle = marker.color + '40';
        this.ctx.fill();

        // Middle ring
        this.ctx.beginPath();
        this.ctx.arc(x, y, baseSize + 2, 0, Math.PI * 2);
        this.ctx.fillStyle = marker.color + '80';
        this.ctx.fill();

        // Core
        this.ctx.beginPath();
        this.ctx.arc(x, y, baseSize, 0, Math.PI * 2);
        this.ctx.fillStyle = marker.color;
        this.ctx.fill();

        // White center
        this.ctx.beginPath();
        this.ctx.arc(x, y, 3, 0, Math.PI * 2);
        this.ctx.fillStyle = '#fff';
        this.ctx.fill();

        // Selected highlight
        if (this.selectedMarker && this.selectedMarker.id === marker.id) {
            this.ctx.beginPath();
            this.ctx.arc(x, y, baseSize + 6, 0, Math.PI * 2);
            this.ctx.strokeStyle = '#fff';
            this.ctx.lineWidth = 2;
            this.ctx.stroke();
        }
    }

    drawScale() {
        const scaleText = `Scale: ${(this.scale / 1000).toFixed(1)}k`;
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        this.ctx.fillRect(10, this.height - 40, 120, 30);
        this.ctx.fillStyle = '#fff';
        this.ctx.font = '14px monospace';
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText(scaleText, 20, this.height - 25);

        const countText = `${this.markers.length} markers`;
        this.ctx.fillRect(140, this.height - 40, 120, 30);
        this.ctx.fillText(countText, 150, this.height - 25);
    }

    destroy() {
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
        }
    }
}

// Global viewer instance
let realRiverViewer = null;

function initRealViewer() {
    console.log('🚀 initRealViewer() called - NEW VERSION LOADED');
    realRiverViewer = new RealRiverViewer('riverMap');

    document.getElementById('closeProperty')?.addEventListener('click', () => {
        document.getElementById('propertyPanel')?.classList.add('hidden');
    });
}
/* Updated: Thu Dec 11 09:08:34 AM +08 2025 */
