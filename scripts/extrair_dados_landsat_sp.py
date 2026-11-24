"""
Extrai Temperatura de Superfície Terrestre (TST / LST), NDVI (vegetação) e Albedo
de imagens reais Landsat 8/9 Collection 2 Level-2 (USGS/NASA) via Microsoft Planetary
Computer STAC API para as 32 Subprefeituras e 96 Distritos do município de São Paulo.

Metodologia física (USGS Collection 2 Level-2):
- TST (°C) = ST_B10 * 0.00341802 + 149.0 - 273.15
- Refletância de superfície (SR) = DN * 0.0000275 - 0.2
- NDVI = (NIR - RED) / (NIR + RED)
- Albedo de ondas curtas (Liang, 2001):
    alpha = 0.356*B2 + 0.130*B4 + 0.373*B5 + 0.085*B6 + 0.072*B7 - 0.0018
- Máscara QA_PIXEL: remove preenchimento, nuvens, nuvens dilatadas, cirros, sombra de nuvem
  e (para métricas terrestres) corpos d'água abertos (bit 7), evitando viés das represas
  Billings e Guarapiranga na temperatura da superfície urbana.
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds
import requests

warnings.filterwarnings("ignore", category=UserWarning)

WORKDIR = Path(__file__).resolve().parent
SUBPREF_GEOJSON = WORKDIR / "subprefeituras-sp.geojson"
DISTRITOS_GEOJSON = WORKDIR / "distritos-sp.geojson"

# Cenas Landsat 8/9 C2 L2 (WRS Path 219 / Row 076) de estação quente (primavera/verão)
# com baixíssima cobertura de nuvens (< 7.5%), 2023–2026
SCENE_IDS = [
    "LC08_L2SP_219076_20260329_02_T1",  # 2026-03-29 (cloud 3.5%)
    "LC09_L2SP_219076_20251129_02_T1",  # 2025-11-29 (cloud 1.3%)
    "LC08_L2SP_219076_20251121_02_T1",  # 2025-11-21 (cloud 2.3%)
    "LC09_L2SP_219076_20241126_02_T1",  # 2024-11-26 (cloud 4.7%)
    "LC09_L2SP_219076_20240315_02_T1",  # 2024-03-15 (cloud 4.4%)
    "LC08_L2SP_219076_20231218_02_T1",  # 2023-12-18 (cloud 4.0%)
]

STAC_ITEM_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2/items/{scene_id}"
SAS_TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/landsat-c2-l2"


def get_sas_token() -> str:
    resp = requests.get(SAS_TOKEN_URL, timeout=20)
    resp.raise_for_status()
    return resp.json()["token"]


def read_window(href: str, bounds: tuple[float, float, float, float], ref_shape=None):
    with rasterio.open(href) as src:
        win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
        if ref_shape is not None:
            data = src.read(
                1,
                window=win,
                out_shape=ref_shape,
                resampling=rasterio.enums.Resampling.nearest,
            )
        else:
            data = src.read(1, window=win)
        transform = src.window_transform(win)
        crs = src.crs
    return data, transform, crs


def main() -> None:
    print("1. Carregando malhas geográficas...")
    gdf_sub = gpd.read_file(SUBPREF_GEOJSON)
    gdf_dist = gpd.read_file(DISTRITOS_GEOJSON)

    print("2. Obtendo token SAS do Microsoft Planetary Computer...")
    sas_token = get_sas_token()

    # Descobre CRS e janela exata na grade da primeira cena
    first_item = requests.get(STAC_ITEM_URL.format(scene_id=SCENE_IDS[0]), timeout=20).json()
    first_lwir = first_item["assets"]["lwir11"]["href"] + "?" + sas_token

    with rasterio.open(first_lwir) as src0:
        raster_crs = src0.crs
        gdf_sub_utm = gdf_sub.to_crs(raster_crs)
        gdf_dist_utm = gdf_dist.to_crs(raster_crs)
        minx, miny, maxx, maxy = gdf_sub_utm.total_bounds
        # Margem de 300 m
        bounds = (minx - 300, miny - 300, maxx + 300, maxy + 300)
        win0 = from_bounds(*bounds, transform=src0.transform).round_offsets().round_lengths()
        ref_transform = src0.window_transform(win0)
        ref_shape = (int(win0.height), int(win0.width))
        # Recalcula bounds alinhados à grade de 30 m da primeira cena
        aligned_bounds = rasterio.windows.bounds(win0, src0.transform)

    print(f"   Grade de referência: {ref_shape} pixels (30 m), CRS={raster_crs}")

    lst_stack = []
    ndvi_stack = []
    albedo_stack = []
    scene_meta = []

    for scene_id in SCENE_IDS:
        print(f"3. Processando cena {scene_id}...")
        item = requests.get(STAC_ITEM_URL.format(scene_id=scene_id), timeout=20).json()
        props = item["properties"]
        assets = item["assets"]

        def read_band(asset_key: str):
            href = assets[asset_key]["href"] + "?" + sas_token
            arr, _, _ = read_window(href, aligned_bounds, ref_shape=ref_shape)
            return arr

        qa = read_band("qa_pixel")
        lwir = read_band("lwir11").astype(np.float32)
        blue = read_band("blue").astype(np.float32)
        red = read_band("red").astype(np.float32)
        nir = read_band("nir08").astype(np.float32)
        swir1 = read_band("swir16").astype(np.float32)
        swir2 = read_band("swir22").astype(np.float32)

        # Bits 0..5 (fill, dilated cloud, cirrus, cloud, cloud shadow, snow) e bit 7 (water)
        cloud_or_fill = (qa & 0b00111111) != 0
        is_water = (qa & (1 << 7)) != 0
        valid_land = (~cloud_or_fill) & (~is_water) & (lwir > 0) & (red > 0) & (nir > 0)

        # Temperatura de superfície (°C)
        lst_c = lwir * 0.00341802 + 149.0 - 273.15
        lst_c = np.where(valid_land & (lst_c > 5.0) & (lst_c < 70.0), lst_c, np.nan)

        # Refletância de superfície (0..1)
        def to_sr(dn):
            sr = dn * 0.0000275 - 0.2
            return np.clip(sr, 0.0, 1.0)

        sr_b = to_sr(blue)
        sr_r = to_sr(red)
        sr_n = to_sr(nir)
        sr_s1 = to_sr(swir1)
        sr_s2 = to_sr(swir2)

        denom = sr_n + sr_r
        ndvi = np.where(valid_land & (denom > 1e-4), (sr_n - sr_r) / np.where(denom > 1e-4, denom, 1.0), np.nan)

        # Albedo de superfície (Liang, 2001)
        albedo = (
            0.356 * sr_b
            + 0.130 * sr_r
            + 0.373 * sr_n
            + 0.085 * sr_s1
            + 0.072 * sr_s2
            - 0.0018
        )
        albedo = np.where(valid_land & (albedo > 0.01) & (albedo < 0.90), albedo, np.nan)

        valid_pct = 100.0 * np.isfinite(lst_c).mean()
        mean_t = float(np.nanmean(lst_c))
        print(f"   -> {props['datetime'][:10]} | {props['platform']} | válidos(terra)={valid_pct:.1f}% | TST média SP={mean_t:.2f} °C")

        lst_stack.append(lst_c)
        ndvi_stack.append(ndvi)
        albedo_stack.append(albedo)
        scene_meta.append({
            "scene_id": scene_id,
            "date": props["datetime"][:10],
            "platform": props["platform"],
            "cloud_cover_scene_pct": props["eo:cloud_cover"],
            "valid_land_pct_sp": round(valid_pct, 2),
            "mean_lst_c_sp": round(mean_t, 2),
        })

    print("4. Calculando composta temporal (mediana pixel-a-pixel, estação quente 2023–2026)...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        lst_med = np.nanmedian(np.stack(lst_stack, axis=0), axis=0).astype(np.float32)
        ndvi_med = np.nanmedian(np.stack(ndvi_stack, axis=0), axis=0).astype(np.float32)
        albedo_med = np.nanmedian(np.stack(albedo_stack, axis=0), axis=0).astype(np.float32)

    # Salva composta raster compacta para mapas de alta resolução
    np.savez_compressed(
        WORKDIR / "landsat_sp_composite.npz",
        lst_c=lst_med,
        ndvi=ndvi_med,
        albedo=albedo_med,
        transform=np.array(ref_transform[:6], dtype=np.float64),
        crs_epsg=np.array([raster_crs.to_epsg()], dtype=np.int32),
    )

    def zonal_stats(gdf_utm: gpd.GeoDataFrame, name_col: str, extra_cols: list[str] | None = None) -> pd.DataFrame:
        shapes = [(geom, idx + 1) for idx, geom in enumerate(gdf_utm.geometry)]
        zone_raster = rasterize(
            shapes=shapes,
            out_shape=ref_shape,
            transform=ref_transform,
            fill=0,
            dtype=np.int32,
        )
        rows = []
        for idx, row in gdf_utm.iterrows():
            mask = zone_raster == (idx + 1)
            t_vals = lst_med[mask]
            t_vals = t_vals[np.isfinite(t_vals)]
            n_vals = ndvi_med[mask]
            n_vals = n_vals[np.isfinite(n_vals)]
            a_vals = albedo_med[mask]
            a_vals = a_vals[np.isfinite(a_vals)]

            rec = {
                name_col: row[name_col],
                "temp_media_c": round(float(np.mean(t_vals)), 2),
                "temp_mediana_c": round(float(np.median(t_vals)), 2),
                "temp_p90_c": round(float(np.percentile(t_vals, 90)), 2),
                "temp_dp_c": round(float(np.std(t_vals)), 2),
                "ndvi_medio": round(float(np.mean(n_vals)), 3),
                "pct_vegetacao_densa": round(float(100.0 * np.mean(n_vals >= 0.45)), 1),
                "albedo_medio": round(float(np.mean(a_vals)), 3),
                "n_pixels_validos": int(t_vals.size),
            }
            if extra_cols:
                for col in extra_cols:
                    rec[col] = row[col]
            rows.append(rec)
        return pd.DataFrame(rows)

    print("5. Calculando estatísticas zonais por Subprefeitura (32)...")
    df_sub = zonal_stats(gdf_sub_utm, "name", extra_cols=["area", "pop_2010", "pop_density_2010"])
    df_sub = df_sub.rename(columns={"name": "subprefeitura"}).sort_values("temp_media_c", ascending=False)
    df_sub.to_csv(WORKDIR / "temperatura_subprefeituras.csv", index=False)

    print("6. Calculando estatísticas zonais por Distrito (96)...")
    df_dist = zonal_stats(gdf_dist_utm, "ds_nome", extra_cols=["ds_subpref", "ds_sigla"])
    df_dist = df_dist.rename(columns={"ds_nome": "distrito", "ds_subpref": "subprefeitura"}).sort_values("temp_media_c", ascending=False)
    df_dist.to_csv(WORKDIR / "temperatura_distritos.csv", index=False)

    with open(WORKDIR / "landsat_metadata.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": "USGS/NASA Landsat 8 & 9 Collection 2 Level-2 via Microsoft Planetary Computer STAC API",
                "wrs_path_row": "219/076",
                "season": "Warm season (Nov-Mar, 2023-2026)",
                "resolution_m": 30,
                "water_masked": True,
                "scenes": scene_meta,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print("\n=== TOP 5 SUBPREFEITURAS MAIS QUENTES (TST média) ===")
    print(df_sub[["subprefeitura", "temp_media_c", "ndvi_medio", "pct_vegetacao_densa", "albedo_medio"]].head(5).to_string(index=False))
    print("\n=== TOP 5 SUBPREFEITURAS MAIS FRESCAS (TST média) ===")
    print(df_sub[["subprefeitura", "temp_media_c", "ndvi_medio", "pct_vegetacao_densa", "albedo_medio"]].tail(5).to_string(index=False))

    print("\n=== RECORTE DO ESTUDO DE CASO (DISTRITOS) ===")
    foco = df_dist[df_dist["distrito"].isin(["JARDIM PAULISTA", "VILA JACUI", "BUTANTA", "ALTO DE PINHEIROS", "SAO MIGUEL", "PARELHEIROS", "MARSILAC", "SE", "BRAS"])]
    print(foco[["distrito", "subprefeitura", "temp_media_c", "temp_p90_c", "ndvi_medio", "pct_vegetacao_densa", "albedo_medio"]].to_string(index=False))


if __name__ == "__main__":
    main()
