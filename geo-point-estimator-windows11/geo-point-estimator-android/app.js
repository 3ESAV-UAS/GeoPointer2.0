// Integração da UI: GPS, leitura de DEM (geotiff.js) e cálculo.

let demSampler = null; // { elevation(lon,lat) }

const $ = (id) => document.getElementById(id);
const num = (id) => {
  const t = $(id).value.trim().replace(",", ".");
  if (t === "") throw new Error("preencha todos os campos numéricos");
  const v = Number(t);
  if (!isFinite(v)) throw new Error("valor inválido: " + $(id).value);
  return v;
};
const mode = () => document.querySelector('input[name="mode"]:checked').value;

function showError(msg) {
  $("outCard").style.display = "block";
  $("out").innerHTML = `<div class="alert">${msg}</div>`;
}

// ---- DEM via geotiff.js ----------------------------------------------------
async function loadDem(file) {
  $("demStatus").textContent = "Lendo DEM...";
  const buf = await file.arrayBuffer();
  const tiff = await GeoTIFF.fromArrayBuffer(buf);
  const image = await tiff.getImage();
  const width = image.getWidth();
  const height = image.getHeight();
  const [west, south, east, north] = image.getBoundingBox();
  const nodata = image.getGDALNoData();
  const band = (await image.readRasters())[0];

  // aviso se o DEM não for geográfico (lat/lon)
  let projected = false;
  try {
    const keys = image.getGeoKeys ? image.getGeoKeys() : image.geoKeys;
    if (keys && keys.ProjectedCSTypeGeoKey) projected = true;
  } catch (e) {}

  const sampler = {
    elevation(lon, lat) {
      const colF = ((lon - west) / (east - west)) * width - 0.5;
      const rowF = ((north - lat) / (north - south)) * height - 0.5;
      const c0 = Math.floor(colF), r0 = Math.floor(rowF);
      const fx = colF - c0, fy = rowF - r0;
      const at = (r, c) => {
        if (r < 0 || c < 0 || r >= height || c >= width) return null;
        const v = band[r * width + c];
        if (nodata != null && v === nodata) return null;
        return v;
      };
      if (c0 < 0 || r0 < 0 || c0 + 1 >= width || r0 + 1 >= height) {
        const c = Math.min(Math.max(Math.round(colF), 0), width - 1);
        const r = Math.min(Math.max(Math.round(rowF), 0), height - 1);
        return at(r, c);
      }
      const v00 = at(r0, c0), v01 = at(r0, c0 + 1), v10 = at(r0 + 1, c0), v11 = at(r0 + 1, c0 + 1);
      if ([v00, v01, v10, v11].some((x) => x == null)) return null;
      const top = v00 * (1 - fx) + v01 * fx;
      const bot = v10 * (1 - fx) + v11 * fx;
      return top * (1 - fy) + bot * fy;
    },
  };
  demSampler = sampler;
  $("demStatus").innerHTML = projected
    ? `<span style="color:#ffd58a">DEM carregado, mas parece projetado (não EPSG:4326). Reprojete para lat/lon.</span>`
    : `DEM carregado: ${width}×${height} px · bbox [${west.toFixed(3)}, ${south.toFixed(3)}, ${east.toFixed(3)}, ${north.toFixed(3)}]`;
}

$("demFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) { demSampler = null; return; }
  try { await loadDem(file); }
  catch (err) { demSampler = null; $("demStatus").innerHTML = `<span style="color:#ffd5d5">Falha ao ler DEM: ${err.message}</span>`; }
});

// ---- GPS -------------------------------------------------------------------
$("btnGps").addEventListener("click", () => {
  if (!navigator.geolocation) return showError("GPS não disponível neste dispositivo.");
  $("btnGps").textContent = "Obtendo...";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      $("lat").value = pos.coords.latitude.toFixed(6);
      $("lon").value = pos.coords.longitude.toFixed(6);
      if (pos.coords.altitude != null) $("droneAlt").value = pos.coords.altitude.toFixed(1);
      $("btnGps").textContent = "Usar meu GPS";
    },
    (err) => { $("btnGps").textContent = "Usar meu GPS"; showError("GPS: " + err.message); },
    { enableHighAccuracy: true, timeout: 10000 }
  );
});

// ---- Exemplo ---------------------------------------------------------------
$("btnExample").addEventListener("click", () => {
  $("lat").value = "-15.793889"; $("lon").value = "-47.882778";
  $("droneAlt").value = "350"; $("terrainAlt").value = "290";
  $("angle").value = "20"; $("azimuth").value = "135";
  document.querySelector('input[value="vertical"]').checked = true;
});

// ---- Calcular --------------------------------------------------------------
$("btnCalc").addEventListener("click", () => {
  try {
    const r = computePoint({
      droneLat: num("lat"), droneLon: num("lon"),
      droneAlt: num("droneAlt"), terrainAlt: num("terrainAlt"),
      cameraAngle: num("angle"), azimuth: num("azimuth"),
      angleMode: mode(), dem: demSampler, useCurvature: $("curv").checked,
    });
    const maps = `https://www.google.com/maps?q=${r.latitude.toFixed(8)},${r.longitude.toFixed(8)}`;
    const methodLabel = r.method === "DEM" ? "Relevo real (DEM)" : "Terreno plano";
    $("outCard").style.display = "block";
    $("out").innerHTML = `
      <div class="results">
        <div class="res big"><span>Coordenada estimada</span>
          <strong>${r.latitude.toFixed(8)}, ${r.longitude.toFixed(8)}</strong></div>
        <div class="res"><span>Distância horizontal</span><strong>${r.horizontalDistance.toFixed(2)} m</strong></div>
        <div class="res"><span>Alcance inclinado</span><strong>${r.slant.toFixed(2)} m</strong></div>
        <div class="res"><span>Cota do terreno</span><strong>${r.groundElev.toFixed(2)} m</strong></div>
        <div class="res"><span>Desnível</span><strong>${r.deltaH.toFixed(2)} m</strong></div>
      </div>
      <div class="det">
        <p>Norte ${r.deltaN.toFixed(2)} m · Leste ${r.deltaE.toFixed(2)} m · Depressão ${r.depression.toFixed(2)}°</p>
        <p>${methodLabel} · WGS84 · curvatura ${r.curvature ? "ligada" : "desligada"}</p>
        <p><a class="maplink" href="${maps}" target="_blank" rel="noopener">Abrir no mapa ↗</a></p>
      </div>`;
    $("outCard").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    showError(err.message);
  }
});

// ---- Service worker (offline) ----------------------------------------------
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("service-worker.js").catch(() => {}));
}
