"""
Gera as 3 figuras sob medida (fundo #FAF9F6, identidade visual do deck IFUSP)
para inserção direta na apresentação PowerPoint:
  1. slide4_mapa_bivariado_deck.png   — Caetano (Slide 4)
  2. slide13_evidencia_fisica_deck.png — Lucas Macor (Slide 13)
  3. slide15_zoom_usp_saoremo_deck.png — Rodrigo Wöss (Slide 15)
"""

from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd
from pyproj import Transformer
from rasterio.transform import Affine
from scipy.stats import linregress, pearsonr

from mapa_bivariado_sp import BIVARIATE_PALETTE, load_idhm_oficial_sp, normalize_key, prepare_bivariate_geodata

warnings.filterwarnings("ignore", category=UserWarning)

WORKDIR = Path(__file__).resolve().parent
OUT_DIR = WORKDIR / "figuras_slides"
OUT_DIR.mkdir(exist_ok=True)

DECK_BG = "#FAF9F6"
ORANGE = "#C2410C"
BLUE = "#1D4ED8"
GREEN = "#15803D"
DARK = "#14181F"
MUTED = "#4B5563"


def make_slide4_bivariate() -> Path:
    """Mapa bivariado (IDHM x TST) otimizado para o quadrante esquerdo do Slide 4."""
    gdf, idhm_bins, temp_bins = prepare_bivariate_geodata(
        geojson_path=WORKDIR / "subprefeituras-sp.geojson",
        temp_csv_path=WORKDIR / "temperatura_subprefeituras.csv",
        geo_name_col="name",
    )

    fig, ax = plt.subplots(figsize=(6.4, 6.2), dpi=240, facecolor=DECK_BG)
    ax.set_facecolor(DECK_BG)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.02)

    gdf.plot(color=gdf["biv_color"], edgecolor="#ffffff", linewidth=0.9, ax=ax)

    destaques = {
        "Pinheiros": (-15500, 1200, "Pinheiros\n0,942 · 38,9 °C"),
        "Butantã": (-15000, -5200, "Butantã (USP)\n0,859 · 39,7 °C"),
        "São Miguel": (9500, 7500, "São Miguel\n0,736 · 43,0 °C"),
        "Itaim Paulista": (9200, -4800, "Itaim Paulista\n0,725 · 43,7 °C"),
        "Mooca": (10500, -11800, "Mooca\n0,869 · 42,6 °C"),
        "Parelheiros": (-13000, -1500, "Parelheiros\n0,680 · 31,5 °C"),
    }

    for nome, (dx, dy, label) in destaques.items():
        row = gdf[gdf["name"] == nome]
        if row.empty:
            continue
        pt = row.geometry.iloc[0].representative_point()
        ax.scatter(pt.x, pt.y, s=24, color=DARK, edgecolor="white", linewidth=0.8, zorder=6)
        ax.annotate(
            label,
            xy=(pt.x, pt.y),
            xytext=(pt.x + dx, pt.y + dy),
            fontsize=7.7,
            fontweight="bold",
            color=DARK,
            ha="left" if dx > 0 else "right",
            va="center",
            bbox=dict(boxstyle="round,pad=0.28", facecolor="white", edgecolor="#cbd5e1", alpha=0.95, lw=0.75),
            arrowprops=dict(arrowstyle="-", color="#334155", lw=0.85, shrinkA=2, shrinkB=3),
            zorder=7,
        )

    minx, miny, maxx, maxy = gdf.total_bounds
    ax.set_xlim(minx - 19500, maxx + 19500)
    ax.set_ylim(miny - 2500, maxy + 3000)
    ax.set_axis_off()

    # Barra de escala 10 km
    sx, sy = minx - 15500, miny + 1500
    ax.plot([sx, sx + 10000], [sy, sy], color=DARK, lw=2.2)
    ax.plot([sx, sx], [sy - 450, sy + 450], color=DARK, lw=1.4)
    ax.plot([sx + 10000, sx + 10000], [sy - 450, sy + 450], color=DARK, lw=1.4)
    ax.text(sx + 5000, sy + 1100, "10 km", ha="center", va="bottom", fontsize=7.8, fontweight="bold", color=DARK)

    # Seta Norte
    nx, ny = minx - 12500, maxy - 4500
    ax.annotate(
        "N",
        xy=(nx, ny + 4200),
        xytext=(nx, ny),
        ha="center",
        va="center",
        fontsize=9,
        fontweight="bold",
        color=DARK,
        arrowprops=dict(arrowstyle="-|>", color=DARK, lw=1.6, mutation_scale=12),
    )

    # Legenda 3x3 compacta e nítida no canto inferior direito
    lax = fig.add_axes([0.67, 0.085, 0.27, 0.255])
    lax.set_facecolor(DECK_BG)
    for (x, y), color in BIVARIATE_PALETTE.items():
        lax.add_patch(Rectangle((x, y), 1, 1, facecolor=color, edgecolor="white", lw=1.3))
    lax.set_xlim(0, 3)
    lax.set_ylim(0, 3)
    lax.set_xticks([])
    lax.set_yticks([])
    for sp in lax.spines.values():
        sp.set_visible(False)

    idhm_l = [f"{idhm_bins[0]:.2f}–{idhm_bins[1]:.2f}", f"{idhm_bins[1]:.2f}–{idhm_bins[2]:.2f}", f"{idhm_bins[2]:.2f}–{idhm_bins[3]:.2f}"]
    temp_l = [f"{temp_bins[0]:.0f}–{temp_bins[1]:.0f}°", f"{temp_bins[1]:.0f}–{temp_bins[2]:.0f}°", f"{temp_bins[2]:.0f}–{temp_bins[3]:.0f}°"]
    for i, lbl in enumerate(idhm_l):
        lax.text(i + 0.5, -0.14, lbl, fontsize=6.4, ha="center", va="top", color=MUTED)
    for j, lbl in enumerate(temp_l):
        lax.text(-0.12, j + 0.5, lbl, fontsize=6.6, ha="right", va="center", color=MUTED)

    lax.text(1.5, -0.50, "IDHM →", fontsize=8.0, fontweight="bold", ha="center", va="top", color=DARK)
    lax.text(-0.92, 1.5, "TST (°C) →", fontsize=8.0, fontweight="bold", ha="center", va="center", rotation=90, color=DARK)
    lax.set_title("Tercis (32 subpref.)", fontsize=8.0, fontweight="bold", pad=4, color=DARK)

    out = OUT_DIR / "slide4_mapa_bivariado_deck.png"
    fig.savefig(out, dpi=240, facecolor=DECK_BG)
    plt.close(fig)
    return out


