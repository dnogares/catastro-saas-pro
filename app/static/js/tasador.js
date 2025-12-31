/**
 * CATASTRO SaaS Pro v2 - Dashboard Envolvente
 */

const AppState = {
    isProcessing: false,
    currentRef: null,
    layers: {
        parcela: null,
        afecciones: null
    }
};

const MapViewer = {
    map: null,
    
    init() {
        // Inicializar mapa centrado en España
        this.map = L.map('main-map', {
            zoomControl: false // Lo movemos para que no estorbe a las tarjetas
        }).setView([40.4167, -3.7037], 6);

        // Capa Base: OpenStreetMap
        const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap'
        }).addTo(this.map);

        // Capa Satélite: PNOA (IGN España)
        const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", {
            layers: 'OI.OrthoimageCoverage',
            format: 'image/png',
            transparent: true,
            attribution: "IGN España"
        });

        // Control de capas
        L.control.layers({ "Callejero": osm, "Satélite": pnoa }, {}, { position: 'bottomright' }).addTo(this.map);
        L.control.zoom({ position: 'bottomright' }).addTo(this.map);
        
        console.log("[MapViewer] Leaflet listo");
    },

    // Dibuja el GeoJSON resultante de tus scripts de Python
    drawGeoJSON(data, type = 'parcela') {
        if (this.layers[type]) this.map.removeLayer(this.layers[type]);

        this.layers[type] = L.geoJSON(data, {
            style: function(feature) {
                return {
                    color: type === 'parcela' ? '#ff0000' : '#e53e3e',
                    weight: 3,
                    fillOpacity: 0.2,
                    dashArray: type === 'parcela' ? '' : '5, 5'
                };
            },
            onEachFeature: (f, l) => {
                if (f.properties) {
                    l.bindPopup(`<b>${type.toUpperCase()}:</b><br>${JSON.stringify(f.properties)}`);
                }
            }
        }).addTo(this.map);

        this.map.fitBounds(this.layers[type].getBounds());
    }
};

// Módulo para interactuar con tus scripts de Python (Flask/FastAPI)
const API = {
    async procesarKML(file) {
        const formData = new FormData();
        formData.append('file', file);
        // Aquí llamarías a tu endpoint que usa AdvancedAnalysisModule
        const response = await fetch('/api/advanced-analysis', { method: 'POST', body: formData });
        return await response.json();
    },

    async consultarCatastro(ref) {
        // Aquí llamarías a tu script de urban_analysis.py
        const response = await fetch(`/api/urban-analysis?ref=${ref}`);
        return await response.json();
    }
};

// Interfaz de Usuario (UI)
const UI = {
    init() {
        // Listener para Referencia Catastral
        document.getElementById('ref-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.ejecutarAnalisisCatastral();
        });

        // Dropzone para KML
        const kmlInput = document.getElementById('kml-input');
        kmlInput.addEventListener('change', (e) => this.manejarSubidaKML(e));

        // Logo Preview
        const logoDrop = document.getElementById('logo-drop');
        logoDrop.addEventListener('click', () => {
            // Lógica para disparar input de imagen
            console.log("Subiendo logo...");
        });
    },

    async ejecutarAnalisisCatastral() {
        const ref = document.getElementById('ref-input').value;
        if (ref.length < 14) return alert("Referencia incompleta");
        
        console.log(`[UI] Analizando: ${ref}`);
        // Aquí simulas la respuesta de urban_analysis.py
        // MapViewer.drawGeoJSON(resultadoPython, 'parcela');
    }
};

// Arrancar todo al cargar la página
document.addEventListener('DOMContentLoaded', () => {
    MapViewer.init();
    UI.init();
});
