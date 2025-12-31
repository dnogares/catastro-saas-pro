/**
 * CATASTRO SaaS Pro - Frontend Engine v2.0
 * Arquitectura basada en módulos para gestión de tarjetas y mapa
 */

const AppState = {
    currentRef: null,
    currentData: null,
    logoB64: null,
    isProcessing: false,
    layers: {
        parcela: null,
        afecciones: L.layerGroup()
    }
};

const MapManager = {
    map: null,

    init() {
        // Inicializar Leaflet centrado en España
        this.map = L.map('main-map', { zoomControl: false }).setView([40.41, -3.70], 6);

        // Capa Base: Callejero
        const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap'
        }).addTo(this.map);

        // Capa Satélite: PNOA (IGN)
        const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", {
            layers: 'OI.OrthoimageCoverage',
            format: 'image/png',
            transparent: true,
            attribution: "IGN España"
        });

        // Controles posicionados para no tapar tarjetas
        L.control.layers({ "Mapa": osm, "Satélite PNOA": pnoa }, {}, { position: 'bottomright' }).addTo(this.map);
        L.control.zoom({ position: 'bottomright' }).addTo(this.map);
        
        AppState.layers.afecciones.addTo(this.map);
    },

    drawParcel(geojson) {
        if (AppState.layers.parcela) this.map.removeLayer(AppState.layers.parcela);
        
        AppState.layers.parcela = L.geoJSON(geojson, {
            style: { color: '#e53e3e', weight: 4, fillOpacity: 0.1 }
        }).addTo(this.map);
        
        this.map.fitBounds(AppState.layers.parcela.getBounds(), { padding: [50, 50] });
    }
};

const UIManager = {
    init() {
        // Buscar por referencia
        document.getElementById('btn-buscar').onclick = () => this.ejecutarAnalisis();
        document.getElementById('ref-input').onkeypress = (e) => { if(e.key === 'Enter') this.ejecutarAnalisis(); };

        // Gestión de Logo (Drag & Drop)
        this.setupLogoUpload();

        // Botón PDF
        document.getElementById('btn-generate-pdf').onclick = () => this.generarInforme();
    },

    async ejecutarAnalisis() {
        const ref = document.getElementById('ref-input').value.toUpperCase();
        if (ref.length < 14) return alert("Referencia Catastral no válida");

        this.setLoading(true);
        try {
            const formData = new FormData();
            formData.append('ref', ref);

            const response = await fetch('http://localhost:8000/api/analizar-referencia', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();

            if (data.status === 'success') {
                AppState.currentRef = ref;
                AppState.currentData = data.datos;
                MapManager.drawParcel(data.geojson);
                this.renderAfecciones(data.datos.zonas_afectadas);
            }
        } catch (error) {
            console.error("Error analizando:", error);
        } finally {
            this.setLoading(false);
        }
    },

    renderAfecciones(lista) {
        const container = document.getElementById('afecciones-container');
        container.innerHTML = lista.map(af => `
            <div class="glass-card mb-sm" style="border-left: 4px solid #e53e3e; padding: 10px;">
                <div class="text-sm font-bold">${af.capa || 'Afección Técnica'}</div>
                <div class="text-xs text-muted">${af.nota}</div>
            </div>
        `).join('') || '<p class="text-xs">Sin afecciones detectadas.</p>';
    },

    setupLogoUpload() {
        const dropZone = document.getElementById('logo-drop');
        dropZone.onclick = () => {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = 'image/*';
            input.onchange = (e) => this.handleImage(e.target.files[0]);
            input.click();
        };
    },

    handleImage(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            AppState.logoB64 = e.target.result;
            document.getElementById('logo-drop').innerHTML = `<img src="${AppState.logoB64}" style="max-height: 100%; max-width: 100%;">`;
        };
        reader.readAsDataURL(file);
    },

    async generarInforme() {
        if (!AppState.currentRef) return alert("Realice un análisis primero");
        
        const btn = document.getElementById('btn-generate-pdf');
        btn.innerText = "⌛ Generando...";
        
        const payload = {
            ref: AppState.currentRef,
            tecnico: document.getElementById('rep-author').value,
            colegiado: document.getElementById('rep-id').value,
            notas: document.getElementById('report-notes')?.value || "",
            logo: AppState.logoB64,
            datos: AppState.currentData
        };

        try {
            const res = await fetch('http://localhost:8000/api/generar-pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `INFORME_${AppState.currentRef}.pdf`;
            a.click();
        } catch (e) { alert("Error al generar PDF"); }
        finally { btn.innerText = "📄 GENERAR INFORME PDF"; }
    },

    setLoading(val) {
        AppState.isProcessing = val;
        document.getElementById('btn-buscar').innerText = val ? "..." : "🔍";
    }
};

document.addEventListener('DOMContentLoaded', () => {
    MapManager.init();
    UIManager.init();
});
