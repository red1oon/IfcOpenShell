/**
 * Klang River Real Data Viewer
 * Loads actual GeoJSON files: river_klang.geojson + project_markers.geojson
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

        // View transform
        this.offsetX = 0;
        this.offsetY = 0;
        this.scale = 1.0;
        this.isDragging = false;
        this.lastMouseX = 0;
        this.lastMouseY = 0;

        // Data
        this.riverGeometry = null;
        this.markers = [];
        this.selectedMarker = null;
        this.buildingsGeometry = [];
        this.roadsGeometry = [];

        // Display options
        this.showRiver = true;
        this.showMarkers = true;
        this.showBuildings = false;  // Use OSM tiles instead
        this.showRoads = true;
        this.showOSMTiles = true;

        // Tile cache
        this.tileCache = {};
        this.tileSize = 256;

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

        // Map projection bounds (will be set from data)
        this.bounds = {
            lon_min: 180,
            lon_max: -180,
            lat_min: 90,
            lat_max: -90
        };

        this.loadData();
    }

    async loadData() {
        try {
            // Load background buildings
            try {
                const buildingsResponse = await fetch('../output/geojson/buildings_klang.geojson');
                const buildingsData = await buildingsResponse.json();
                this.processBuildingsData(buildingsData);
                console.log('✓ Loaded buildings');
            } catch (e) {
                console.warn('Buildings not loaded:', e);
            }

            // Load river geometry from Blender database (matches viewport shape)
            const riverResponse = await fetch('../output/geojson/river_from_blender.geojson');
            const riverData = await riverResponse.json();
            this.processRiverData(riverData);

            // Load project markers
            const markersResponse = await fetch('../output/geojson/project_markers.geojson');
            const markersData = await markersResponse.json();
            this.processMarkers(markersData);

            // Calculate bounds
            this.calculateBounds();

            // Setup event listeners
            this.setupEventListeners();

            // Start rendering
            this.render();

            console.log('✓ Loaded real Klang River data');
            console.log(`  Buildings: ${this.buildingsGeometry.length}`);
            console.log(`  River: 1 feature`);
            console.log(`  Markers: ${this.markers.length}`);
            console.log(`  Bounds: ${JSON.stringify(this.bounds)}`);

        } catch (error) {
            console.error('Error loading data:', error);
        }
    }

    processBuildingsData(geojson) {
        // Extract building polygons
        this.buildingsGeometry = [];

        const features = geojson.type === 'FeatureCollection' ? geojson.features : [geojson];

        for (let feature of features) {
            if (feature.geometry.type === 'Polygon') {
                this.buildingsGeometry.push(feature.geometry.coordinates);
            } else if (feature.geometry.type === 'MultiPolygon') {
                for (let polygon of feature.geometry.coordinates) {
                    this.buildingsGeometry.push(polygon);
                }
            }
        }
    }

    processRiverData(geojson) {
        // Extract polygon from river GeoJSON (single Feature)
        this.riverGeometry = [];

        // Handle both Feature and FeatureCollection
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
            lon: feature.geometry.coordinates[0],
            lat: feature.geometry.coordinates[1]
        }));
    }

    calculateBounds() {
        // Calculate bounds from river geometry
        for (let polygon of this.riverGeometry) {
            for (let ring of polygon) {
                for (let coord of ring) {
                    const [lon, lat] = coord;
                    this.bounds.lon_min = Math.min(this.bounds.lon_min, lon);
                    this.bounds.lon_max = Math.max(this.bounds.lon_max, lon);
                    this.bounds.lat_min = Math.min(this.bounds.lat_min, lat);
                    this.bounds.lat_max = Math.max(this.bounds.lat_max, lat);
                }
            }
        }

        // Expand slightly for padding
        const lon_range = this.bounds.lon_max - this.bounds.lon_min;
        const lat_range = this.bounds.lat_max - this.bounds.lat_min;
        const padding = 0.05;

        this.bounds.lon_min -= lon_range * padding;
        this.bounds.lon_max += lon_range * padding;
        this.bounds.lat_min -= lat_range * padding;
        this.bounds.lat_max += lat_range * padding;

        // Set initial scale to fit
        this.fitToView();
    }

    fitToView() {
        const lon_range = this.bounds.lon_max - this.bounds.lon_min;
        const lat_range = this.bounds.lat_max - this.bounds.lat_min;

        // Calculate scale to fit
        const scaleX = this.width / lon_range;
        const scaleY = this.height / lat_range;
        this.scale = Math.min(scaleX, scaleY) * 0.9; // 90% to leave margin

        // Center the view
        this.offsetX = this.width / 2 - (this.bounds.lon_min + lon_range / 2) * this.scale;
        this.offsetY = this.height / 2 + (this.bounds.lat_min + lat_range / 2) * this.scale; // Flip Y
    }

    zoomTowardsCenter(zoomFactor) {
        // Get center point in world coordinates before zoom
        const centerX = this.width / 2;
        const centerY = this.height / 2;
        const [centerLon, centerLat] = this.screenToLatLon(centerX, centerY);

        // Apply zoom
        const newScale = this.scale * zoomFactor;
        if (newScale >= 100 && newScale <= 100000) {
            this.scale = newScale;

            // Adjust offset to keep center point at same screen position
            this.offsetX = centerX - centerLon * this.scale;
            this.offsetY = centerY + centerLat * this.scale;
        }
    }

    latLonToScreen(lon, lat) {
        // Convert lat/lon to screen coordinates
        // Note: Lat is flipped (Y increases downward on screen)
        const x = this.offsetX + lon * this.scale;
        const y = this.offsetY - lat * this.scale;
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
            this.lastMouseX = e.clientX - rect.left;
            this.lastMouseY = e.clientY - rect.top;
        });

        this.canvas.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            if (this.isDragging) {
                const dx = mouseX - this.lastMouseX;
                const dy = mouseY - this.lastMouseY;
                this.offsetX += dx;
                this.offsetY += dy;
                this.lastMouseX = mouseX;
                this.lastMouseY = mouseY;
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
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            this.handleMarkerClick(mouseX, mouseY);
        });

        // Zoom (very slow fixed rate for smooth two-finger control)
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();

            // Ultra slow zoom: 0.5% per scroll event
            const delta = e.deltaY > 0 ? 0.995 : 1.005;

            const newScale = this.scale * delta;
            if (newScale >= 100 && newScale <= 100000) {
                this.scale = newScale;
            }
        });

        // Reset view button
        document.getElementById('resetView')?.addEventListener('click', () => {
            this.fitToView();
        });

        // Zoom buttons (10% per click, centered)
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
            const [x, y] = this.latLonToScreen(marker.lon, marker.lat);
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
            const [x, y] = this.latLonToScreen(marker.lon, marker.lat);
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
        `;

        content.innerHTML = html;
        panel.classList.remove('hidden');
    }

    render() {
        // Clear canvas with light background
        this.ctx.fillStyle = '#E8E8E8';
        this.ctx.fillRect(0, 0, this.width, this.height);

        // Save context
        this.ctx.save();

        // Draw OpenStreetMap tiles (background)
        if (this.showOSMTiles) {
            this.drawOSMTiles();
        }

        // Draw river geometry
        if (this.showRiver) {
            this.drawRiver();
        }

        // Draw markers with pulse animation
        if (this.showMarkers) {
            this.pulsePhase += 0.05;
            this.drawMarkers();
        }

        // Restore context
        this.ctx.restore();

        // Draw UI overlays
        this.drawScale();

        // Continue animation
        this.animationFrame = requestAnimationFrame(() => this.render());
    }

    getOSMZoomLevel() {
        // Calculate zoom based on how much lat/lon range is visible
        const [minLon, maxLat] = this.screenToLatLon(0, 0);
        const [maxLon, minLat] = this.screenToLatLon(this.width, this.height);

        const lonRange = maxLon - minLon;

        // At zoom 0, full world is 360 degrees
        // Each zoom level halves the range
        // zoom = log2(360 / lonRange)
        const zoom = Math.log2(360 / lonRange);

        return Math.max(8, Math.min(18, Math.floor(zoom)));
    }

    latLonToTile(lat, lon, zoom) {
        const n = Math.pow(2, zoom);
        const x = Math.floor(n * ((lon + 180) / 360));
        const latRad = lat * Math.PI / 180;
        const y = Math.floor(n * (1 - (Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI)) / 2);
        return [x, y];
    }

    tileToLatLon(x, y, zoom) {
        const n = Math.pow(2, zoom);
        const lon = x / n * 360 - 180;
        const latRad = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n)));
        const lat = latRad * 180 / Math.PI;
        return [lon, lat];
    }

    drawOSMTiles() {
        const zoom = this.getOSMZoomLevel();

        // Get visible bounds in lat/lon
        const [minLon, maxLat] = this.screenToLatLon(0, 0);
        const [maxLon, minLat] = this.screenToLatLon(this.width, this.height);

        // Get tile range
        const [minTileX, maxTileY] = this.latLonToTile(maxLat, minLon, zoom);
        const [maxTileX, minTileY] = this.latLonToTile(minLat, maxLon, zoom);

        // Draw tiles
        for (let x = minTileX - 1; x <= maxTileX + 1; x++) {
            for (let y = minTileY - 1; y <= maxTileY + 1; y++) {
                const tileKey = `${zoom}/${x}/${y}`;

                // Get tile top-left corner in lat/lon
                const [tileLon, tileLat] = this.tileToLatLon(x, y, zoom);
                const [tileX, tileY] = this.latLonToScreen(tileLon, tileLat);

                // Calculate tile width/height in screen pixels
                const [nextLon, nextLat] = this.tileToLatLon(x + 1, y + 1, zoom);
                const [nextX, nextY] = this.latLonToScreen(nextLon, nextLat);
                const tileWidth = Math.abs(nextX - tileX);
                const tileHeight = Math.abs(nextY - tileY);

                // Load and draw tile
                if (!this.tileCache[tileKey]) {
                    const img = new Image();
                    img.crossOrigin = 'anonymous';
                    img.src = `https://tile.openstreetmap.org/${zoom}/${x}/${y}.png`;
                    this.tileCache[tileKey] = img;
                }

                const tile = this.tileCache[tileKey];
                if (tile.complete && tile.naturalWidth > 0) {
                    this.ctx.drawImage(tile, tileX, tileY, tileWidth, tileHeight);
                }
            }
        }
    }

    drawBuildings() {
        for (let polygon of this.buildingsGeometry) {
            for (let ring of polygon) {
                if (ring.length < 3) continue;

                // Draw building footprints
                this.ctx.beginPath();
                const [lon0, lat0] = ring[0];
                const [x0, y0] = this.latLonToScreen(lon0, lat0);
                this.ctx.moveTo(x0, y0);

                for (let i = 1; i < ring.length; i++) {
                    const [lon, lat] = ring[i];
                    const [x, y] = this.latLonToScreen(lon, lat);
                    this.ctx.lineTo(x, y);
                }

                this.ctx.closePath();
                this.ctx.fillStyle = '#DDDDDD'; // Light gray
                this.ctx.fill();
                this.ctx.strokeStyle = '#BBBBBB';
                this.ctx.lineWidth = 0.5 / this.scale * 1000;
                this.ctx.stroke();
            }
        }
    }

    drawRiver() {
        for (let polygon of this.riverGeometry) {
            for (let ring of polygon) {
                if (ring.length < 3) continue;

                // Draw filled polygon
                this.ctx.beginPath();
                const [lon0, lat0] = ring[0];
                const [x0, y0] = this.latLonToScreen(lon0, lat0);
                this.ctx.moveTo(x0, y0);

                for (let i = 1; i < ring.length; i++) {
                    const [lon, lat] = ring[i];
                    const [x, y] = this.latLonToScreen(lon, lat);
                    this.ctx.lineTo(x, y);
                }

                this.ctx.closePath();
                this.ctx.fillStyle = '#4FC3F7AA'; // Blue with transparency
                this.ctx.fill();

                this.ctx.strokeStyle = '#2196F3';
                this.ctx.lineWidth = 1 / this.scale * 1000; // Scale-independent
                this.ctx.stroke();
            }
        }
    }

    drawMarkers() {
        for (let marker of this.markers) {
            // Only draw if this marker type is visible
            if (this.markerTypeVisibility[marker.type]) {
                this.drawMarker(marker);
            }
        }
    }

    drawMarker(marker) {
        const [x, y] = this.latLonToScreen(marker.lon, marker.lat);

        // Determine size based on priority
        let baseSize = 8;
        if (marker.priority === 'HIGH') baseSize = 10;
        if (marker.priority === 'LOW') baseSize = 6;

        // Pulse animation
        const pulseSize = 2 + Math.sin(this.pulsePhase / marker.pulse_rate + marker.id * 0.3) * 1.5;

        // Outer glow (pulsing)
        this.ctx.beginPath();
        this.ctx.arc(x, y, baseSize + pulseSize + 4, 0, Math.PI * 2);
        this.ctx.fillStyle = marker.color + '40'; // 25% opacity
        this.ctx.fill();

        // Middle ring
        this.ctx.beginPath();
        this.ctx.arc(x, y, baseSize + 2, 0, Math.PI * 2);
        this.ctx.fillStyle = marker.color + '80'; // 50% opacity
        this.ctx.fill();

        // Core marker
        this.ctx.beginPath();
        this.ctx.arc(x, y, baseSize, 0, Math.PI * 2);
        this.ctx.fillStyle = marker.color;
        this.ctx.fill();

        // White center dot
        this.ctx.beginPath();
        this.ctx.arc(x, y, 3, 0, Math.PI * 2);
        this.ctx.fillStyle = '#fff';
        this.ctx.fill();

        // Highlight selected
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

        // Marker count
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

// Initialize when DOM is ready (will be called from index.html)
function initRealViewer() {
    realRiverViewer = new RealRiverViewer('riverMap');

    // Close property panel button
    document.getElementById('closeProperty')?.addEventListener('click', () => {
        document.getElementById('propertyPanel')?.classList.add('hidden');
    });
}
