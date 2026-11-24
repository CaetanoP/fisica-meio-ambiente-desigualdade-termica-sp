"""
Painel Científico Completo — Física das Ilhas de Calor em São Paulo (IFUSP).

Gera uma figura em 4 painéis integrando:
  (A) Heatmap Térmico Contínuo em 30 m (Landsat 8/9 TST) com destaque para
      Jardim Paulista, Cidade Universitária (Butantã), Vila Jacuí e Parelheiros;
  (B) Mapa Coroplético de Cobertura Vegetal (NDVI) por Distrito (96 distritos),
      evidenciando a relação espacial direta entre arborização e frescor;
  (C) Relação Física TST × NDVI (regressão linear, r = -0,973, R² = 94,7%)
      com pontos coloridos por IDHM e equação do balanço de energia Rn = H + LE + G;
  (D) O Paradoxo Socioespacial: IDHM × TST colorido por % de Vegetação Densa,
      mostrando por que Parelheiros/Perus são frias (Mata Atlântica) enquanto a
      periferia urbana adensada (Vila Jacuí / Itaim Paulista) concentra calor extremo.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd
from rasterio.features import rasterize
from rasterio.transform import Affine
from scipy.stats import linregress, pearsonr

from mapa_bivariado_sp import load_idhm_oficial_sp, normalize_key

warnings.filterwarnings("ignore", category=UserWarning)

WORKDIR = Path(__file__).resolve().parent


def main() -> None:
    # 1. Carrega dados vetoriais, tabulares e raster 30 m
    gdf_sub = gpd.read_file(WORKDIR / "subprefeituras-sp.geojson")
    gdf_dist = gpd.read_file(WORKDIR / "distritos-sp.geojson")
    df_sub = pd.read_csv(WORKDIR / "temperatura_subprefeituras.csv")
    df_dist = pd.read_csv(WORKDIR / "temperatura_distritos.csv")
    df_idhm = load_idhm_oficial_sp()[["chave", "idhm"]]

    comp = np.load(WORKDIR / "landsat_sp_composite.npz")
    lst_c = comp["lst_c"]
    ndvi = comp["ndvi"]
    t_vals = comp["transform"]
    transform = Affine(*t_vals)
    raster_epsg = f"EPSG:{int(comp['crs_epsg'][0])}"

    gdf_sub_r = gdf_sub.to_crs(raster_epsg)
    gdf_dist_r = gdf_dist.to_crs(raster_epsg)

    # Junta IDHM nas subprefeituras
    df_sub["chave"] = df_sub["subprefeitura"].map(normalize_key)
    df_sub = df_sub.merge(df_idhm, on="chave", how="left", validate="1:1")

    # Junta métricas nos 96 distritos
    gdf_dist_r = gdf_dist_r.merge(
        df_dist[["distrito", "temp_media_c", "ndvi_medio", "pct_vegetacao_densa"]],
        left_on="ds_nome",
        right_on="distrito",
        how="left",
    )

    # Máscara exata do limite municipal de São Paulo sobre o raster 30 m
    sp_union = gdf_sub_r.geometry.union_all()
    sp_mask = rasterize(
        [(sp_union, 1)],
        out_shape=lst_c.shape,
        transform=transform,
        fill=0,
        dtype=np.uint8,
    ) == 1
    lst_sp = np.where(sp_mask, lst_c, np.nan)

    # Extensão do raster para imshow
    h, w = lst_sp.shape
    left, top = transform * (0, 0)
    right, bottom = transform * (w, h)
    extent = [left, right, bottom, top]

    # Paleta térmica limpa (azul/teal fresco -> creme -> laranja -> vermelho escuro)
    thermal_cmap = LinearSegmentedColormap.from_list(
        "ifusp_thermal",
        ["#1d4e89", "#2b8cbe", "#7bccc4", "#f7f3d7", "#fdae61", "#e6550d", "#99000d"],
    )
    thermal_cmap.set_bad(alpha=0.0)

    veg_cmap = LinearSegmentedColormap.from_list(
        "ifusp_veg",
        ["#8c2d04", "#d95f0e", "#fed98e", "#a1d99b", "#31a354", "#005a32"],
    )

    # 2. Monta figura 2x2 com estética editorial limpa (alinhada ao PDF do IFUSP)
    fig = plt.figure(figsize=(16, 14.5), dpi=180, facecolor="#f7f6f2")
    gs = fig.add_gridspec(
        2, 2,
        height_ratios=[1.25, 0.92],
        width_ratios=[1.0, 1.0],
        hspace=0.26,
        wspace=0.22,
        left=0.055, right=0.955, top=0.895, bottom=0.075,
    )

    # ── PAINEL A: Heatmap contínuo 30 m (Landsat TST) ──────────────────────────
    ax_a = fig.add_subplot(gs[0, 0])
    ax_a.set_facecolor("#f7f6f2")
    im = ax_a.imshow(lst_sp, extent=extent, cmap=thermal_cmap, vmin=29, vmax=47, origin="upper", interpolation="bilinear")
    gdf_sub_r.boundary.plot(ax=ax_a, color="#1f2937", linewidth=0.45, alpha=0.55)

    # Destaca os 3 bairros/distritos do estudo de caso + Parelheiros
    foco_distritos = {
        "JARDIM PAULISTA": (-15500, 3200, "Jardim Paulista\n37,6 °C · NDVI 0,33"),
        "BUTANTA": (-15500, -5200, "Butantã (USP)\n39,2 °C · NDVI 0,45"),
        "VILA JACUI": (3500, 10500, "Vila Jacuí\n43,5 °C · NDVI 0,24"),
        "PARELHEIROS": (-14000, 0, "Parelheiros\n32,3 °C · NDVI 0,75"),
    }
    for dnome, (dx, dy, lbl) in foco_distritos.items():
        r = gdf_dist_r[gdf_dist_r["ds_nome"] == dnome]
        if r.empty:
            continue
        pt = r.geometry.iloc[0].representative_point()
        r.boundary.plot(ax=ax_a, color="#111827", linewidth=1.3, zorder=5)
        ax_a.scatter(pt.x, pt.y, s=30, color="#111827", edgecolor="white", linewidth=1.0, zorder=6)
        ax_a.annotate(
            lbl,
            xy=(pt.x, pt.y),
            xytext=(pt.x + dx, pt.y + dy),
            fontsize=8.0,
            fontweight="bold",
            color="#111827",
            ha="center" if dnome == "VILA JACUI" else ("left" if dx > 0 else "right"),
            va="center",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#94a3b8", alpha=0.94, lw=0.8),
            arrowprops=dict(arrowstyle="-", color="#111827", lw=1.0, shrinkA=2, shrinkB=4),
            zorder=7,
        )

    minx, miny, maxx, maxy = gdf_sub_r.total_bounds
    ax_a.set_xlim(minx - 18000, maxx + 15000)
    ax_a.set_ylim(miny - 2500, maxy + 3500)
    ax_a.set_axis_off()
    ax_a.set_title("A. Heatmap de Temperatura de Superfície (TST · 30 m)", fontsize=12.2, fontweight="bold", color="#111827", pad=8, loc="left")

    cbar_a = fig.colorbar(im, ax=ax_a, fraction=0.036, pad=0.015, shrink=0.72)
    cbar_a.set_label("TST média — estação quente (°C)", fontsize=8.8, fontweight="bold", color="#1f2937")
    cbar_a.ax.tick_params(labelsize=8)

    # ── PAINEL B: Cobertura Vegetal (NDVI) por Distrito (96 distritos) ─────────
    ax_b = fig.add_subplot(gs[0, 1])
    ax_b.set_facecolor("#f7f6f2")
    gdf_dist_r.plot(
        column="ndvi_medio",
        cmap=veg_cmap,
        vmin=0.14,
        vmax=0.80,
        edgecolor="#ffffff",
        linewidth=0.35,
        ax=ax_b,
    )
    gdf_sub_r.boundary.plot(ax=ax_b, color="#1f2937", linewidth=0.55, alpha=0.5)

    # Anota extremos de vegetação
    veg_notes = {
        "BRAS": (13500, -4500, "Brás (Centro/Leste)\nNDVI 0,15 · 43,5 °C"),
        "VILA JACUI": (12500, 5500, "Vila Jacuí\n9,1% veg. densa"),
        "ALTO DE PINHEIROS": (-15500, 4200, "Alto de Pinheiros\n42,5% veg. densa"),
        "MARSILAC": (-14000, 1000, "Marsilac (Mata Atlântica)\n99,5% veg. densa · 30,9 °C"),
    }
    for dnome, (dx, dy, lbl) in veg_notes.items():
        r = gdf_dist_r[gdf_dist_r["ds_nome"] == dnome]
        if r.empty:
            continue
        pt = r.geometry.iloc[0].representative_point()
        ax_b.scatter(pt.x, pt.y, s=26, color="#111827", edgecolor="white", linewidth=0.9, zorder=6)
        ax_b.annotate(
            lbl,
            xy=(pt.x, pt.y),
            xytext=(pt.x + dx, pt.y + dy),
            fontsize=8.0,
            fontweight="bold",
            color="#111827",
            ha="left" if dx > 0 else "right",
            va="center",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#94a3b8", alpha=0.93, lw=0.8),
            arrowprops=dict(arrowstyle="-", color="#111827", lw=1.0, shrinkA=2, shrinkB=4),
            zorder=7,
        )

    ax_b.set_xlim(minx - 17500, maxx + 17000)
    ax_b.set_ylim(miny - 2500, maxy + 2500)
    ax_b.set_axis_off()
    ax_b.set_title("B. Arborização e Vegetação por Distrito (NDVI · 96 distritos)", fontsize=12.2, fontweight="bold", color="#111827", pad=8, loc="left")

    sm_b = plt.cm.ScalarMappable(cmap=veg_cmap, norm=plt.Normalize(vmin=0.14, vmax=0.80))
    sm_b.set_array([])
    cbar_b = fig.colorbar(sm_b, ax=ax_b, fraction=0.036, pad=0.015, shrink=0.72)
    cbar_b.set_label("NDVI médio (0 = solo/asfalto · 0,8 = mata)", fontsize=8.8, fontweight="bold", color="#1f2937")
    cbar_b.ax.tick_params(labelsize=8)

    # ── PAINEL C: Física do Resfriamento (TST vs NDVI) ─────────────────────────
    ax_c = fig.add_subplot(gs[1, 0])
    ax_c.set_facecolor("#ffffff")

    x_ndvi = df_sub["ndvi_medio"].to_numpy()
    y_tst = df_sub["temp_media_c"].to_numpy()
    c_idhm = df_sub["idhm"].astype(float).to_numpy()

    res = linregress(x_ndvi, y_tst)
    r_val, p_val = pearsonr(x_ndvi, y_tst)
    x_line = np.linspace(0.18, 0.82, 100)
    y_line = res.intercept + res.slope * x_line

    ax_c.plot(x_line, y_line, color="#c84610", lw=2.2, linestyle="--", zorder=2, label="Regressão linear")
    sc_c = ax_c.scatter(x_ndvi, y_tst, c=c_idhm, cmap="viridis", vmin=0.68, vmax=0.95, s=85, edgecolor="#111827", linewidth=0.8, zorder=4)

    # Anota subprefeituras representativas em áreas livres
    labels_c = {
        "Itaim Paulista": (0.045, 0.45, "left"),
        "Vila Maria/Vila Guilherme": (0.045, 0.90, "left"),
        "São Miguel": (0.065, 0.35, "left"),
        "Mooca": (-0.012, -1.65, "left"),
        "Pinheiros": (-0.035, -1.15, "right"),
        "Butantã": (0.055, 0.65, "left"),
        "Capela do Socorro": (0.045, 0.55, "left"),
        "Parelheiros": (-0.055, -0.55, "right"),
    }
    for sub, (dx, dy, ha) in labels_c.items():
        row = df_sub[df_sub["subprefeitura"] == sub].iloc[0]
        ax_c.annotate(
            sub.replace("/Vila Guilherme", ""),
            xy=(row["ndvi_medio"], row["temp_media_c"]),
            xytext=(row["ndvi_medio"] + dx, row["temp_media_c"] + dy),
            fontsize=7.8,
            fontweight="bold",
            color="#1f2937",
            ha=ha,
            arrowprops=dict(arrowstyle="-", color="#64748b", lw=0.75, shrinkA=1, shrinkB=4),
        )

    ax_c.set_xlim(0.16, 0.85)
    ax_c.set_ylim(30.2, 45.2)

    # Caixa de física / estatística
    box_txt = (
        f"r = {r_val:.3f}  (R² = {r_val**2 * 100:.1f}%, p < 10⁻²⁰)\n"
        f"Inclinação: {res.slope:.1f} °C por +1,0 NDVI\n"
        f"(≈ {res.slope * 0.1:.2f} °C a cada +0,10 de NDVI)\n"
        "Balanço: Rₙ = H + LE + G  (↑ árvores ⇒ ↑ LE ⇒ ↓ T)"
    )
    ax_c.text(
        0.97, 0.96, box_txt,
        transform=ax_c.transAxes,
        ha="right", va="top",
        fontsize=8.2, color="#111827",
        bbox=dict(boxstyle="round,pad=0.45", facecolor="#fef3c7", edgecolor="#d97706", alpha=0.92, lw=0.9),
    )

    ax_c.set_xlabel("NDVI médio da Subprefeitura (cobertura vegetal / arborização)", fontsize=9.5, fontweight="bold", color="#111827")
    ax_c.set_ylabel("Temperatura de Superfície média (°C)", fontsize=9.5, fontweight="bold", color="#111827")
    ax_c.set_title("C. Mecanismo Físico: Vegetação explica 95% da variação de TST", fontsize=12.0, fontweight="bold", color="#111827", pad=8, loc="left")
    ax_c.grid(True, linestyle=":", alpha=0.45, color="#94a3b8")
    ax_c.spines["top"].set_visible(False)
    ax_c.spines["right"].set_visible(False)
    cbar_c = fig.colorbar(sc_c, ax=ax_c, pad=0.02, shrink=0.88)
    cbar_c.set_label("IDHM (2010)", fontsize=8.5, fontweight="bold", color="#1f2937")
    cbar_c.ax.tick_params(labelsize=8)

    # ── PAINEL D: O Paradoxo Socioespacial (IDHM vs TST colorido por % Veg) ────
    ax_d = fig.add_subplot(gs[1, 1])
    ax_d.set_facecolor("#ffffff")

    x_idhm = df_sub["idhm"].astype(float).to_numpy()
    c_veg = df_sub["pct_vegetacao_densa"].to_numpy()

    # Faixas interpretativas de fundo (3 regimes socioambientais)
    ax_d.axvspan(0.67, 0.778, ymin=0.0, ymax=0.55, color="#dcfce7", alpha=0.55, zorder=0)
    ax_d.axvspan(0.695, 0.808, ymin=0.66, ymax=1.0, color="#fee2e2", alpha=0.55, zorder=0)
    ax_d.axvspan(0.848, 0.958, ymin=0.42, ymax=0.71, color="#e0f2fe", alpha=0.55, zorder=0)

    ax_d.text(0.676, 37.2, "1. Bordas Florestais / APAs\n(Baixo IDHM, mas frias pela\nMata Atlântica / Cantareira)", fontsize=7.5, color="#166534", fontweight="bold", va="top")
    ax_d.text(0.700, 45.45, "2. Periferia Densa = Desigualdade Térmica\n(Baixo IDHM + pouca árvore + calor extremo)", fontsize=7.5, color="#991b1b", fontweight="bold", va="top")
    ax_d.text(0.953, 37.9, "3. Centro-Oeste Arborizado\n(Alto IDHM + bairros-jardim)", fontsize=7.5, color="#075985", fontweight="bold", ha="right", va="top")

    sc_d = ax_d.scatter(x_idhm, y_tst, c=c_veg, cmap=veg_cmap, vmin=5, vmax=95, s=85, edgecolor="#111827", linewidth=0.8, zorder=4)

    labels_d = {
        "Parelheiros": (0.015, 0.15, "left"),
        "Perus": (0.018, -0.85, "left"),
        "Capela do Socorro": (0.018, 0.15, "left"),
        "Itaim Paulista": (-0.050, -0.45, "left"),
        "São Miguel": (-0.048, -1.05, "left"),
        "Vila Maria/Vila Guilherme": (0.016, 0.35, "left"),
        "Mooca": (0.014, 0.55, "left"),
        "Sé": (-0.016, 0.65, "right"),
        "Pinheiros": (-0.016, -0.60, "right"),
        "Vila Mariana": (-0.006, 1.35, "center"),
        "Butantã": (-0.016, -0.85, "right"),
    }
    for sub, (dx, dy, ha) in labels_d.items():
        row = df_sub[df_sub["subprefeitura"] == sub].iloc[0]
        ax_d.annotate(
            sub.replace("/Vila Guilherme", ""),
            xy=(row["idhm"], row["temp_media_c"]),
            xytext=(row["idhm"] + dx, row["temp_media_c"] + dy),
            fontsize=7.6,
            fontweight="bold",
            color="#1f2937",
            ha=ha,
            arrowprops=dict(arrowstyle="-", color="#64748b", lw=0.75, shrinkA=1, shrinkB=4),
        )

    ax_d.set_xlim(0.67, 0.96)
    ax_d.set_ylim(30.3, 45.8)
    ax_d.set_xlabel("IDHM da Subprefeitura (SMUL/PNUD, 2010)", fontsize=9.5, fontweight="bold", color="#111827")
    ax_d.set_ylabel("Temperatura de Superfície média (°C)", fontsize=9.5, fontweight="bold", color="#111827")
    ax_d.set_title("D. O Paradoxo IDHM × Calor: o papel mediador da arborização", fontsize=12.0, fontweight="bold", color="#111827", pad=8, loc="left")
    ax_d.grid(True, linestyle=":", alpha=0.45, color="#94a3b8")
    ax_d.spines["top"].set_visible(False)
    ax_d.spines["right"].set_visible(False)
    cbar_d = fig.colorbar(sc_d, ax=ax_d, pad=0.02, shrink=0.88)
    cbar_d.set_label("% Área com Vegetação Densa (NDVI ≥ 0,45)", fontsize=8.5, fontweight="bold", color="#1f2937")
    cbar_d.ax.tick_params(labelsize=8)

    # Cabeçalho e rodapé
    fig.text(
        0.055, 0.962,
        "Física das Ilhas de Calor Urbanas em São Paulo: Temperatura, Arborização e IDHM",
        fontsize=17, fontweight="bold", color="#111827", ha="left", va="top",
    )
    fig.text(
        0.055, 0.930,
        "Análise espacial e termodinâmica com imagens reais de satélite Landsat 8/9 (30 m · estação quente 2023–2026) cruzadas com IDHM oficial (SMUL/PNUD)",
        fontsize=10.2, color="#4b5563", ha="left", va="top",
    )
    fig.text(
        0.055, 0.015,
        "Nota física: A TST (banda termal infravermelha 10,9 μm, passagem ~10h30 local) mede a temperatura radiativa da superfície (telhados, asfalto, copas), tipicamente superior à temperatura do ar.\n"
        "A correlação negativa TST × NDVI (r = -0,973) confirma que o resfriamento por calor latente (evapotranspiração, LE) e sombreamento domina sobre pequenas variações de albedo entre materiais urbanos.",
        fontsize=8.0, color="#4b5563", ha="left", va="bottom",
    )

    out_path = WORKDIR / "painel_fisica_ilhas_calor_sp.png"
    fig.savefig(out_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Painel científico salvo em: {out_path}")


if __name__ == "__main__":
    main()
