"""
Mapa Coroplético Bivariado de São Paulo: IDHM × Temperatura de Superfície (TST).

Versão corrigida e aprimorada do script base, integrada a dados reais de
Temperatura de Superfície Terrestre (Landsat 8/9 C2 L2, estação quente 2023–2026)
e IDHM 2010 oficial por Subprefeitura (SMUL/PNUD).
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle
import numpy as np
import pandas as pd


# Matriz de cores 3x3 (eixo X: IDHM baixo->alto | eixo Y: Temp baixa->alta)
# Paleta clássica de Joshua Stevens (alto contraste visual e boa leitura bivariada)
BIVARIATE_PALETTE: dict[tuple[int, int], str] = {
    (0, 0): "#e8e8e8", (1, 0): "#ace4e4", (2, 0): "#5ac8c8",  # Temp baixa
    (0, 1): "#dfb0d6", (1, 1): "#a5add3", (2, 1): "#5698b9",  # Temp média
    (0, 2): "#be64ac", (1, 2): "#8c62aa", (2, 2): "#3b4994",  # Temp alta
}

# Mapeamento de variações nominais comuns entre GeoSampa/codigourbano e SMUL/PNUD
SUBPREF_ALIASES: dict[str, str] = {
    "CASA VERDE": "CASA VERDE CACHOEIRINHA",
    "SAO MIGUEL": "SAO MIGUEL PAULISTA",
    "GUAIANAZES": "GUAIANASES",
    "ARICANDUVA VILA FORMOSA": "ARICANDUVA FORMOSA CARRAO",
    "ARICANDUVA FORMOSA": "ARICANDUVA FORMOSA CARRAO",
    "FREGUESIA BRASILANDIA": "FREGUESIA DO O BRASILANDIA",
    "M BOI MIRIM": "M'BOI MIRIM",
}


def normalize_key(text: str) -> str:
    """Padroniza nomes de subprefeituras e resolve apelidos/grafias variantes."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("utf-8")
    key = " ".join(text.upper().strip().replace("-", " ").replace("/", " ").split())
    return SUBPREF_ALIASES.get(key, key)


def load_idhm_oficial_sp() -> pd.DataFrame:
    """IDHM 2010 por Subprefeitura (SMUL/PNUD). Sapopemba usa proxy de Vila Prudente (desmembrada em 2013)."""
    dados = [
        ("Pinheiros", 0.942), ("Vila Mariana", 0.938), ("Santo Amaro", 0.909),
        ("Lapa", 0.906), ("Sé", 0.889), ("Mooca", 0.869),
        ("Santana/Tucuruvi", 0.869), ("Butantã", 0.859), ("Ipiranga", 0.824),
        ("Aricanduva/Formosa/Carrão", 0.822), ("Jabaquara", 0.821), ("Penha", 0.804),
        ("Casa Verde/Cachoeirinha", 0.799), ("Vila Maria/Vila Guilherme", 0.793),
        ("Pirituba/Jaraguá", 0.787), ("Vila Prudente", 0.785), ("Campo Limpo", 0.783),
        ("Ermelino Matarazzo", 0.777), ("Jaçanã/Tremembé", 0.768),
        ("Freguesia do Ó/Brasilândia", 0.762), ("Itaquera", 0.758),
        ("Cidade Ademar", 0.758), ("Capela do Socorro", 0.750),
        ("São Miguel Paulista", 0.736), ("São Mateus", 0.732), ("Perus", 0.731),
        ("Itaim Paulista", 0.725), ("M'Boi Mirim", 0.716), ("Guaianases", 0.713),
        ("Cidade Tiradentes", 0.708), ("Parelheiros", 0.680),
        ("Sapopemba", 0.785),  # Proxy de Vila Prudente para malhas com 32 subprefeituras
    ]
    df = pd.DataFrame(dados, columns=["subprefeitura", "idhm"])
    df["subprefeitura"] = df["subprefeitura"].astype("string")
    df["idhm"] = df["idhm"].astype("Float64")
    df["chave"] = df["subprefeitura"].map(normalize_key)
    return df