def make_slide13_physics_evidence() -> Path:
    """Gráfico duplo para o novo Slide 13 do Lucas Macor: TST x NDVI e Paradoxo IDHM/Albedo."""
    df_sub = pd.read_csv(WORKDIR / "temperatura_subprefeituras.csv")
    df_idhm = load_idhm_oficial_sp()[["chave", "idhm"]]
    df_sub["chave"] = df_sub["subprefeitura"].map(normalize_key)
    df_sub = df_sub.merge(df_idhm, on="chave", how="left", validate="1:1")

    veg_cmap = LinearSegmentedColormap.from_list(
        "ifusp_veg",
        ["#9a3412", "#ea580c", "#fbbf24", "#86efac", "#16a34a", "#14532d"],
    )

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.2, 4.75), dpi=240, facecolor=DECK_BG)
    fig.subplots_adjust(left=0.065, right=0.94, top=0.89, bottom=0.14, wspace=0.28)

    # ── Painel 1: TST vs NDVI ─────────────────────────────────────────────────
    ax1.set_facecolor("#FFFFFF")
    x_ndvi = df_sub["ndvi_medio"].to_numpy()
    y_tst = df_sub["temp_media_c"].to_numpy()
    c_idhm = df_sub["idhm"].astype(float).to_numpy()

    res = linregress(x_ndvi, y_tst)
    r_val, _ = pearsonr(x_ndvi, y_tst)
    x_line = np.linspace(0.18, 0.82, 100)
    ax1.plot(x_line, res.intercept + res.slope * x_line, color=BLUE, lw=2.3, ls="--", zorder=2)

    sc1 = ax1.scatter(x_ndvi, y_tst, c=c_idhm, cmap="viridis", vmin=0.68, vmax=0.95, s=88, edgecolor=DARK, lw=0.85, zorder=4)

    lbls1 = {
        "Itaim Paulista": (0.055, 0.42, "left"),
        "Vila Maria/Vila Guilherme": (0.055, 1.08, "left"),
        "São Miguel": (0.055, 0.05, "left"),
        "Pinheiros": (-0.032, -1.25, "right"),
        "Butantã": (0.055, 0.72, "left"),
        "Parelheiros": (-0.015, 1.35, "center"),
    }
    for sub, (dx, dy, ha) in lbls1.items():
        row = df_sub[df_sub["subprefeitura"] == sub].iloc[0]
        ax1.annotate(
            sub.replace("/Vila Guilherme", ""),
            xy=(row["ndvi_medio"], row["temp_media_c"]),
            xytext=(row["ndvi_medio"] + dx, row["temp_media_c"] + dy),
            fontsize=8.2,
            fontweight="bold",
            color=DARK,
            ha=ha,
            arrowprops=dict(arrowstyle="-", color="#64748b", lw=0.8, shrinkA=1, shrinkB=4),
        )

    ax1.text(
        0.04, 0.06,
        f"r = {r_val:.3f}  (R² = {r_val**2 * 100:.1f}%, p < 10⁻²⁰)\n"
        f"−2,0 °C a cada +0,10 de NDVI\n"
        "↑ Árvores ⇒ ↑ Calor Latente (LE) ⇒ ↓ T",
        transform=ax1.transAxes,
        ha="left", va="bottom",
        fontsize=8.4, fontweight="bold", color="#1e3a8a",
        bbox=dict(boxstyle="round,pad=0.45", facecolor="#eff6ff", edgecolor="#93c5fd", lw=0.95),
    )

    ax1.set_xlim(0.16, 0.85)
    ax1.set_ylim(30.2, 45.6)
    ax1.set_xlabel("NDVI médio da Subprefeitura (cobertura vegetal)", fontsize=9.8, fontweight="bold", color=DARK)
    ax1.set_ylabel("Temperatura de Superfície média (°C)", fontsize=9.8, fontweight="bold", color=DARK)
    ax1.set_title("1. Vegetação explica 95% da variação de TST", fontsize=11.3, fontweight="bold", color=DARK, loc="left", pad=8)
    ax1.grid(True, ls=":", alpha=0.45, color="#94a3b8")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    cb1 = fig.colorbar(sc1, ax=ax1, pad=0.02, shrink=0.92)
    cb1.set_label("IDHM (2010)", fontsize=8.4, fontweight="bold", color=DARK)
    cb1.ax.tick_params(labelsize=8)

    # ── Painel 2: Paradoxo do Albedo (TST vs Albedo colorido por % Vegetação) ─
    ax2.set_facecolor("#FFFFFF")
    x_alb = df_sub["albedo_medio"].to_numpy() * 100.0  # em %
    c_veg = df_sub["pct_vegetacao_densa"].to_numpy()

    sc2 = ax2.scatter(x_alb, y_tst, c=c_veg, cmap=veg_cmap, vmin=5, vmax=95, s=88, edgecolor=DARK, lw=0.85, zorder=4)

    lbls2 = {
        "Parelheiros": (0.02, 1.15, "center"),
        "Capela do Socorro": (0.28, 0.25, "left"),
        "Pinheiros": (-0.18, -1.15, "right"),
        "Butantã": (0.36, -0.75, "left"),
        "Sé": (-0.25, 0.85, "right"),
        "Itaim Paulista": (-0.52, 0.85, "right"),
        "São Miguel": (0.14, -1.30, "center"),
        "Vila Maria/Vila Guilherme": (-0.10, 1.10, "right"),
    }
    for sub, (dx, dy, ha) in lbls2.items():
        row = df_sub[df_sub["subprefeitura"] == sub].iloc[0]
        ax2.annotate(
            sub.replace("/Vila Guilherme", ""),
            xy=(row["albedo_medio"] * 100.0, row["temp_media_c"]),
            xytext=(row["albedo_medio"] * 100.0 + dx, row["temp_media_c"] + dy),
            fontsize=8.0,
            fontweight="bold",
            color=DARK,
            ha=ha,
            arrowprops=dict(arrowstyle="-", color="#64748b", lw=0.8, shrinkA=1, shrinkB=4),
        )

    ax2.text(
        0.96, 0.06,
        "Paradoxo Físico Confirmado:\n"
        "• Mata escura (α ≈ 13,7%) → 31,5 °C\n"
        "• Periferia seca (α ≈ 16,3%) → 43,6 °C\n"
        "Evapotranspiração (LE) domina sobre\n"
        "pequenas variações de albedo urbano.",
        transform=ax2.transAxes,
        ha="right", va="bottom",
        fontsize=8.0, fontweight="bold", color="#7c2d12",
        bbox=dict(boxstyle="round,pad=0.45", facecolor="#fff7ed", edgecolor="#fdba74", lw=0.95),
    )

    ax2.set_xlim(13.2, 16.95)
    ax2.set_ylim(30.2, 45.6)
    ax2.set_xlabel("Albedo médio de ondas curtas — α (%) · Landsat 8/9", fontsize=9.8, fontweight="bold", color=DARK)
    ax2.set_ylabel("Temperatura de Superfície média (°C)", fontsize=9.8, fontweight="bold", color=DARK)
    ax2.set_title("2. Por que a mata mais escura é 12 °C mais fria?", fontsize=11.3, fontweight="bold", color=DARK, loc="left", pad=8)
    ax2.grid(True, ls=":", alpha=0.45, color="#94a3b8")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    cb2 = fig.colorbar(sc2, ax=ax2, pad=0.02, shrink=0.92)
    cb2.set_label("% Vegetação Densa (NDVI ≥ 0,45)", fontsize=8.4, fontweight="bold", color=DARK)
    cb2.ax.tick_params(labelsize=8)

    out = OUT_DIR / "slide13_evidencia_fisica_deck.png"
    fig.savefig(out, dpi=240, facecolor=DECK_BG)
    plt.close(fig)
    return out


