const AppState = {
    currentRef: null,
    afecciones: [],
    logoB64: null
};

const MapManager = {
    map: null,
    parcelLayer: null,

    init() {
        this.map = L.map('main-map', { zoomControl: false }).setView([40.41, -3.70], 6);
        
        const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(this.map);
        const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", {
            layers: 'OI.OrthoimageCoverage', format: 'image/png', transparent: true
        });

        L.control.layers({ "Callejero": osm, "Satélite": pnoa }, {}, { position: 'bottomright' }).addTo(this.map);
        L.control.zoom({ position: 'bottomright' }).addTo(this.map);
    },

    updateParcel(geojson) {
        if (this.parcelLayer) this.map.removeLayer(this.parcelLayer);
        this.parcelLayer = L.geoJSON(geojson, {
            style: { color: '#e53e3e', weight: 3, fillOpacity: 0.2 }
        }).addTo(this.map);
        this.map.fitBounds(this.parcelLayer.getBounds());
    }
};

const Actions = {
    async buscarReferencia() {
        const ref = document.getElementById('ref-input').value;
        if (!ref) return;

        try {
            const res = await fetch(`http://localhost:8000/api/analizar-referencia?ref=${ref}`, { method: 'POST' });
            const data = await res.json();
            
            if (data.status === 'success') {
                AppState.currentRef = ref;
                AppState.afecciones = data.datos.zonas_afectadas;
                MapManager.updateParcel(data.geojson);
                this.renderAfecciones();
            }
        } catch (e) { console.error("Error:", e); }
    },

    renderAfecciones() {
        const container = document.getElementById('afecciones-container');
        container.innerHTML = AppState.afecciones.map(af => `
            <div class="afeccion-item" style="border-left: 4px solid #e53e3e; margin-bottom: 8px; padding: 5px; background: rgba(255,255,255,0.5)">
                <strong>${af.capa || 'Afección'}</strong><br>
                <span class="text-xs">${af.nota}</span>
            </div>
        `).join('');
    },

    async generarPDF() {
        const body = {
            ref: AppState.currentRef,
            tecnico: document.getElementById('rep-author').value,
            colegiado: document.getElementById('rep-id').value,
            logo: AppState.logoB64
        };
        // Petición al endpoint de FastAPI (main.py)
        console.log("Generando informe para", body.ref);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    MapManager.init();
    document.getElementById('btn-buscar').onclick = () => Actions.buscarReferencia();
    document.getElementById('btn-generate-pdf').onclick = () => Actions.generarPDF();
});
