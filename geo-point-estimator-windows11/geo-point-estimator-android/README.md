# Geo Point Estimator — versão Android (PWA)

App web que roda offline no celular. Estima a coordenada de um ponto observado
por drone, com geodésica WGS84 e, opcionalmente, relevo real (DEM GeoTIFF).

## Recursos

- Geodésica WGS84 (Vincenty) — mesma precisão da versão Windows.
- Relevo real: carregue um GeoTIFF (EPSG:4326) pelo botão de arquivo; o app faz
  a interseção do raio da câmera com o terreno (ray-march + bisseção).
- Correção de curvatura da Terra + refração.
- Botão "Usar meu GPS" para preencher a posição do drone/observador.
- "Abrir no mapa" leva o ponto estimado ao Google Maps.
- 100% offline depois de instalado. Nenhum dado sai do aparelho.

## Como instalar no Android (recomendado)

A forma mais simples de ter o ícone na tela inicial:

1. Publique esta pasta em qualquer hospedagem estática gratuita
   (GitHub Pages, Netlify Drop, Cloudflare Pages). É só arrastar a pasta.
2. No celular, abra o endereço no **Chrome**.
3. Menu (tres pontinhos) > **Adicionar à tela inicial** / **Instalar app**.
4. Pronto: abre em tela cheia e funciona sem internet.

> O service worker (offline real e instalação) exige HTTPS ou localhost — por
> isso a hospedagem estática. Qualquer uma das opções acima serve em segundos.

## Uso rápido sem hospedar

Copie a pasta para o celular e abra o `index.html` no navegador. O cálculo
funciona offline (os arquivos já estão no aparelho). A instalação como app e o
cache offline automático só ficam disponíveis quando servido por HTTPS.

## DEM (relevo)

Use um GeoTIFF de elevação em **EPSG:4326** (lat/lon). Fontes: SRTM 30m,
Copernicus GLO-30. Recorte só a sua área de operação para o arquivo ficar leve.
Se o DEM estiver projetado (UTM etc.), reprojete para lat/lon antes.

## Arquivos

- index.html — interface
- geo.js — geodésica WGS84 + ray-march (espelha o geo_core.py)
- app.js — GPS, leitura de DEM, cálculo
- geotiff.js — leitor de GeoTIFF (embutido para uso offline)
- manifest.webmanifest, service-worker.js, icon.png — instalação/offline