def prepare_bivariate_geodata(
    geojson_path: str | Path,
    temp_csv_path: str | Path,
    geo_name_col: str = "name",
    target_crs: str = "EPSG:31983",  # SIRGAS 2000 / UTM 23S (projeção oficial GeoSampa)
) -> tuple[gpd.GeoDataFrame, np.ndarray, np.ndarray]:
    """
    Carrega malha, reprojeta para UTM 23S, faz join 1:1 com IDHM e Temperatura
    e atribui tercis e cores bivariadas.
    """
    gdf = gpd.read_file(geojson_path)
    if target_crs:
        gdf = gdf.to_crs(target_crs)
    gdf["chave"] = gdf[geo_name_col].map(normalize_key)

    df_idhm = load_idhm_oficial_sp()[["chave", "idhm"]]
    df_temp = pd.read_csv(temp_csv_path)
    df_temp["subprefeitura"] = df_temp["subprefeitura"].astype("string")
    df_temp["temp_media_c"] = df_temp["temp_media_c"].astype("Float64")
    df_temp["chave"] = df_temp["subprefeitura"].map(normalize_key)

    extra_cols = [c for c in ["ndvi_medio", "pct_vegetacao_densa", "albedo_medio"] if c in df_temp.columns]

    gdf = (
        gdf.merge(df_idhm, on="chave", how="left", validate="1:1")
           .merge(df_temp[["chave", "temp_media_c", *extra_cols]], on="chave", how="left", validate="1:1")
    )

    if gdf["idhm"].isna().any() or gdf["temp_media_c"].isna().any():
        faltantes = gdf.loc[gdf["idhm"].isna() | gdf["temp_media_c"].isna(), geo_name_col].tolist()
        raise ValueError(f"Chaves sem correspondência no merge: {faltantes}")

    # Classificação em tercis (0 = Baixo, 1 = Médio, 2 = Alto) retornando os cortes exatos
    gdf["idhm_bin"], idhm_bins = pd.qcut(
        gdf["idhm"].astype(float), q=3, labels=[0, 1, 2], retbins=True, duplicates="drop"
    )
    gdf["temp_bin"], temp_bins = pd.qcut(
        gdf["temp_media_c"].astype(float), q=3, labels=[0, 1, 2], retbins=True, duplicates="drop"
    )
    gdf["idhm_bin"] = gdf["idhm_bin"].astype(int)
    gdf["temp_bin"] = gdf["temp_bin"].astype(int)
    gdf["biv_color"] = [
        BIVARIATE_PALETTE[(x, y)] for x, y in zip(gdf["idhm_bin"], gdf["temp_bin"])
    ]
    return gdf, idhm_bins, temp_bins


