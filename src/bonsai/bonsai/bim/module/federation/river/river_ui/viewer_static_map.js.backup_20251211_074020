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

        // ================================================================
        // ========== BACKGROUND IMAGE ALIGNMENT - ADJUST HERE ===========
        // ================================================================
        
        // IMAGE FILE: Put your map image in same folder or adjust path
        this.bgImageSrc = 'map_klang_valley.png';  // ← Your image file
        
        // POSITION: Move image left/right, up/down (in pixels)
        this.bgOffsetX = 0;    // ← Positive = move image RIGHT
        this.bgOffsetY = 0;    // ← Positive = move image DOWN
        
        // SCALE: Make image bigger/smaller (1.0 = original size)
        this.bgScale = 0.7;    // ← 1.2 = 20% bigger, 0.8 = 20% smaller
        
        // ================================================================
        
        this.bgImage = null;
        this.bgLoaded = false;

        // Data
        this.riverGeometry = null;
        this.markers = [];
        this.selectedMarker = null;

        // Display options
        this.showRiver = true;
        this.showMarkers = true;
        this.showBackground = true;

        // Overlay scale multiplier (make river/sensors 2x larger)
        this.overlayScale = 2.0;

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
            // Load river geometry from Blender database
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
            console.log(`  River: 1 feature`);
            console.log(`  Markers: ${this.markers.length}`);

        } catch (error) {
            console.error('Error loading data:', error);
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
        // Actual river extent from database
        this.bounds.lon_min = 101.309;
        this.bounds.lon_max = 101.589;
        this.bounds.lat_min = 2.987;
        this.bounds.lat_max = 3.096;
        this.fitToView();
    }

    fitToView() {
        const lon_range = this.bounds.lon_max - this.bounds.lon_min;
        const lat_range = this.bounds.lat_max - this.bounds.lat_min;

        const scaleX = this.width / lon_range;
        const scaleY = this.height / lat_range;
        this.scale = Math.min(scaleX, scaleY) * 0.47;  // Keep original zoom level

        // Center the river, shifted up
        const centerLon = this.bounds.lon_min + lon_range / 2;
        const centerLat = this.bounds.lat_min + lat_range / 2;

        this.offsetX = this.width / 2 - centerLon * this.scale;
        this.offsetY = (this.height / 2 - 30) + centerLat * this.scale;  // +120 shifts up more
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

    latLonToScreen(lon, lat, applyOverlayScale = false) {
        const x = this.offsetX + lon * this.scale;
        const y = this.offsetY - lat * this.scale;

        // If overlay scale requested, scale around canvas center
        if (applyOverlayScale) {
            const centerX = this.width / 2;
            const centerY = this.height / 2;
            return [
                centerX + (x - centerX) * this.overlayScale,
                centerY + (y - centerY) * this.overlayScale
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
            const scaleX = this.canvas.width / rect.width;
            const scaleY = this.canvas.height / rect.height;
            const mouseX = (e.clientX - rect.left) * scaleX;
            const mouseY = (e.clientY - rect.top) * scaleY;
            this.handleMarkerClick(mouseX, mouseY);
        });

        // Zoom
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const zoomFactor = e.deltaY > 0 ? 0.995 : 1.005;
            this.zoomTowardsCenter(zoomFactor);
        });

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
            const [x, y] = this.latLonToScreen(marker.lon, marker.lat, true);
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
            const [x, y] = this.latLonToScreen(marker.lon, marker.lat, true);
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
        this.drawScale();

        // Continue animation
        this.animationFrame = requestAnimationFrame(() => this.render());
    }

    // ================================================================
    // BACKGROUND IMAGE DRAWING - Uses adjustment variables from top
    // ================================================================
    drawBackground() {
        const imgWidth = this.bgImage.width * this.bgScale;
        const imgHeight = this.bgImage.height * this.bgScale;
        
        // Draw image with offsets applied
        this.ctx.drawImage(
            this.bgImage,
            this.bgOffsetX,           // ← X position (adjust at top of file)
            this.bgOffsetY,           // ← Y position (adjust at top of file)
            imgWidth,                 // ← Width (controlled by bgScale)
            imgHeight                 // ← Height (controlled by bgScale)
        );
    }

    drawRiver() {
        for (let polygon of this.riverGeometry) {
            for (let ring of polygon) {
                if (ring.length < 3) continue;

                this.ctx.beginPath();
                const [lon0, lat0] = ring[0];
                const [x0, y0] = this.latLonToScreen(lon0, lat0, true);
                this.ctx.moveTo(x0, y0);

                for (let i = 1; i < ring.length; i++) {
                    const [lon, lat] = ring[i];
                    const [x, y] = this.latLonToScreen(lon, lat, true);
                    this.ctx.lineTo(x, y);
                }

                this.ctx.closePath();
                this.ctx.fillStyle = '#4FC3F7AA';
                this.ctx.fill();

                this.ctx.strokeStyle = '#2196F3';
                this.ctx.lineWidth = 1 / this.scale * 1000;
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
        const [x, y] = this.latLonToScreen(marker.lon, marker.lat, true);

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
    realRiverViewer = new RealRiverViewer('riverMap');

    document.getElementById('closeProperty')?.addEventListener('click', () => {
        document.getElementById('propertyPanel')?.classList.add('hidden');
    });
}
