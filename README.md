# Geo Point Estimator

Aplicacao local em Python com interface no navegador para estimar a coordenada
geografica de um ponto observado por drone.

## Precisao

- Projecao geodesica direta no elipsoide **WGS84** (geographiclib).
- **Relevo real**: interseccao do raio da camera com um DEM (GeoTIFF) via
  marcha de raio + refino por bisseccao.
- Correcao opcional de **curvatura da Terra + refracao** (k=0.13).
- Sem DEM, usa terreno plano com a cota informada (modo rapido).

## Como executar

1. Tenha Python 3.11+ instalado (marque "Add Python to PATH").
2. Duplo clique em `run_windows.bat` (instala dependencias na 1a vez e sobe o app).
3. Acesse http://localhost:8765 (abre sozinho).

Ou manualmente:

```bash
pip install -r requirements.txt
python app.py
```

## Gerar executavel (.exe)

Duplo clique em `build_exe.bat`. O resultado fica em `dist\geo-point-estimator.exe`.

## Usando relevo (DEM)

No formulario, informe o caminho de um GeoTIFF de elevacao no campo
"Caminho do DEM". Fontes uteis: SRTM 30m, Copernicus GLO-30. O DEM pode estar
em qualquer CRS (e reprojetado para amostragem). Deixe o campo vazio para o
modo de terreno plano.

## Campos

- Latitude/longitude e altitude ASL do drone
- Altitude do terreno ASL (usada apenas sem DEM)
- Angulo da camera (a partir da vertical ou do horizonte) e azimute
- Caminho do DEM (opcional) e correcao de curvatura