def plot_bivariate_map(
    gdf_prepared: gpd.GeoDataFrame,
    idhm_bins: np.ndarray,
    temp_bins: np.ndarray,
    palette: dict[tuple[int, int], str] = BIVARIATE_PALETTE,
    output_path: str | Path | None = None,
) -> plt.Figure:
    """Gera o mapa coroplético bivariado com legenda numérica, escala, norte e destaques."""
    fig, ax = plt.subplots(figsize=(10.5, 12.2), dpi=180, facecolor="#f7f6f2")
    ax.set_facecolor("#f7f6f2")

    gdf_prepared.plot(
        color=gdf_prepared["biv_color"],
        edgecolor="#ffffff",
        linewidth=1.0,
        ax=ax,
    )

    # Destaque sutil com callouts para subprefeituras-chave do estudo de caso e extremos
    destaques = {
        "Pinheiros": (-19500, 1500, "Pinheiros (Jd. Paulista)\nIDHM 0,942 · 38,9 °C"),
        "Butantã": (-18500, -5200, "Butantã (USP)\nIDHM 0,859 · 39,7 °C"),
        "São Miguel": (13500, 5800, "São Miguel (V. Jacuí)\nIDHM 0,736 · 43,0 °C"),
        "Itaim Paulista": (12500, -3200, "Itaim Paulista\nIDHM 0,725 · 43,7 °C"),
        "Vila Maria/Vila Guilherme": (14500, 11800, "V. Maria / V. Guilherme\nIDHM 0,793 · 43,6 °C"),
        "Mooca": (14000, -10800, "Mooca\nIDHM 0,869 · 42,6 °C"),
        "Parelheiros": (-16500, -1500, "Parelheiros (Mata Atlântica)\nIDHM 0,680 · 31,5 °C"),
    }

    for nome, (dx, dy, label) in destaques.items():
        row = gdf_prepared[gdf_prepared["name"] == nome]
        if row.empty:
            continue
        pt = row.geometry.iloc[0].representative_point()
        ax.scatter(pt.x, pt.y, s=26, color="#1a1a1a", edgecolor="white", linewidth=0.9, zorder=6)
        ax.annotate(
            label,
            xy=(pt.x, pt.y),
            xytext=(pt.x + dx, pt.y + dy),
            fontsize=8.0,
            fontweight="semibold",
            color="#1f2328",
            ha="left" if dx > 0 else "right",
            va="center",
            bbox=dict(boxstyle="round,pad=0.32", facecolor="white", edgecolor="#cbd5e1", alpha=0.93, lw=0.8),
            arrowprops=dict(arrowstyle="-", color="#334155", lw=0.9, shrinkA=2, shrinkB=4),
            zorder=7,
        )

    # Ajusta margens para o mapa preencher bem o quadro e os callouts respirarem
    fig.subplots_adjust(left=0.03, right=0.97, top=0.90, bottom=0.09)
    minx, miny, maxx, maxy = gdf_prepared.total_bounds
    ax.set_xlim(minx - 19000, maxx + 19500)
    ax.set_ylim(miny - 3500, maxy + 3500)
    ax.set_axis_off()

    # Barra de escala de 10 km (UTM está em metros)
    scale_x = minx - 15000
    scale_y = miny + 2000
    ax.plot([scale_x, scale_x + 10000], [scale_y, scale_y], color="#1f2328", lw=2.5)
    ax.plot([scale_x, scale_x], [scale_y - 450, scale_y + 450], color="#1f2328", lw=1.5)
    ax.plot([scale_x + 10000, scale_x + 10000], [scale_y - 450, scale_y + 450], color="#1f2328", lw=1.5)
    ax.text(scale_x + 5000, scale_y + 1100, "10 km", ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="#1f2328")

    # Seta Norte
    north_x = minx - 11000
    north_y = maxy - 5500
    ax.annotate(
        "N",
        xy=(north_x, north_y + 4500),
        xytext=(north_x, north_y),
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color="#1f2328",
        arrowprops=dict(arrowstyle="-|>", color="#1f2328", lw=1.8, mutation_scale=14),
    )

    # Título e subtítulo
    fig.text(
        0.5, 0.968,
        "São Paulo: Desigualdade Socioespacial (IDHM) × Temperatura de Superfície",
        ha="center", va="top", fontsize=15.5, fontweight="bold", color="#111827",
    )
    fig.text(
        0.5, 0.938,
        "Mapa bivariado por Subprefeitura (tercis) · TST média da estação quente (Landsat 8/9 C2 L2, 2023–2026) · IDHM 2010 (SMUL/PNUD)",
        ha="center", va="top", fontsize=9.3, color="#4b5563",
    )

    # Legenda 3x3 no canto inferior direito (bem acima do rodapé) com intervalos numéricos reais
    legend_ax = fig.add_axes([0.67, 0.165, 0.22, 0.195])
    legend_ax.set_facecolor("#f7f6f2")
    for (x, y), color in palette.items():
        legend_ax.add_patch(Rectangle((x, y), 1, 1, facecolor=color, edgecolor="white", lw=1.4))

    legend_ax.set_xlim(0, 3)
    legend_ax.set_ylim(0, 3)
    legend_ax.set_xticks([])
    legend_ax.set_yticks([])
    for spine in legend_ax.spines.values():
        spine.set_visible(False)

    # Rótulos dos intervalos reais dos tercis
    idhm_labels = [f"{idhm_bins[0]:.2f}–{idhm_bins[1]:.2f}", f"{idhm_bins[1]:.2f}–{idhm_bins[2]:.2f}", f"{idhm_bins[2]:.2f}–{idhm_bins[3]:.2f}"]
    temp_labels = [f"{temp_bins[0]:.1f}–{temp_bins[1]:.1f}°", f"{temp_bins[1]:.1f}–{temp_bins[2]:.1f}°", f"{temp_bins[2]:.1f}–{temp_bins[3]:.1f}°"]

    for i, lbl in enumerate(idhm_labels):
        legend_ax.text(i + 0.5, -0.14, lbl, fontsize=7.0, ha="center", va="top", color="#374151")
    for j, lbl in enumerate(temp_labels):
        legend_ax.text(-0.12, j + 0.5, lbl, fontsize=7.0, ha="right", va="center", color="#374151")

    legend_ax.text(1.5, -0.46, "IDHM (menor → maior)", fontsize=8.8, fontweight="bold", ha="center", va="top", color="#111827")
    legend_ax.text(-1.05, 1.5, "TST (°C) →", fontsize=8.8, fontweight="bold", ha="center", va="center", rotation=90, color="#111827")
    legend_ax.set_title("Legenda (Tercis)", fontsize=9.4, fontweight="bold", pad=6, color="#111827")

    # Nota de interpretação nos cantos + fonte
    fig.text(
        0.04, 0.018,
        "Leitura física: Magenta (#be64ac) = menor IDHM + maior calor (ex.: Itaim Paulista, São Miguel); "
        "Cinza claro (#e8e8e8) = menor IDHM + menor calor por vegetação preservada (ex.: Parelheiros, Perus);\n"
        "Ciano (#5ac8c8) = maior IDHM + menor calor (ex.: Pinheiros); "
        "Azul escuro (#3b4994) = maior IDHM + maior calor por impermeabilização/uso industrial (ex.: Mooca, Aricanduva, Jabaquara).\n"
        "Fontes: USGS/NASA Landsat 8/9 C2 L2 (6 cenas de verão/primavera, 30 m, máscara QA_PIXEL sem nuvens/água) · IDHM 2010 (SMUL/PNUD) · Malha GeoSampa/codigourbano (EPSG:31983).",
        fontsize=7.3, color="#4b5563", ha="left", va="bottom",
    )

    if output_path:
        fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    return fig


if __name__ == "__main__":
    workdir = Path(__file__).resolve().parent
    gdf_ready, idhm_bins, temp_bins = prepare_bivariate_geodata(
        geojson_path=workdir / "subprefeituras-sp.geojson",
        temp_csv_path=workdir / "temperatura_subprefeituras.csv",
        geo_name_col="name",  # No shapefile oficial do GeoSampa, troque para 'sp_nome'
    )
    out = workdir / "mapa_idhm_temperatura_sp.png"
    plot_bivariate_map(gdf_ready, idhm_bins, temp_bins, output_path=out)
    print(f"Mapa salvo com sucesso em: {out}")