def make_slide15_usp_saoremo_zoom() -> Path:
    """Zoom térmico real de 30 m (Landsat 8/9) na divisa Campus USP × Comunidade São Remo."""
    comp = np.load(WORKDIR / "landsat_sp_composite.npz")
    lst = comp["lst_c"]
    T = Affine(*comp["transform"])
    epsg = int(comp["crs_epsg"][0])

    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    # Centro entre IFUSP/Campus USP e São Remo (janela ~4,2 km x 3,2 km)
    cx, cy = tr.transform(-46.735, -23.562)
    half_w, half_h = 2150, 1650
    x0, x1 = cx - half_w, cx + half_w
    y0, y1 = cy - half_h, cy + half_h

    c0, r1 = ~T * (x0, y0)
    c1, r0 = ~T * (x1, y1)
    r0, r1 = max(0, int(r0)), min(lst.shape[0], int(r1))
    c0, c1 = max(0, int(c0)), min(lst.shape[1], int(c1))

    patch = lst[r0:r1, c0:c1]
    left, top = T * (c0, r0)
    right, bottom = T * (c1, r1)

    thermal_cmap = LinearSegmentedColormap.from_list(
        "ifusp_thermal",
        ["#1d4e89", "#2b8cbe", "#7bccc4", "#f7f3d7", "#fdae61", "#e6550d", "#99000d"],
    )
    # Corpos d'água mascarados (Raia Olímpica e Rio Pinheiros) em azul-água suave
    thermal_cmap.set_bad("#93c5fd")

    fig, ax = plt.subplots(figsize=(6.8, 5.2), dpi=240, facecolor=DECK_BG)
    ax.set_facecolor("#93c5fd")
    fig.subplots_adjust(left=0.02, right=0.86, top=0.91, bottom=0.06)

    im = ax.imshow(patch, extent=[left, right, bottom, top], cmap=thermal_cmap, vmin=32, vmax=45, origin="upper", interpolation="bilinear")

    # Marcadores reais com coordenadas geográficas exatas
    pontos = [
        (-46.7347, -23.5608, "IFUSP / Campus USP\n36,7 °C (média campus)", (-40, 700), GREEN, "center"),
        (-46.7290, -23.5655, "Mata da CUASO (IB-USP)\n34,7 °C · NDVI 0,70", (-120, -700), GREEN, "center"),
        (-46.7450, -23.5650, "Comunidade São Remo\n42,3 °C · NDVI 0,24", (-140, 860), ORANGE, "center"),
        (-46.7510, -23.5700, "Entorno Rio Pequeno\n43,2 °C", (280, -520), ORANGE, "left"),
    ]
    # Rótulo sutil para Raia Olímpica / Rio Pinheiros
    rx, ry = tr.transform(-46.7215, -23.5500)
    ax.text(rx, ry, "Rio Pinheiros /\nRaia Olímpica", fontsize=7.0, fontweight="bold", color="#1e3a8a", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="#93c5fd", alpha=0.88, lw=0.7), zorder=5)

    for lon, lat, txt, (dx, dy), col, ha in pontos:
        px, py = tr.transform(lon, lat)
        ax.scatter(px, py, s=55, color=col, edgecolor="white", linewidth=1.4, zorder=6)
        ax.annotate(
            txt,
            xy=(px, py),
            xytext=(px + dx, py + dy),
            fontsize=8.2,
            fontweight="bold",
            color=DARK,
            ha=ha,
            va="center",
            bbox=dict(boxstyle="round,pad=0.32", facecolor="white", edgecolor=col, alpha=0.95, lw=1.2),
            arrowprops=dict(arrowstyle="-|>", color=DARK, lw=1.1, shrinkA=2, shrinkB=5),
            zorder=7,
        )

    # Barra de escala 500 m
    sx = left + 180
    sy = bottom + 170
    ax.plot([sx, sx + 500], [sy, sy], color="white", lw=3.8, zorder=7)
    ax.plot([sx, sx + 500], [sy, sy], color=DARK, lw=2.0, zorder=8)
    ax.text(sx + 250, sy + 75, "500 m", ha="center", va="bottom", fontsize=8.2, fontweight="bold",
            color=DARK, bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.85), zorder=9)

    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_edgecolor("#cbd5e1")
        sp.set_linewidth(1.0)

    ax.set_title("Imagem Termal Real (Landsat 8/9 · 30 m): Divisa USP × São Remo", fontsize=10.2, fontweight="bold", color=DARK, pad=8, loc="left")

    cax = fig.add_axes([0.885, 0.12, 0.032, 0.75])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label("TST média — estação quente (°C)", fontsize=8.8, fontweight="bold", color=DARK)
    cb.ax.tick_params(labelsize=8)

    out = OUT_DIR / "slide15_zoom_usp_saoremo_deck.png"
    fig.savefig(out, dpi=240, facecolor=DECK_BG)
    plt.close(fig)
    return out


if __name__ == "__main__":
    for fn in [make_slide4_bivariate, make_slide13_physics_evidence, make_slide15_usp_saoremo_zoom]:
        p = fn()
        print("Gerado:", p)
