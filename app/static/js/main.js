document.addEventListener('DOMContentLoaded', () => {
    // Inicializar Mapa
    const map = L.map('map').setView([40.416775, -3.703790], 6);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    let currentLayer = null;

    // Elementos UI
    const btnAnalizar = document.getElementById('btn-analizar');
    const refInput = document.getElementById('refcat-input');
    const resultsContainer = document.getElementById('results-container');
    const analysisData = document.getElementById('analysis-data');

    // Función de Análisis
    async function analizarParcela() {
        const referencia = refInput.value.trim();
        if (!referencia) {
            alert('Por favor, introduce una referencia catastral.');
            return;
        }

        btnAnalizar.disabled = true;
        btnAnalizar.innerText = 'Analizando...';

        try {
            const response = await fetch('/api/catastro/consultar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ referencia_catastral: referencia })
            });

            const result = await response.json();

            if (result.status === 'success' && result.data) {
                mostrarResultados(result.data);
                if (result.data.geojson) {
                    actualizarMapa(result.data.geojson);
                }
            } else {
                alert('Error: ' + (result.detail || 'No se pudo analizar la parcela'));
            }
        } catch (error) {
            console.error('Error en la petición:', error);
            alert('Error de conexión con el servidor.');
        } finally {
            btnAnalizar.disabled = false;
            btnAnalizar.innerText = 'Analizar Parcela';
        }
    }

    function mostrarResultados(data) {
        resultsContainer.style.display = 'block';
        analysisData.innerHTML = `
            <div class="result-item"><strong>Referencia:</strong> \${data.referencia}</div>
            <div class="result-item"><strong>Localización:</strong> \${data.direccion || 'No disponible'}</div>
            <div class="result-item"><strong>Uso:</strong> \${data.uso || 'No especificado'}</div>
            <div class="result-item"><strong>Superficie:</strong> \${data.superficie || '0'} m²</div>
        `;
    }

    function actualizarMapa(geojson) {
        if (currentLayer) map.removeLayer(currentLayer);
        currentLayer = L.geoJSON(geojson, {
            style: { color: '#2563eb', weight: 3, fillOpacity: 0.2 }
        }).addTo(map);
        map.fitBounds(currentLayer.getBounds());
    }

    btnAnalizar.addEventListener('click', analizarParcela);
});
