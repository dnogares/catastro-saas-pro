/**
 * CATASTRO SaaS Pro - Frontend Controller
 */

const AppState = {
    currentRef: null,
    currentData: null,
    logoB64: null,
    isMapLoaded: false
};

const MapManager = {
    map: null,
    layers: {
        parcela: null,
        afecciones: L.layerGroup()
    },

    init() {
        this.map = L.map('main-map', { zoomControl: false }).setView([40.41, -3.70], 6);

        const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(this.map);
        const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", {
            layers: 'OI.OrthoimageCoverage',
            format: 'image/png',
            transparent: true,
            attribution: "IGN España"
        });

        L.control.layers({ "Mapa": osm, "Satélite": pnoa }, {}, { position: 'bottomright' }).addTo(this.map);
        L.control.zoom({ position: 'bottomright' }).addTo(this.map);
        this.layers.afecciones.addTo(this.map);
        AppState.isMapLoaded = true;
    },

    drawParcel(geojson) {
        if (this.layers.parcela) this.map.removeLayer(this.layers.parcela);
        this.layers.parcela = L.geoJSON(geojson, {
            style: { color: '#e53e3e', weight: 4, fillOpacity: 0.2, dashArray: '5, 10' }
        }).addTo(this.map);
        this.map.fitBounds(this.layers.parcela.getBounds(), { padding: [50, 50] });
    }
};

const UIActions = {
    init() {
        // Buscador
        document.getElementById('btn-buscar').onclick = () => this.runAnalysis();
        document.getElementById('ref-input').onkeypress = (e) => { if(e.key === 'Enter') this.runAnalysis(); };

        // Logo
        this.setupLogoHandler();

        // PDF
        document.getElementById('btn-generate-pdf').onclick = () => this.generatePDF();
    },

    async runAnalysis() {
        const ref = document.getElementById('ref-input').value.trim().toUpperCase();
        if (ref.length < 14) return alert("Referencia Catastral no válida");

        const btn = document.getElementById('btn-buscar');
        btn.innerHTML = "⌛";
        
        try {
            const fd = new FormData();
            fd.append('ref', ref);

            const response = await fetch('http://localhost:8000/api/analizar-referencia', { method: 'POST', body: fd });
            const result = await response.json();

            if (result.status === 'success') {
                AppState.currentRef = ref;
                AppState.currentData = result.datos;
                MapManager.drawParcel(result.geojson);
                this.updateAfeccionesPanel(result.datos.zonas_afectadas);
            }
        } catch (error) {
            console.error("Error en análisis:", error);
            alert("Error conectando con el servidor Python");
        } finally {
            btn.innerHTML = "🔍";
        }
    },

    updateAfeccionesPanel(afecciones) {
        const container = document.getElementById('afecciones-container');
        if (!afecciones || afecciones.length === 0) {
            container.innerHTML = '<p class="text-xs text-muted">Sin afecciones detectadas en esta parcela.</p>';
            return;
        }

        container.innerHTML = afecciones.map(af => `
            <div class="afeccion-card mb-sm p-sm" style="border-left: 4px solid #e53e3e; background: rgba(255,255,255,0.4)">
                <div class="text-xs font-bold">${af.capa || 'Normativa'}</div>
                <div class="text-xs">${af.nota}</div>
            </div>
        `).join('');
    },

    setupLogoHandler() {
        const dropZone = document.getElementById('logo-drop');
        dropZone.onclick = () => {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = 'image/*';
            input.onchange = (e) => {
                const reader = new FileReader();
                reader.onload = (ev) => {
                    AppState.logoB64 = ev.target.result;
                    dropZone.innerHTML = `<img src="${ev.target.result}" style="max-height:100%; border-radius:4px">`;
                };
                reader.readAsDataURL(e.target.files[0]);
            };
            input.click();
        };
    },

    async generatePDF() {
        if (!AppState.currentRef) return alert("Primero analice una referencia");
        
        const btn = document.getElementById('btn-generate-pdf');
        const originalText = btn.innerHTML;
        btn.innerHTML = "⌛ GENERANDO PDF...";
        btn.disabled = true;

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

            if (res.ok) {
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Informe_${AppState.currentRef}.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
            } else {
                throw new Error("Error en el servidor");
            }
        } catch (e) {
            alert("Error al generar el PDF");
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    MapManager.init();
    UIActions.init();
});
