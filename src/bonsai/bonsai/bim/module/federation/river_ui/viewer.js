/**
 * Klang River Interactive Viewer
 * Canvas-based map with pulsing markers and river visualization
 */

class RiverViewer {
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

        // Animation
        this.pulsePhase = 0;
        this.animationFrame = null;

        // Data
        this.markers = [];
        this.riverPath = [];
        this.selectedMarker = null;

        this.initializeData();
        this.setupEventListeners();
        this.render();
    }

    initializeData() {
        // Generate 40+ markers along Klang River (56km)
        const stretches = calculateWorkloadByStretch(40);
        this.markers = stretches.map((stretch, idx) => {
            // Create river path with slight curves
            const progress = idx / 40;
            const x = 100 + (this.width - 200) * progress;
            const y = this.height / 2 + Math.sin(progress * Math.PI * 3) * 80;

            this.riverPath.push({ x, y });

            return {
                id: stretch.id,
                name: stretch.name,
                x: x,
                y: y,
                priority: stretch.priority,
                km: stretch.km_start,
                data: stretch
            };
        });
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
                // Check hover
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

        // Zoom
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            const newScale = this.scale * delta;
            if (newScale >= 0.5 && newScale <= 3.0) {
                this.scale = newScale;
            }
        });

        // Reset view button
        document.getElementById('resetView')?.addEventListener('click', () => {
            this.offsetX = 0;
            this.offsetY = 0;
            this.scale = 1.0;
        });
    }

    checkMarkerHover(mouseX, mouseY) {
        const worldX = (mouseX - this.offsetX) / this.scale;
        const worldY = (mouseY - this.offsetY) / this.scale;

        for (let marker of this.markers) {
            const dist = Math.sqrt((worldX - marker.x) ** 2 + (worldY - marker.y) ** 2);
            if (dist < 15) {
                this.canvas.style.cursor = 'pointer';
                return;
            }
        }
        this.canvas.style.cursor = this.isDragging ? 'grabbing' : 'grab';
    }

    handleMarkerClick(mouseX, mouseY) {
        const worldX = (mouseX - this.offsetX) / this.scale;
        const worldY = (mouseY - this.offsetY) / this.scale;

        for (let marker of this.markers) {
            const dist = Math.sqrt((worldX - marker.x) ** 2 + (worldY - marker.y) ** 2);
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
                <span class="label">Location:</span>
                <span class="value">km ${marker.km.toFixed(1)} - ${(marker.km + 1.4).toFixed(1)}</span>
            </div>
            <div class="result-item">
                <span class="label">Priority:</span>
                <span class="value">${marker.priority}</span>
            </div>
            <div class="result-item">
                <span class="label">Dredging Volume:</span>
                <span class="value">${marker.data.dredging_m3.toLocaleString()} m³</span>
            </div>
            <div class="result-item">
                <span class="label">Excavator Days:</span>
                <span class="value">${marker.data.excavator_days} days</span>
            </div>
            <div class="result-item">
                <span class="label">Labor Required:</span>
                <span class="value">${marker.data.labor_days} person-days</span>
            </div>
            <div class="result-item">
                <span class="label">Boom Sites:</span>
                <span class="value">${marker.data.boom_sites}</span>
            </div>
            <div class="result-item">
                <span class="label">Phase:</span>
                <span class="value">Phase ${marker.data.phase}</span>
            </div>
        `;

        content.innerHTML = html;
        panel.classList.remove('hidden');
    }

    render() {
        // Clear canvas
        this.ctx.clearRect(0, 0, this.width, this.height);

        // Save context
        this.ctx.save();

        // Apply transform
        this.ctx.translate(this.offsetX, this.offsetY);
        this.ctx.scale(this.scale, this.scale);

        // Draw river path
        this.drawRiverPath();

        // Draw markers with pulse animation
        this.pulsePhase += 0.05;
        this.drawMarkers();

        // Restore context
        this.ctx.restore();

        // Draw UI overlays (in screen space)
        this.drawScale();

        // Continue animation
        this.animationFrame = requestAnimationFrame(() => this.render());
    }

    drawRiverPath() {
        if (this.riverPath.length < 2) return;

        // River outline (wider)
        this.ctx.strokeStyle = '#1565c0';
        this.ctx.lineWidth = 24;
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        this.ctx.beginPath();
        this.ctx.moveTo(this.riverPath[0].x, this.riverPath[0].y);
        for (let i = 1; i < this.riverPath.length; i++) {
            this.ctx.lineTo(this.riverPath[i].x, this.riverPath[i].y);
        }
        this.ctx.stroke();

        // River center (water color)
        this.ctx.strokeStyle = '#42a5f5';
        this.ctx.lineWidth = 16;

        this.ctx.beginPath();
        this.ctx.moveTo(this.riverPath[0].x, this.riverPath[0].y);
        for (let i = 1; i < this.riverPath.length; i++) {
            this.ctx.lineTo(this.riverPath[i].x, this.riverPath[i].y);
        }
        this.ctx.stroke();

        // Draw km markers along path
        this.ctx.fillStyle = '#fff';
        this.ctx.font = '10px monospace';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';

        for (let i = 0; i < this.riverPath.length; i += 5) {
            const point = this.riverPath[i];
            const km = Math.round(i * 1.4);
            this.ctx.fillText(`${km}km`, point.x, point.y - 20);
        }
    }

    drawMarkers() {
        for (let marker of this.markers) {
            this.drawMarker(marker);
        }
    }

    drawMarker(marker) {
        // Determine color
        let color;
        switch (marker.priority) {
            case 'HIGH':
                color = '#f44336';
                break;
            case 'MEDIUM':
                color = '#ff9800';
                break;
            case 'LOW':
                color = '#4caf50';
                break;
            default:
                color = '#2196f3';
        }

        // Pulse animation
        const pulseSize = 3 + Math.sin(this.pulsePhase + marker.id * 0.5) * 2;

        // Outer glow (pulsing)
        this.ctx.beginPath();
        this.ctx.arc(marker.x, marker.y, 12 + pulseSize, 0, Math.PI * 2);
        this.ctx.fillStyle = color + '40'; // 25% opacity
        this.ctx.fill();

        // Middle ring
        this.ctx.beginPath();
        this.ctx.arc(marker.x, marker.y, 10, 0, Math.PI * 2);
        this.ctx.fillStyle = color + '80'; // 50% opacity
        this.ctx.fill();

        // Core marker
        this.ctx.beginPath();
        this.ctx.arc(marker.x, marker.y, 7, 0, Math.PI * 2);
        this.ctx.fillStyle = color;
        this.ctx.fill();

        // White center dot
        this.ctx.beginPath();
        this.ctx.arc(marker.x, marker.y, 3, 0, Math.PI * 2);
        this.ctx.fillStyle = '#fff';
        this.ctx.fill();

        // Highlight selected
        if (this.selectedMarker && this.selectedMarker.id === marker.id) {
            this.ctx.beginPath();
            this.ctx.arc(marker.x, marker.y, 15, 0, Math.PI * 2);
            this.ctx.strokeStyle = '#fff';
            this.ctx.lineWidth = 2;
            this.ctx.stroke();
        }
    }

    drawScale() {
        const scaleText = `Scale: ${(this.scale * 100).toFixed(0)}%`;
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        this.ctx.fillRect(10, this.height - 40, 120, 30);
        this.ctx.fillStyle = '#fff';
        this.ctx.font = '14px monospace';
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText(scaleText, 20, this.height - 25);
    }

    destroy() {
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
        }
    }
}

// Initialize viewer when DOM is ready
let riverViewer = null;

document.addEventListener('DOMContentLoaded', () => {
    riverViewer = new RiverViewer('riverMap');

    // Close property panel button
    document.getElementById('closeProperty')?.addEventListener('click', () => {
        document.getElementById('propertyPanel')?.classList.add('hidden');
    });
});

// Export data functions (for CSV/GeoJSON)
function exportToCSV(data, filename) {
    const csv = convertToCSV(data);
    downloadFile(csv, filename, 'text/csv');
}

function exportToGeoJSON(markers) {
    const geojson = {
        type: 'FeatureCollection',
        features: markers.map(m => ({
            type: 'Feature',
            geometry: {
                type: 'Point',
                coordinates: [101.4 + (m.id * 0.01), 3.0 + (m.id * 0.01)]
            },
            properties: {
                id: m.id,
                name: m.name,
                priority: m.priority,
                km: m.km,
                dredging_m3: m.data.dredging_m3,
                excavator_days: m.data.excavator_days,
                labor_days: m.data.labor_days
            }
        }))
    };
    return geojson;
}

function convertToCSV(objArray) {
    const array = typeof objArray !== 'object' ? JSON.parse(objArray) : objArray;
    let csv = '';

    // Header
    const headers = Object.keys(array[0]);
    csv += headers.join(',') + '\n';

    // Rows
    for (let item of array) {
        const values = headers.map(header => {
            const val = item[header];
            return typeof val === 'string' ? `"${val}"` : val;
        });
        csv += values.join(',') + '\n';
    }

    return csv;
}

function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}
