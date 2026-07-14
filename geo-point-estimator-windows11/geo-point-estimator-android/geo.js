// Núcleo de cálculo geográfico (versão JavaScript, espelha geo_core.py)
// - Geodésica direta WGS84 (Vincenty)
// - Interseção raio-terreno (ray-march + bisseção) com curvatura + refração

const WGS84_A = 6378137.0;            // semieixo maior (m)
const WGS84_F = 1 / 298.257223563;    // achatamento
const WGS84_B = WGS84_A * (1 - WGS84_F);
const REFRACTION_K = 0.13;

const d2r = (d) => (d * Math.PI) / 180;
const r2d = (r) => (r * 180) / Math.PI;
const normLon = (lon) => ((lon + 180) % 360 + 360) % 360 - 180;

// Geodésica direta de Vincenty: ponto destino dado origem, azimute e distância.
function destinationPoint(latDeg, lonDeg, distanceM, bearingDeg) {
  if (distanceM < 0) throw new Error("a distância não pode ser negativa");
  if (distanceM === 0) return { lat: latDeg, lon: lonDeg };

  const a = WGS84_A, b = WGS84_B, f = WGS84_F;
  const alpha1 = d2r(bearingDeg);
  const s = distanceM;
  const sinA1 = Math.sin(alpha1), cosA1 = Math.cos(alpha1);

  const tanU1 = (1 - f) * Math.tan(d2r(latDeg));
  const cosU1 = 1 / Math.sqrt(1 + tanU1 * tanU1);
  const sinU1 = tanU1 * cosU1;

  const sigma1 = Math.atan2(tanU1, cosA1);
  const sinAlpha = cosU1 * sinA1;
  const cosSqAlpha = 1 - sinAlpha * sinAlpha;
  const uSq = cosSqAlpha * (a * a - b * b) / (b * b);
  const A = 1 + (uSq / 16384) * (4096 + uSq * (-768 + uSq * (320 - 175 * uSq)));
  const B = (uSq / 1024) * (256 + uSq * (-128 + uSq * (74 - 47 * uSq)));

  let sigma = s / (b * A);
  let sigmaP, cos2SigmaM, sinSigma, cosSigma;
  let iter = 0;
  do {
    cos2SigmaM = Math.cos(2 * sigma1 + sigma);
    sinSigma = Math.sin(sigma);
    cosSigma = Math.cos(sigma);
    const deltaSigma = B * sinSigma * (cos2SigmaM + (B / 4) *
      (cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM) -
        (B / 6) * cos2SigmaM * (-3 + 4 * sinSigma * sinSigma) *
        (-3 + 4 * cos2SigmaM * cos2SigmaM)));
    sigmaP = sigma;
    sigma = s / (b * A) + deltaSigma;
  } while (Math.abs(sigma - sigmaP) > 1e-12 && ++iter < 100);

  const tmp = sinU1 * sinSigma - cosU1 * cosSigma * cosA1;
  const lat2 = Math.atan2(
    sinU1 * cosSigma + cosU1 * sinSigma * cosA1,
    (1 - f) * Math.sqrt(sinAlpha * sinAlpha + tmp * tmp)
  );
  const lambda = Math.atan2(
    sinSigma * sinA1,
    cosU1 * cosSigma - sinU1 * sinSigma * cosA1
  );
  const C = (f / 16) * cosSqAlpha * (4 + f * (4 - 3 * cosSqAlpha));
  const L = lambda - (1 - C) * f * sinAlpha *
    (sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM)));

  return { lat: r2d(lat2), lon: normLon(lonDeg + r2d(L)) };
}

function depressionAngleDeg(cameraAngleDeg, angleMode) {
  if (angleMode === "vertical") {
    if (!(cameraAngleDeg >= 0 && cameraAngleDeg < 90))
      throw new Error("o ângulo a partir da vertical deve ficar entre 0 e 90 graus");
    return 90 - cameraAngleDeg;
  }
  if (!(cameraAngleDeg > 0 && cameraAngleDeg <= 90))
    throw new Error("o ângulo a partir do horizonte deve ficar entre 0 e 90 graus");
  return cameraAngleDeg;
}

function curvatureDrop(d, useCurvature) {
  if (!useCurvature || d <= 0) return 0;
  return (1 - REFRACTION_K) * d * d / (2 * WGS84_A);
}

// dem: objeto com método elevation(lon, lat) -> número ou null. Pode ser null.
function computePoint(opts) {
  const {
    droneLat, droneLon, droneAlt, terrainAlt,
    cameraAngle, azimuth, angleMode,
    dem = null, useCurvature = true,
    maxRangeM = 60000, stepM = 5,
  } = opts;

  const dep = depressionAngleDeg(cameraAngle, angleMode);
  const tanDep = Math.tan(d2r(dep));
  let method = "plano";
  let horizontalDistance, point, groundElev;

  if (!dem) {
    const deltaH = droneAlt - terrainAlt;
    if (deltaH < 0) throw new Error("a altitude do terreno não pode ficar acima da altitude do drone");
    if (tanDep <= 0) throw new Error("ângulo de depressão inválido (visada horizontal)");
    horizontalDistance = deltaH / tanDep;
    if (!isFinite(horizontalDistance)) throw new Error("distância inválida calculada");
    groundElev = terrainAlt;
    point = destinationPoint(droneLat, droneLon, horizontalDistance, azimuth);
  } else {
    method = "DEM";
    const startElev = dem.elevation(droneLon, droneLat);
    if (startElev != null && droneAlt <= startElev)
      throw new Error("a altitude do drone está abaixo do relevo na própria posição");

    const diffAt = (d) => {
      const p = destinationPoint(droneLat, droneLon, d, azimuth);
      const g = dem.elevation(p.lon, p.lat);
      if (g == null) return { diff: null, p, g: null };
      const rayAlt = droneAlt - d * tanDep + curvatureDrop(d, useCurvature);
      return { diff: rayAlt - g, p, g };
    };

    let prevD = 0;
    let hit = null;
    let d = stepM;
    while (d <= maxRangeM) {
      const { diff } = diffAt(d);
      if (diff == null) break;
      if (diff <= 0) { hit = [prevD, d]; break; }
      prevD = d;
      d += stepM;
    }
    if (!hit) throw new Error(
      "o raio não interceptou o relevo dentro do alcance/área do DEM. " +
      "Verifique ângulo, azimute e a cobertura do arquivo de relevo.");

    let [lo, hi] = hit, pHit = null, gHit = null;
    for (let i = 0; i < 60; i++) {
      const mid = 0.5 * (lo + hi);
      const { diff, p, g } = diffAt(mid);
      if (diff == null) { hi = mid; continue; }
      pHit = p; gHit = g;
      if (diff > 0) lo = mid; else hi = mid;
      if (hi - lo < 0.05) break;
    }
    horizontalDistance = 0.5 * (lo + hi);
    point = pHit || destinationPoint(droneLat, droneLon, horizontalDistance, azimuth);
    groundElev = gHit != null ? gHit : terrainAlt;
  }

  const deltaH = droneAlt - groundElev;
  const deltaN = horizontalDistance * Math.cos(d2r(azimuth));
  const deltaE = horizontalDistance * Math.sin(d2r(azimuth));
  const slant = Math.hypot(horizontalDistance, deltaH);

  return {
    horizontalDistance, deltaH, deltaN, deltaE, slant,
    groundElev, depression: dep,
    latitude: point.lat, longitude: point.lon,
    method, geodesic: "WGS84", curvature: useCurvature,
  };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { destinationPoint, computePoint, depressionAngleDeg };
}
