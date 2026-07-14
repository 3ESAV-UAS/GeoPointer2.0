from __future__ import annotations

import html
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import geo_core
from geo_core import HAS_GEOGRAPHICLIB, compute_point

HOST = "0.0.0.0"
PORT = 8765
LOCAL_OPEN_HOST = "127.0.0.1"


def _parse_float(value: str) -> float:
    text = value.strip().replace(",", ".")
    if not text:
        raise ValueError("campo vazio")
    return float(text)


def _escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


# cache simples de DEM para não reabrir o arquivo a cada cálculo
_DEM_CACHE: dict[str, object] = {}


def _get_dem(path: str):
    path = path.strip()
    if not path:
        return None
    if not os.path.isfile(path):
        raise ValueError(f"arquivo de relevo não encontrado: {path}")
    cached = _DEM_CACHE.get(path)
    if cached is not None:
        return cached
    try:
        dem = geo_core.DEM(path)
    except ModuleNotFoundError:
        raise ValueError(
            "para usar relevo (DEM) instale a dependência: pip install rasterio"
        )
    except Exception as exc:
        raise ValueError(f"falha ao abrir o DEM: {exc}")
    _DEM_CACHE[path] = dem
    return dem


def render_page(values=None, result=None, error=None) -> str:
    values = values or {}
    defaults = {
        "lat": values.get("lat", "-15.793889"),
        "lon": values.get("lon", "-47.882778"),
        "drone_alt": values.get("drone_alt", "350"),
        "terrain_alt": values.get("terrain_alt", "290"),
        "angle": values.get("angle", "20"),
        "azimuth": values.get("azimuth", "135"),
        "angle_mode": values.get("angle_mode", "vertical"),
        "dem_path": values.get("dem_path", ""),
        "curvature": values.get("curvature", "on"),
    }

    vertical_checked = "checked" if defaults["angle_mode"] == "vertical" else ""
    horizon_checked = "checked" if defaults["angle_mode"] == "horizon" else ""
    curv_checked = "checked" if defaults["curvature"] == "on" else ""

    geod_badge = "WGS84 (geographiclib)" if HAS_GEOGRAPHICLIB else "esférico (instale geographiclib p/ WGS84)"

    result_html = ""
    if result:
        method_label = "Relevo real (DEM)" if result["method"] == "DEM" else "Terreno plano"
        result_html = f"""
        <div class="results-grid">
            <div class="result">
                <span>Latitude estimada</span>
                <strong>{result['latitude']:.8f}</strong>
            </div>
            <div class="result">
                <span>Longitude estimada</span>
                <strong>{result['longitude']:.8f}</strong>
            </div>
            <div class="result">
                <span>Distância horizontal</span>
                <strong>{result['horizontal_distance_m']:.2f} m</strong>
            </div>
            <div class="result">
                <span>Alcance inclinado (slant)</span>
                <strong>{result['slant_range_m']:.2f} m</strong>
            </div>
            <div class="result">
                <span>Cota do terreno no alvo</span>
                <strong>{result['ground_elev_m']:.2f} m</strong>
            </div>
            <div class="result">
                <span>Desnível vertical</span>
                <strong>{result['delta_h_m']:.2f} m</strong>
            </div>
        </div>
        <div class="details">
            <p><strong>Deslocamento norte:</strong> {result['delta_n_m']:.2f} m &nbsp; | &nbsp; <strong>Leste:</strong> {result['delta_e_m']:.2f} m</p>
            <p><strong>Ângulo de depressão:</strong> {result['depression_deg']:.2f}°</p>
            <p><strong>Modelo:</strong> {method_label} · geodésia {result['geodesic']} · curvatura {'ligada' if result['curvature'] else 'desligada'}</p>
        </div>
        """

    error_html = f'<div class="alert">{_escape(error)}</div>' if error else ""

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Estimador de Coordenada Geográfica</title>
  <style>
    :root {{
      --bg:#0b1220; --panel:#121c2b; --panel-2:#162235; --accent:#71b7ff;
      --text:#eaf1f8; --muted:#9eb3c7; --border:rgba(255,255,255,0.08);
      --shadow:0 20px 60px rgba(0,0,0,0.35);
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;
      color:var(--text);
      background:radial-gradient(circle at top left,rgba(113,183,255,0.18),transparent 34%),
        radial-gradient(circle at top right,rgba(90,255,205,0.10),transparent 26%),
        linear-gradient(180deg,#09101c 0%,var(--bg) 100%); }}
    .wrap {{ max-width:1180px; margin:0 auto; padding:32px 20px 40px; }}
    .hero {{ display:grid; gap:12px; margin-bottom:22px; }}
    .eyebrow {{ color:var(--accent); text-transform:uppercase; letter-spacing:0.16em; font-size:12px; font-weight:700; }}
    h1 {{ margin:0; font-size:clamp(30px,4vw,48px); line-height:1.05; }}
    .sub {{ margin:0; color:var(--muted); max-width:820px; font-size:15px; line-height:1.5; }}
    .badge {{ display:inline-block; margin-top:4px; font-size:12px; color:var(--accent);
      border:1px solid var(--border); padding:4px 10px; border-radius:999px; }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1.1fr) minmax(320px,0.9fr); gap:18px; align-items:start; }}
    .card {{ background:rgba(18,28,43,0.92); border:1px solid var(--border); border-radius:22px; box-shadow:var(--shadow); overflow:hidden; }}
    .card header {{ padding:20px 22px 0; }}
    .card h2 {{ margin:0; font-size:20px; }}
    .card p.small {{ margin:6px 0 0; color:var(--muted); font-size:13px; }}
    form {{ padding:18px 22px 22px; }}
    .fields {{ display:grid; gap:14px; }}
    .field {{ display:grid; gap:7px; }}
    label {{ font-size:13px; color:#d7e4f0; font-weight:600; }}
    input[type="text"] {{ width:100%; border:1px solid var(--border); background:var(--panel-2);
      color:var(--text); border-radius:14px; padding:13px 14px; outline:none; font-size:15px; }}
    input[type="text"]:focus {{ border-color:rgba(113,183,255,0.65); box-shadow:0 0 0 4px rgba(113,183,255,0.12); }}
    .hint {{ color:var(--muted); font-size:12px; margin-top:-2px; }}
    .mode {{ display:flex; flex-wrap:wrap; gap:12px; padding:8px 0 2px; }}
    .mode label {{ display:flex; align-items:center; gap:8px; padding:10px 12px; border:1px solid var(--border);
      border-radius:999px; background:rgba(255,255,255,0.02); font-weight:500; cursor:pointer; }}
    .actions {{ display:flex; gap:10px; margin-top:18px; flex-wrap:wrap; }}
    button {{ appearance:none; border:0; border-radius:14px; padding:12px 16px; font-size:14px; font-weight:700; cursor:pointer; }}
    .primary {{ background:linear-gradient(135deg,#7dc0ff,#4aa5ff); color:#09111b; }}
    .secondary {{ background:transparent; color:var(--text); border:1px solid var(--border); }}
    .result-panel {{ padding:18px 22px 22px; display:grid; gap:16px; }}
    .alert {{ background:rgba(255,138,138,0.12); color:#ffd5d5; border:1px solid rgba(255,138,138,0.32);
      padding:14px 16px; border-radius:14px; font-size:14px; line-height:1.4; }}
    .results-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .result {{ background:rgba(255,255,255,0.03); border:1px solid var(--border); border-radius:16px; padding:14px; }}
    .result span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:6px; }}
    .result strong {{ font-size:16px; word-break:break-word; }}
    .details {{ border-top:1px solid var(--border); padding-top:12px; color:#dce7f2; font-size:14px; line-height:1.5; }}
    .footer-note {{ margin-top:16px; color:var(--muted); font-size:12px; }}
    @media (max-width:920px) {{ .grid {{ grid-template-columns:1fr; }} .results-grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">Ferramenta local</div>
      <h1>Estimador de coordenada geográfica</h1>
      <p class="sub">Posição do drone, altitude ASL, ângulo da câmera e azimute. Com um DEM (GeoTIFF), o ponto é obtido pela interseção do raio da câmera com o relevo real.</p>
      <span class="badge">Geodésia: {geod_badge}</span>
    </section>

    <div class="grid">
      <section class="card">
        <header>
          <h2>Dados de entrada</h2>
          <p class="small">Aceita ponto ou vírgula decimal. Azimute: 0° = norte, 90° = leste.</p>
        </header>
        <form method="post">
          <div class="fields">
            <div class="field">
              <label for="lat">Latitude do drone (graus)</label>
              <input id="lat" name="lat" type="text" value="{_escape(defaults['lat'])}" />
            </div>
            <div class="field">
              <label for="lon">Longitude do drone (graus)</label>
              <input id="lon" name="lon" type="text" value="{_escape(defaults['lon'])}" />
            </div>
            <div class="field">
              <label for="drone_alt">Altitude do drone ASL (m)</label>
              <input id="drone_alt" name="drone_alt" type="text" value="{_escape(defaults['drone_alt'])}" />
            </div>
            <div class="field">
              <label for="terrain_alt">Altitude do terreno ASL (m) — usada só sem DEM</label>
              <input id="terrain_alt" name="terrain_alt" type="text" value="{_escape(defaults['terrain_alt'])}" />
            </div>
            <div class="field">
              <label for="angle">Ângulo da câmera (graus)</label>
              <input id="angle" name="angle" type="text" value="{_escape(defaults['angle'])}" />
            </div>
            <div class="field">
              <label for="azimuth">Azimute da câmera (graus)</label>
              <input id="azimuth" name="azimuth" type="text" value="{_escape(defaults['azimuth'])}" />
              <div class="hint">Ex.: 0 norte, 90 leste, 180 sul, 270 oeste.</div>
            </div>
            <div class="field">
              <label for="dem_path">Caminho do DEM / GeoTIFF (opcional)</label>
              <input id="dem_path" name="dem_path" type="text" placeholder="C:\\relevo\\area.tif" value="{_escape(defaults['dem_path'])}" />
              <div class="hint">Vazio = terreno plano. Com arquivo = interseção com relevo real (requer rasterio).</div>
            </div>
            <div class="field">
              <label>Referência do ângulo</label>
              <div class="mode">
                <label><input type="radio" name="angle_mode" value="vertical" {vertical_checked} /> A partir da vertical</label>
                <label><input type="radio" name="angle_mode" value="horizon" {horizon_checked} /> A partir do horizonte</label>
              </div>
            </div>
            <div class="field">
              <div class="mode">
                <label><input type="checkbox" name="curvature" value="on" {curv_checked} /> Corrigir curvatura da Terra + refração</label>
              </div>
            </div>
          </div>
          <div class="actions">
            <button class="primary" type="submit">Calcular</button>
            <button class="secondary" type="submit" name="example" value="1">Preencher exemplo</button>
            <button class="secondary" type="reset">Limpar formulário</button>
          </div>
        </form>
      </section>

      <aside class="card">
        <header>
          <h2>Resultado</h2>
          <p class="small">A saída abaixo atualiza após o cálculo.</p>
        </header>
        <div class="result-panel">
          {error_html}
          {result_html if result_html else '<div class="details"><p>Preencha os campos e clique em <strong>Calcular</strong>.</p></div>'}
          <div class="footer-note">Com DEM, o cálculo marcha o raio da câmera (passo fino + bisseção) até cruzar o terreno, considerando curvatura e refração.</div>
        </div>
      </aside>
    </div>
  </div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._send_html(render_page())

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        form = parse_qs(raw, keep_blank_values=True)

        def g(name, default=""):
            return form.get(name, [default])[0]

        values = {
            "lat": g("lat"),
            "lon": g("lon"),
            "drone_alt": g("drone_alt"),
            "terrain_alt": g("terrain_alt"),
            "angle": g("angle"),
            "azimuth": g("azimuth"),
            "angle_mode": g("angle_mode", "vertical"),
            "dem_path": g("dem_path"),
            "curvature": "on" if form.get("curvature") else "",
        }

        if form.get("example"):
            values.update({
                "lat": "-15.793889", "lon": "-47.882778", "drone_alt": "350",
                "terrain_alt": "290", "angle": "20", "azimuth": "135",
                "angle_mode": "vertical",
            })

        try:
            dem = _get_dem(values["dem_path"])
            result = compute_point(
                drone_lat=_parse_float(values["lat"]),
                drone_lon=_parse_float(values["lon"]),
                drone_alt_asl=_parse_float(values["drone_alt"]),
                terrain_alt_asl=_parse_float(values["terrain_alt"]),
                camera_angle_deg=_parse_float(values["angle"]),
                azimuth_deg=_parse_float(values["azimuth"]),
                angle_mode=values["angle_mode"],
                dem=dem,
                use_curvature=values["curvature"] == "on",
            )
            body = render_page(values=values, result=result)
        except Exception as exc:
            body = render_page(values=values, error=str(exc))

        self._send_html(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def open_browser_later(url: str) -> None:
    threading.Timer(0.8, lambda: webbrowser.open(url, new=2)).start()


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Servidor iniciado em http://{LOCAL_OPEN_HOST}:{PORT}")
    print(f"Geodesia: {'WGS84' if HAS_GEOGRAPHICLIB else 'esferica (instale geographiclib)'}")
    print("Abra o navegador se ele nao abrir sozinho.")
    open_browser_later(f"http://{LOCAL_OPEN_HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
