"""Núcleo de cálculo geográfico.

Fornece:
 - Projeção geodésica direta no elipsoide WGS84 (geographiclib), com fallback
   esférico se a biblioteca não estiver instalada.
 - Amostragem de relevo a partir de um DEM local (GeoTIFF) via rasterio.
 - Interseção raio-terreno (ray-march + bisseção) com correção de curvatura
   terrestre e refração atmosférica.

Tudo degrada de forma graciosa: sem geographiclib usa esfera; sem rasterio ou
sem DEM usa terreno plano com a cota informada manualmente.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_378_137.0  # raio equatorial WGS84
REFRACTION_K = 0.13           # coeficiente padrão de refração atmosférica


# --------------------------------------------------------------------------- #
# Projeção geodésica
# --------------------------------------------------------------------------- #
try:
    from geographiclib.geodesic import Geodesic  # type: ignore

    _GEOD = Geodesic.WGS84
    HAS_GEOGRAPHICLIB = True
except Exception:  # pragma: no cover - fallback
    _GEOD = None
    HAS_GEOGRAPHICLIB = False


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float


def _normalize_lon(lon_deg: float) -> float:
    return ((lon_deg + 180.0) % 360.0) - 180.0


def destination_point_sphere(lat_deg, lon_deg, distance_m, bearing_deg) -> GeoPoint:
    lat1 = math.radians(lat_deg)
    lon1 = math.radians(lon_deg)
    bearing = math.radians(bearing_deg)
    ad = distance_m / EARTH_RADIUS_M

    sin_lat1, cos_lat1 = math.sin(lat1), math.cos(lat1)
    sin_ad, cos_ad = math.sin(ad), math.cos(ad)

    lat2 = math.asin(sin_lat1 * cos_ad + cos_lat1 * sin_ad * math.cos(bearing))
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * sin_ad * cos_lat1,
        cos_ad - sin_lat1 * math.sin(lat2),
    )
    return GeoPoint(math.degrees(lat2), _normalize_lon(math.degrees(lon2)))


def destination_point(lat_deg, lon_deg, distance_m, bearing_deg) -> GeoPoint:
    """Ponto de destino dado origem, distância e azimute.

    Usa WGS84 (geographiclib) quando disponível; senão, esfera.
    """
    if distance_m < 0:
        raise ValueError("a distância não pode ser negativa")
    if HAS_GEOGRAPHICLIB:
        r = _GEOD.Direct(lat_deg, lon_deg, bearing_deg, distance_m)
        return GeoPoint(r["lat2"], _normalize_lon(r["lon2"]))
    return destination_point_sphere(lat_deg, lon_deg, distance_m, bearing_deg)


# --------------------------------------------------------------------------- #
# DEM (Modelo Digital de Elevação)
# --------------------------------------------------------------------------- #
class DEM:
    """Wrapper leve sobre um GeoTIFF de elevação com amostragem bilinear.

    Aceita DEM em qualquer CRS: converte lon/lat (EPSG:4326) para o CRS do
    raster antes de amostrar.
    """

    def __init__(self, path: str):
        import rasterio  # import tardio: só exige rasterio se o DEM for usado
        from rasterio.warp import transform as warp_transform

        self._rasterio = rasterio
        self._warp_transform = warp_transform
        self._ds = rasterio.open(path)
        self._band = self._ds.read(1)
        self._nodata = self._ds.nodata
        self._crs = self._ds.crs
        self._is_geographic = bool(self._crs and self._crs.is_geographic)
        self.path = path

    def close(self) -> None:
        try:
            self._ds.close()
        except Exception:
            pass

    def _to_ds_crs(self, lon, lat):
        if self._is_geographic or self._crs is None:
            return lon, lat
        xs, ys = self._warp_transform("EPSG:4326", self._crs, [lon], [lat])
        return xs[0], ys[0]

    def elevation(self, lon: float, lat: float):
        """Elevação (m) em lon/lat com interpolação bilinear. None se fora/nodata."""
        x, y = self._to_ds_crs(lon, lat)
        # coordenada de pixel fracionária
        col_f, row_f = ~self._ds.transform * (x, y)
        col_f -= 0.5
        row_f -= 0.5
        c0 = math.floor(col_f)
        r0 = math.floor(row_f)
        fx = col_f - c0
        fy = row_f - r0
        h, w = self._band.shape
        if c0 < 0 or r0 < 0 or c0 + 1 >= w or r0 + 1 >= h:
            # cai para vizinho mais próximo na borda
            c = min(max(int(round(col_f)), 0), w - 1)
            r = min(max(int(round(row_f)), 0), h - 1)
            v = float(self._band[r, c])
            return None if self._nodata is not None and v == self._nodata else v

        v00 = float(self._band[r0, c0])
        v01 = float(self._band[r0, c0 + 1])
        v10 = float(self._band[r0 + 1, c0])
        v11 = float(self._band[r0 + 1, c0 + 1])
        if self._nodata is not None and self._nodata in (v00, v01, v10, v11):
            return None
        top = v00 * (1 - fx) + v01 * fx
        bot = v10 * (1 - fx) + v11 * fx
        return top * (1 - fy) + bot * fy


# --------------------------------------------------------------------------- #
# Geometria do raio da câmera
# --------------------------------------------------------------------------- #
def _depression_angle_deg(camera_angle_deg: float, angle_mode: str) -> float:
    """Retorna o ângulo de depressão abaixo do horizonte (graus)."""
    if angle_mode == "vertical":
        if not 0.0 <= camera_angle_deg < 90.0:
            raise ValueError("o ângulo a partir da vertical deve ficar entre 0 e 90 graus")
        return 90.0 - camera_angle_deg
    if not 0.0 < camera_angle_deg <= 90.0:
        raise ValueError("o ângulo a partir do horizonte deve ficar entre 0 e 90 graus")
    return camera_angle_deg


def _curvature_drop(d: float, use_curvature: bool) -> float:
    """Queda aparente do terreno por curvatura + refração ao longo de d metros."""
    if not use_curvature or d <= 0:
        return 0.0
    return (1.0 - REFRACTION_K) * d * d / (2.0 * EARTH_RADIUS_M)


def compute_point(
    drone_lat: float,
    drone_lon: float,
    drone_alt_asl: float,
    terrain_alt_asl: float,
    camera_angle_deg: float,
    azimuth_deg: float,
    angle_mode: str,
    dem: DEM | None = None,
    use_curvature: bool = True,
    max_range_m: float = 60_000.0,
    step_m: float = 5.0,
) -> dict:
    """Estima a coordenada do ponto visado.

    Se `dem` for fornecido, faz marcha do raio contra o relevo real até a
    interseção. Caso contrário, usa terreno plano na cota `terrain_alt_asl`.
    """
    dep = _depression_angle_deg(camera_angle_deg, angle_mode)
    tan_dep = math.tan(math.radians(dep))

    method = "plano"
    used_geodesic = "WGS84" if HAS_GEOGRAPHICLIB else "esférico"

    # ----- Modo terreno plano (sem DEM) -----------------------------------
    if dem is None:
        delta_h = drone_alt_asl - terrain_alt_asl
        if delta_h < 0:
            raise ValueError("a altitude do terreno não pode ficar acima da altitude do drone")
        if tan_dep <= 0:
            raise ValueError("ângulo de depressão inválido (visada horizontal)")
        horizontal_distance = delta_h / tan_dep
        if not math.isfinite(horizontal_distance):
            raise ValueError("distância inválida calculada")
        ground_elev = terrain_alt_asl
    else:
        # ----- Modo DEM: marcha do raio ----------------------------------
        method = "DEM"
        start_elev = dem.elevation(drone_lon, drone_lat)
        if start_elev is not None and drone_alt_asl <= start_elev:
            raise ValueError("a altitude do drone está abaixo do relevo na própria posição")

        def diff_at(d: float):
            p = destination_point(drone_lat, drone_lon, d, azimuth_deg)
            g = dem.elevation(p.longitude, p.latitude)
            if g is None:
                return None, p, None
            ray_alt = drone_alt_asl - d * tan_dep + _curvature_drop(d, use_curvature)
            return ray_alt - g, p, g

        prev_d = 0.0
        prev_diff = drone_alt_asl - (start_elev if start_elev is not None else terrain_alt_asl)
        hit_d = None
        d = step_m
        last_valid_p = None
        while d <= max_range_m:
            diff, p, g = diff_at(d)
            if diff is None:
                # saiu da cobertura do DEM: aborta marcha
                break
            last_valid_p = (p, g)
            if diff <= 0.0:
                hit_d = (prev_d, d)
                break
            prev_d, prev_diff = d, diff
            d += step_m

        if hit_d is None:
            raise ValueError(
                "o raio não interceptou o relevo dentro do alcance/área do DEM. "
                "Verifique ângulo, azimute e a cobertura do arquivo de relevo."
            )

        # refino por bisseção
        lo, hi = hit_d
        g_hit = None
        p_hit = None
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            diff, p, g = diff_at(mid)
            if diff is None:
                hi = mid
                continue
            p_hit, g_hit = p, g
            if diff > 0:
                lo = mid
            else:
                hi = mid
            if hi - lo < 0.05:  # 5 cm
                break
        horizontal_distance = 0.5 * (lo + hi)
        point = p_hit if p_hit is not None else destination_point(
            drone_lat, drone_lon, horizontal_distance, azimuth_deg
        )
        ground_elev = g_hit if g_hit is not None else terrain_alt_asl
        delta_h = drone_alt_asl - ground_elev

    if dem is None:
        point = destination_point(drone_lat, drone_lon, horizontal_distance, azimuth_deg)

    delta_n = horizontal_distance * math.cos(math.radians(azimuth_deg))
    delta_e = horizontal_distance * math.sin(math.radians(azimuth_deg))
    slant_range = math.hypot(horizontal_distance, delta_h)

    return {
        "horizontal_distance_m": horizontal_distance,
        "delta_h_m": delta_h,
        "delta_n_m": delta_n,
        "delta_e_m": delta_e,
        "slant_range_m": slant_range,
        "ground_elev_m": ground_elev,
        "depression_deg": dep,
        "latitude": point.latitude,
        "longitude": point.longitude,
        "method": method,
        "geodesic": used_geodesic,
        "curvature": use_curvature,
    }
