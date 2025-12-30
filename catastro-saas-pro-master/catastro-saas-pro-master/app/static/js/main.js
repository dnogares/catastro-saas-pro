document.addEventListener('DOMContentLoaded', () => {
    // Inicializar Mapa
    const map = L.map('map', { zoomControl: false }).setView([40.41, -3.70], 6);
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Capas Base
    const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
    const satelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}');
    
    // WMS Catastro (Para visualización)
    const catastroWMS = L.tileLayer.wms('https://ovc.catastro.es/ovc/wms/CP.ashx', {
        layers: 'CP.CadastralParcel',
        format: 'image/png',
        transparent: true,
        attribution: 'Dirección General del Catastro'
    }).addTo(map);

    L.control.layers({ "Mapa": osm, "Satélite": satelite }, { "Catastro": catastroWMS }).addTo(map);

    let layerParcela = null;

    // Formulario de Búsqueda
    const form = document.getElementById('consulta-form');
    const panelResultados = document.getElementById('consulta-result');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const ref = document.getElementById('referencia').value;
        
        panelResultados.innerHTML = '<div class="loader"></div><p>Analizando capas locales...</p>';

        try {
            const response = await fetch('/api/analizar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ referencia_catastral: ref })
            });
            const res = await response.json();

            if (response.ok) {
                // Dibujar parcela en el mapa
                if (layerParcela) map.removeLayer(layerParcela);
                layerParcela = L.geoJSON(res.data.geometria, {
                    style: { color: '#ff4444', weight: 3, fillOpacity: 0.4 }
                }).addTo(map);
                map.fitBounds(layerParcela.getBounds());

                // Mostrar información y botón de descarga
                let html = `
                    <div class="result-card">
                        <h3>Referencia: ${ref}</h3>
                        <a href="${res.data.pdf_url}" class="btn-download">📥 Descargar Informe PDF</a>
                        <div class="listado-afecciones">
                            <h4>Afecciones del Territorio:</h4>
                `;

                if (res.data.afecciones.length > 0) {
                    res.data.afecciones.forEach(af => {
                        // El color viene de tus CSV de leyendas
                        const colorBorde = af.leyenda_aplicable?.[0]?.color || '#3b82f6';
                        html += `
                            <div class="item-afeccion" style="border-left: 5px solid ${colorBorde}">
                                <strong>${af.capa}</strong><br>
                                <span>${af.leyenda_aplicable?.[0]?.etiqueta || 'Área Protegida'}</span>
                            </div>`;
                    });
                } else {
                    html += '<p class="success-msg">✅ Parcela sin afecciones detectadas.</p>';
                }

                html += '</div></div>';
                panelResultados.innerHTML = html;
            } else {
                panelResultados.innerHTML = `<p class="error">Error: ${res.detail}</p>`;
            }
        } catch (err) {
            panelResultados.innerHTML = '<p class="error">Error al conectar con el servidor.</p>';
        }
    });
});
