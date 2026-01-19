#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remote ID x ERBs (sniffers passivos) — Heatmap de cobertura + métricas por bucket

O que este script faz:
1) Lê um CSV de ERBs (torres) e trata cada torre como um sniffer (receptor passivo).
2) (Opcional) Lê pontos de voo (utm_points_with_flightid.csv) e buckets (position_bucket.csv)
   para calcular cobertura efetiva por bucket de tempo.
3) Gera um mapa HTML (Folium) com heatmap de "capacidade de detecção" (cobertura) por operadora
   e opcionalmente sobrepõe trajetórias/points dos voos.

Requisitos:
  pip install numpy pandas folium scikit-learn
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import folium
from folium.plugins import HeatMap
from sklearn.neighbors import BallTree


# -----------------------------
# CONFIGURAÇÕES 
# -----------------------------

# --- Entradas ---
TOWERS_CSV_PATH = "data/Estacoes_SMP_interlagos.csv"  
TOWERS_SEP = ";"
FLIGHT_POINTS_CSV = "data/utm_points_with_flightid.csv"   # colunas: flight_id,lon,lat,alt,timestamp
BUCKETS_CSV = "data/position_bucket.csv"                  # colunas: Flight ID, Bucket Start, Bucket End

# --- Filtros (opcionais) ---
FILTER_MUNICIPIO_UF = None  # ex: "São Paulo - SP" (ou None)
FILTER_OPERADORAS = None    # ex: {"VIVO", "CLARO"} (ou None)
FILTER_FLIGHT_IDS = None    # ex: {"1ZNBK5900C00A8"} (ou None)
FILTER__TECH = None

# --- Modelo de rádio / Remote ID ---
MODEL = "fspl"  # "fspl" (recomendado p/ 2.4 GHz) ou "cost231" (aproximação macrocelular)

REMOTEID_FREQ_MHZ = 2400.0   # ex: 2400 (Wi-Fi/BLE) — ajuste para o seu Remote ID
DRONE_EIRP_DBM = 20.0        # potência efetiva do transmissor Remote ID (ajuste/calibre)
SNIFFER_ANT_GAIN_DB = 0.0    # ganho antena do sniffer na torre (se quiser)
SNIFFER_CABLE_LOSS_DB = 0.0  # perdas de cabo/conector no sniffer (se quiser)
EXTRA_CLUTTER_LOSS_DB = 15.0 # perdas adicionais (urbanização/NLoS/interferência) — calibração principal

DETECTION_THRESHOLD_DBM = -90.0  # limiar de detecção do sniffer (sensibilidade efetiva)

# Alturas
TOWER_HEIGHT_M = 30.0        # altura típica do sniffer na torre (se não tiver no CSV)
HEATMAP_DRONE_ALT_M = 120.0  # altitude assumida do drone (para o heatmap)

# --- Heatmap ---
GRID_STEP_M = 50.0          # resolução do grid (metros). Menor = mais preciso, mais lento
MAP_MARGIN_M = 1500.0        # margem em metros ao redor da área das torres/pontos de voo
MAX_RANGE_KM = 15.0          # raio máximo para considerar torres (acelera). Ajuste conforme cenário

# Normalização do peso do heatmap (RSSI -> 0..1)
WEIGHT_MIN_DBM = -115.0
WEIGHT_MAX_DBM = -70.0

# --- Métricas por bucket ---
COMPUTE_BUCKET_METRICS = True
K_REDUNDANCY = (1, 2, 3)     # métricas para >=k torres detectando

# --- Overlay de voos no mapa ---
DRAW_FLIGHT_POINTS = True
MAX_POINTS_TO_DRAW = 0     # limite para não pesar o HTML


# --- Anti-spoofing: Consistência Físico–Digital (Métrica chave) ---
# Ideia: comparar a distância estimada via RSSI (Modelo Log-Distance) com a distância
# inferida a partir do GPS reportado no payload do Remote ID.
COMPUTE_ANTISPOOF_METRICS = True

# Se True, injeta trajetórias falsas (spoof) no dataset para avaliação (experimento).
INJECT_SPOOFING_ATTACKS = True
ATTACK_MODE = "near_best_tower"   # "near_best_tower" (gera ε alto) ou "random_far"
ATTACK_FLIGHT_FRACTION = 0.30     # fração de voos rotulados como ataque (0..1)
ATTACK_SEED = 7
ATTACK_NEAR_TOWER_RADIUS_M = 30.0 # para "near_best_tower": GPS falso perto do sniffer

# RSSI "medido": o script simula RSSI com base no modelo atual e adiciona ruído gaussiano (dB)
RSSI_NOISE_STD_DB = 3.0
MAX_POINTS_ANTISPOOF = 0      # 0 = usa todos; >0 = amostra aleatória

# Modelo Log-Distance (para estimar distância a partir de RSSI)
LOGDIST_D0_M = 1.0
LOGDIST_PATHLOSS_EXPONENT_N = 2.2   # ~2 (LoS) .. ~3.5 (urbano/NLoS)
LOGDIST_RSSI0_DBM = None            # se None, calcula a partir de FSPL em d0 e parâmetros atuais

# Métrica residual normalizada
#   ε = |D_RSSI - D_GPS| / D_GPS
EPS_HONEST_MAX = 0.2
EPS_ATTACK_MIN = 1.0
EPS_DECISION_THRESHOLD = 0.6        # limiar p/ classificar "ataque" e montar matriz de confusão

# -----------------------------
# UTILITÁRIOS
# -----------------------------

def pick_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = {c.strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in cols:
            return cols[key]
    return None

def to_float_series(s: pd.Series) -> pd.Series:
    # aceita vírgula decimal
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")

def haversine_km_vec(lat1_deg: np.ndarray, lon1_deg: np.ndarray, lat2_deg: float, lon2_deg: float) -> np.ndarray:
    """Distância Haversine (km) entre arrays (lat1,lon1) e um ponto (lat2,lon2)."""
    R = 6371.0
    lat1 = np.deg2rad(lat1_deg)
    lon1 = np.deg2rad(lon1_deg)
    lat2 = math.radians(lat2_deg)
    lon2 = math.radians(lon2_deg)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * math.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return R * c

def dist_3d_km(d_hor_km: np.ndarray, dz_m: np.ndarray) -> np.ndarray:
    return np.sqrt(d_hor_km**2 + (dz_m / 1000.0)**2)

def fspl_db(f_mhz: float, d_km: np.ndarray) -> np.ndarray:
    # FSPL(dB) = 32.44 + 20log10(f_MHz) + 20log10(d_km)
    d = np.maximum(d_km, 1e-6)
    return 32.44 + 20.0 * np.log10(f_mhz) + 20.0 * np.log10(d)

def cost231_hata_pathloss_db(f_mhz: float, d_km: np.ndarray, hb_m: float, hr_m: float, metropolitan: bool = False) -> np.ndarray:
    """
    COST-231 Hata (aproximação). Lembrete: é um modelo macrocelular; para 2.4 GHz use FSPL por padrão.
    """
    d = np.maximum(d_km, 1e-6)
    logf = np.log10(f_mhz)
    a_hr = (1.1 * logf - 0.7) * hr_m - (1.56 * logf - 0.8)
    C = 3.0 if metropolitan else 0.0
    return 46.3 + 33.9 * logf - 13.82 * np.log10(hb_m) - a_hr + (44.9 - 6.55 * np.log10(hb_m)) * np.log10(d) + C

def rssi_dbm_from_distance(
    d_km: np.ndarray,
    f_mhz: float,
    tx_eirp_dbm: float,
    rx_ant_gain_db: float,
    rx_cable_loss_db: float,
    extra_losses_db: float,
    model: str,
    hb_m_for_cost231: float = 30.0,
    hr_m_for_cost231: float = 1.5,
    metropolitan: bool = False,
) -> np.ndarray:
    if model == "fspl":
        pl = fspl_db(f_mhz, d_km)
    elif model == "cost231":
        pl = cost231_hata_pathloss_db(f_mhz, d_km, hb_m_for_cost231, hr_m_for_cost231, metropolitan)
    else:
        raise ValueError("MODEL deve ser 'fspl' ou 'cost231'")

    return (tx_eirp_dbm + rx_ant_gain_db) - rx_cable_loss_db - pl - extra_losses_db
    
def normalize_weight(rssi_dbm: np.ndarray, lo: float, hi: float) -> np.ndarray:
    w = (rssi_dbm - lo) / (hi - lo)
    return np.clip(w, 0.0, 1.0)

def make_grid(lat_min, lat_max, lon_min, lon_max, step_m: float) -> Tuple[np.ndarray, np.ndarray]:
    # Aproximação: 1 grau lat ~ 111.32 km
    dlat = step_m / 111_320.0
    lat_mid = 0.5 * (lat_min + lat_max)
    dlon = step_m / (111_320.0 * max(math.cos(math.radians(lat_mid)), 1e-6))

    lats = np.arange(lat_min, lat_max + dlat, dlat)
    lons = np.arange(lon_min, lon_max + dlon, dlon)

    # Retorna malha em vetores 1D (mesh)
    LAT, LON = np.meshgrid(lats, lons, indexing="ij")
    return LAT.ravel(), LON.ravel()

def margin_deg_lat(m: float) -> float:
    return m / 111_320.0

def margin_deg_lon(m: float, lat_deg: float) -> float:
    return m / (111_320.0 * max(math.cos(math.radians(lat_deg)), 1e-6))

# -----------------------------
# CARREGAMENTO DE TORRES
# -----------------------------

@dataclass
class TowerData:
    df: pd.DataFrame
    lat: np.ndarray
    lon: np.ndarray
    op: np.ndarray
    tower_id: np.ndarray
    tree: BallTree
    tech: str

def load_towers(csv_path: str, sep: str) -> TowerData:
    df = pd.read_csv(csv_path, sep=sep, dtype=str)

    col_id = pick_col(df, ["Número Estação", "Numero Estacao", "station_id", "id", "ID", "CODIGO"])
    col_lat = pick_col(df, ["lat", "latitude", "Latitude", "LAT", "LATITUDE"])
    col_lon = pick_col(df, ["lon", "longitude", "Longitude", "LON", "LONGITUDE"])
    col_op  = pick_col(df, ["operadora", "op", "empresa", "provedor", "Prestadora", "Operadora", "EMPRESA", "Empresa Estação", "Entidade"]) 
    col_mun = pick_col(df, ["Município - UF", "Municipio - UF", "municipio_uf", "municipio"])
    col_tech = pick_col(df, ["Tecnologia", "Tipo de Tecnologia 5G", "Geração"])

    if col_lat is None or col_lon is None:
        raise ValueError("Não encontrei colunas de latitude/longitude no CSV de torres.")

    df["lat"] = to_float_series(df[col_lat])
    df["lon"] = to_float_series(df[col_lon])
    df = df.dropna(subset=["lat", "lon"]).copy()

    if col_op is None:
        df["operadora"] = "UNKNOWN"
    else:
        df["operadora"] = df[col_op].astype(str).str.strip()

    # filtro município
    if FILTER_MUNICIPIO_UF is not None and col_mun is not None:
        df = df[df[col_mun].astype(str).str.strip() == FILTER_MUNICIPIO_UF].copy()

    # filtro operadoras
    if FILTER_OPERADORAS is not None:
        df = df[df["operadora"].isin(FILTER_OPERADORAS)].copy()

    # filtro tecnologia
    if FILTER__TECH is not None:
        df = df[df["tech"].isin(FILTER__TECH)].copy()

    if col_id is None:
        df["tower_id"] = np.arange(len(df)).astype(str)
    else:
        df["tower_id"] = df[col_id].astype(str).str.strip()

    if col_tech is None:
        df["tech"] = "UNKNOWN"
    else:
        df["tech"] = df[col_tech].astype(str).str.strip()

    # Dedup simples (operadora + lat/lon arredondados)
    df["lat_r"] = df["lat"].round(6)
    df["lon_r"] = df["lon"].round(6)
    before = len(df)

    df = df.drop_duplicates(subset=["operadora", "tower_id", "lat_r", "lon_r", "tech"]).copy()
    after = len(df)
    print(f"Dedup OK: {before} -> {after} torres (removidas {before-after} duplicatas)")

    lat = df["lat"].to_numpy(float)
    lon = df["lon"].to_numpy(float)
    op = df["operadora"].to_numpy(str)
    tower_id = df["tower_id"].to_numpy(str)
    tech = df["tech"].to_numpy(str)

    coords_rad = np.deg2rad(np.c_[lat, lon])
    tree = BallTree(coords_rad, metric="haversine")

    return TowerData(df=df, lat=lat, lon=lon, op=op, tower_id=tower_id, tree=tree, tech=tech)



# -----------------------------
# ANTI-SPOOFING (Consistência Físico–Digital)
# -----------------------------

def haversine_km_pairwise(lat1_deg: np.ndarray, lon1_deg: np.ndarray, lat2_deg: np.ndarray, lon2_deg: np.ndarray) -> np.ndarray:
    """Haversine (km) para pares correspondentes (lat1,lon1) <-> (lat2,lon2)."""
    R = 6371.0
    lat1 = np.deg2rad(lat1_deg)
    lon1 = np.deg2rad(lon1_deg)
    lat2 = np.deg2rad(lat2_deg)
    lon2 = np.deg2rad(lon2_deg)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return R * c

def logdistance_rssi_dbm(d_m: np.ndarray, rssi0_dbm: float, d0_m: float, n: float) -> np.ndarray:
    """Modelo Log-Distance: RSSI(d) = RSSI(d0) - 10*n*log10(d/d0)."""
    d = np.maximum(np.asarray(d_m, dtype=float), 1e-6)
    return rssi0_dbm - 10.0 * n * np.log10(d / float(d0_m))

def logdistance_distance_m_from_rssi(rssi_dbm: np.ndarray, rssi0_dbm: float, d0_m: float, n: float) -> np.ndarray:
    """Inversão do Log-Distance: d = d0 * 10^((RSSI0 - RSSI)/(10*n))."""
    rssi = np.asarray(rssi_dbm, dtype=float)
    expo = (float(rssi0_dbm) - rssi) / (10.0 * float(n))
    d_m = float(d0_m) * (10.0 ** expo)
    return np.maximum(d_m, 1e-6)

def default_logdist_rssi0_dbm() -> float:
    """Se LOGDIST_RSSI0_DBM=None, calcula RSSI(d0) via FSPL + link budget atual."""
    d0_km = float(LOGDIST_D0_M) / 1000.0
    # usa FSPL como referência em d0; extra_losses entra para refletir ambiente (clutter)
    pl0 = fspl_db(REMOTEID_FREQ_MHZ, np.asarray([d0_km], dtype=float))[0]
    link_budget = (DRONE_EIRP_DBM + SNIFFER_ANT_GAIN_DB) - SNIFFER_CABLE_LOSS_DB
    return float(link_budget - pl0 - EXTRA_CLUTTER_LOSS_DB)

def jitter_latlon_around(lat_deg: float, lon_deg: float, radius_m: float, rng: np.random.Generator) -> Tuple[float, float]:
    """Gera (lat,lon) aleatório em um círculo de raio radius_m ao redor do ponto."""
    # amostra uniforme em área
    r = float(radius_m) * math.sqrt(float(rng.random()))
    theta = 2.0 * math.pi * float(rng.random())
    north_m = r * math.cos(theta)
    east_m = r * math.sin(theta)

    dlat = north_m / 111_320.0
    dlon = east_m / (111_320.0 * max(math.cos(math.radians(lat_deg)), 1e-6))
    return lat_deg + dlat, lon_deg + dlon

def prepare_remoteid_payload_columns(flight_points: pd.DataFrame) -> pd.DataFrame:
    """Cria colunas 'true_*' (posição física) e 'rid_*' (posição reportada no Remote ID)."""
    fp = flight_points.copy()
    fp["true_lat"] = fp["lat"]
    fp["true_lon"] = fp["lon"]
    fp["true_alt"] = fp["alt"]
    fp["rid_lat"] = fp["lat"]
    fp["rid_lon"] = fp["lon"]
    fp["rid_alt"] = fp["alt"]
    fp["is_attack"] = False
    return fp

def inject_spoofing_attacks(
    fp: pd.DataFrame,
    tower: TowerData,
    best_tower_idx: np.ndarray,
) -> pd.DataFrame:
    """Introduce trajetórias falsas (spoof) alterando apenas o GPS reportado (rid_*)."""
    if not INJECT_SPOOFING_ATTACKS:
        return fp

    rng = np.random.default_rng(ATTACK_SEED)
    fids = fp["flight_id"].astype(str).unique().tolist()
    if len(fids) == 0:
        return fp

    n_attack = int(math.ceil(float(ATTACK_FLIGHT_FRACTION) * len(fids)))
    n_attack = max(0, min(n_attack, len(fids)))
    attack_fids = set(rng.choice(fids, size=n_attack, replace=False).tolist()) if n_attack > 0 else set()

    fp = fp.copy()
    fp["is_attack"] = fp["flight_id"].astype(str).isin(attack_fids)

    if len(attack_fids) == 0:
        return fp

    # Onde não temos best tower (-1), usa torre mais próxima (k=1).
    idx = np.asarray(best_tower_idx, dtype=int)
    missing = (idx < 0)
    if np.any(missing):
        pts_rad = np.deg2rad(np.c_[fp.loc[missing, "true_lat"].to_numpy(float), fp.loc[missing, "true_lon"].to_numpy(float)])
        _, nn_idx = tower.tree.query(pts_rad, k=1)
        idx[missing] = nn_idx[:, 0].astype(int)

    if ATTACK_MODE == "near_best_tower":
        # GPS falso "colado" no sniffer (torre escolhida) + jitter pequeno
        at_mask = fp["is_attack"].to_numpy(bool)
        for i in np.where(at_mask)[0]:
            tidx = int(idx[i])
            lat0 = float(tower.lat[tidx])
            lon0 = float(tower.lon[tidx])
            lat_fake, lon_fake = jitter_latlon_around(lat0, lon0, ATTACK_NEAR_TOWER_RADIUS_M, rng)
            fp.at[i, "rid_lat"] = lat_fake
            fp.at[i, "rid_lon"] = lon_fake
            # mantém altitude reportada (poderia também ser spoofada)
            fp.at[i, "rid_alt"] = float(fp.at[i, "true_alt"])
    elif ATTACK_MODE == "random_far":
        # GPS falso aleatório dentro do bounding box das torres (gera inconsistência moderada)
        lat_min, lat_max = float(tower.lat.min()), float(tower.lat.max())
        lon_min, lon_max = float(tower.lon.min()), float(tower.lon.max())
        at_mask = fp["is_attack"].to_numpy(bool)
        fp.loc[at_mask, "rid_lat"] = rng.uniform(lat_min, lat_max, size=int(np.sum(at_mask)))
        fp.loc[at_mask, "rid_lon"] = rng.uniform(lon_min, lon_max, size=int(np.sum(at_mask)))
        fp.loc[at_mask, "rid_alt"] = fp.loc[at_mask, "true_alt"].to_numpy(float)
    else:
        raise ValueError("ATTACK_MODE inválido. Use 'near_best_tower' ou 'random_far'.")

    return fp

def compute_physdig_consistency_metrics(
    fp: pd.DataFrame,
    tower: TowerData,
    max_range_km: float,
) -> pd.DataFrame:
    """
    Calcula:
      - D_RSSI: distância estimada a partir do RSSI (Log-Distance)
      - D_GPS: distância 3D inferida do GPS reportado (Remote ID payload)
      - ε = |D_RSSI - D_GPS| / D_GPS
    Retorna um DataFrame com métricas ponto-a-ponto e imprime a matriz de confusão.
    """
    if fp is None or fp.empty:
        return pd.DataFrame()

    # (Opcional) amostragem para reduzir custo computacional
    if int(MAX_POINTS_ANTISPOOF) > 0 and len(fp) > int(MAX_POINTS_ANTISPOOF):
        fp = fp.sample(int(MAX_POINTS_ANTISPOOF), random_state=ATTACK_SEED).sort_values("timestamp")

    # 1) RSSI "medido" (simulado a partir do modelo atual + ruído)
    best_rssi_dbm, _, best_idx = detect_at_points(
        tower,
        fp["true_lat"].to_numpy(float),
        fp["true_lon"].to_numpy(float),
        fp["true_alt"].to_numpy(float),
        max_range_km=max_range_km,
    )
    rng = np.random.default_rng(ATTACK_SEED)
    measured_rssi = best_rssi_dbm + rng.normal(0.0, float(RSSI_NOISE_STD_DB), size=len(best_rssi_dbm))

    # 2) injeta ataques (altera apenas rid_*), usando a melhor torre como "sniffer"
    fp2 = inject_spoofing_attacks(fp, tower, best_idx)

    # 3) torre associada por ponto (melhor RSSI). fallback p/ mais próxima se -1
    idx = np.asarray(best_idx, dtype=int)
    missing = (idx < 0)
    if np.any(missing):
        pts_rad = np.deg2rad(np.c_[fp2.loc[missing, "true_lat"].to_numpy(float), fp2.loc[missing, "true_lon"].to_numpy(float)])
        _, nn_idx = tower.tree.query(pts_rad, k=1)
        idx[missing] = nn_idx[:, 0].astype(int)

    tlat = tower.lat[idx]
    tlon = tower.lon[idx]

    # 4) D_GPS: distância 3D da torre até o GPS reportado no Remote ID
    d_hor_gps_km = haversine_km_pairwise(tlat, tlon, fp2["rid_lat"].to_numpy(float), fp2["rid_lon"].to_numpy(float))
    dz_gps_m = fp2["rid_alt"].to_numpy(float) - float(TOWER_HEIGHT_M)
    d_gps_km = dist_3d_km(d_hor_gps_km, dz_gps_m)

    # 5) D_RSSI: inversão do modelo Log-Distance
    rssi0 = float(LOGDIST_RSSI0_DBM) if LOGDIST_RSSI0_DBM is not None else default_logdist_rssi0_dbm()
    d_rssi_m = logdistance_distance_m_from_rssi(measured_rssi, rssi0_dbm=rssi0, d0_m=LOGDIST_D0_M, n=LOGDIST_PATHLOSS_EXPONENT_N)
    d_rssi_km = d_rssi_m / 1000.0

    # 6) ε
    eps = np.abs(d_rssi_km - d_gps_km) / np.maximum(d_gps_km, 1e-6)

    out = fp2.copy()
    out["best_rssi_dbm"] = best_rssi_dbm
    out["measured_rssi_dbm"] = measured_rssi
    out["tower_idx"] = idx
    out["tower_lat"] = tlat
    out["tower_lon"] = tlon
    out["D_GPS_km"] = d_gps_km
    out["D_RSSI_km"] = d_rssi_km
    out["epsilon"] = eps

    # 7) Avaliação (matriz de confusão)
    y_true = out["is_attack"].to_numpy(bool)
    y_pred = (out["epsilon"].to_numpy(float) >= float(EPS_DECISION_THRESHOLD))

    tp = int(np.sum(y_true & y_pred))
    fp_ = int(np.sum((~y_true) & y_pred))
    tn = int(np.sum((~y_true) & (~y_pred)))
    fn = int(np.sum(y_true & (~y_pred)))

    # estatísticas rápidas (o que você quer mostrar no paper/relatório)
    def _pct(x: np.ndarray, q: float) -> float:
        x = x[np.isfinite(x)]
        return float(np.quantile(x, q)) if len(x) else float("nan")

    eps_hon = out.loc[~out["is_attack"], "epsilon"].to_numpy(float)
    eps_att = out.loc[out["is_attack"], "epsilon"].to_numpy(float)

    print("\n=== Anti-Spoofing: Consistência Físico–Digital ===")
    print(f"RSSI0(d0) usado no Log-Distance: {rssi0:.2f} dBm (d0={LOGDIST_D0_M} m, n={LOGDIST_PATHLOSS_EXPONENT_N})")
    print(f"Ruído RSSI (σ): {float(RSSI_NOISE_STD_DB):.1f} dB")
    print(f"Totais: honest={int(np.sum(~y_true))} | ataque={int(np.sum(y_true))}")
    print(f"ε (honest): p50={_pct(eps_hon,0.50):.3f} p90={_pct(eps_hon,0.90):.3f} p99={_pct(eps_hon,0.99):.3f} | frac(ε<{EPS_HONEST_MAX})={float(np.mean(eps_hon < EPS_HONEST_MAX)) if len(eps_hon) else float('nan'):.3f}")
    print(f"ε (ataque): p50={_pct(eps_att,0.50):.3f} p10={_pct(eps_att,0.10):.3f} | frac(ε>{EPS_ATTACK_MIN})={float(np.mean(eps_att > EPS_ATTACK_MIN)) if len(eps_att) else float('nan'):.3f}")
    print(f"Decisão: ataque se ε >= {float(EPS_DECISION_THRESHOLD):.2f}")

    # matriz de confusão
    print("\nMatriz de Confusão (linhas=True, colunas=Pred):")
    print("            Pred Honest   Pred Ataque")
    print(f"True Honest     {tn:6d}       {fp_:6d}")
    print(f"True Ataque     {fn:6d}       {tp:6d}")

    precision = tp / (tp + fp_) if (tp + fp_) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    fpr = fp_ / (fp_ + tn) if (fp_ + tn) else float("nan")
    print(f"Precision={precision:.3f} | Recall/TPR={recall:.3f} | FPR={fpr:.3f}")

    # salva outputs
    out_csv = "antispoof_point_metrics.csv"
    out.to_csv(out_csv, index=False)
    print(f"Detalhes ponto-a-ponto salvos em: {out_csv}")

    cm_csv = "antispoof_confusion_matrix.csv"
    pd.DataFrame([{
        "threshold_epsilon": float(EPS_DECISION_THRESHOLD),
        "TN": tn, "FP": fp_, "FN": fn, "TP": tp,
        "precision": precision, "recall": recall, "fpr": fpr,
    }]).to_csv(cm_csv, index=False)
    print(f"Matriz de confusão salva em: {cm_csv}")

    return out


# -----------------------------
# CÁLCULO DE DETECÇÃO (por ponto)
# -----------------------------

def detect_at_points(
    tower: TowerData,
    pts_lat: np.ndarray,
    pts_lon: np.ndarray,
    pts_alt_m: np.ndarray,
    drone_alt_is_used: bool = True,
    max_range_km: float = 15.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Para cada ponto (drone), calcula:
      - best_rssi_dbm: melhor RSSI entre torres candidatas
      - n_detecting: quantas torres >= threshold
      - best_tower_idx: índice da melhor torre (-1 se nenhuma candidata)
    """
    # Busca torres dentro do raio (haversine em radianos)
    pts_rad = np.deg2rad(np.c_[pts_lat, pts_lon])
    r_rad = max_range_km / 6371.0
    ind_list = tower.tree.query_radius(pts_rad, r=r_rad)

    best_rssi = np.full(len(pts_lat), -np.inf, dtype=float)
    n_detect = np.zeros(len(pts_lat), dtype=int)
    best_idx = np.full(len(pts_lat), -1, dtype=int)

    for i, inds in enumerate(ind_list):
        if len(inds) == 0:
            continue

        # distância horizontal
        d_hor_km = haversine_km_vec(tower.lat[inds], tower.lon[inds], float(pts_lat[i]), float(pts_lon[i]))
        # diferença vertical: drone alt vs torre
        dz_m = np.full(len(inds), float(pts_alt_m[i] - TOWER_HEIGHT_M))
        d3d_km = dist_3d_km(d_hor_km, dz_m)

        rssi = rssi_dbm_from_distance(
            d_km=d3d_km,
            f_mhz=REMOTEID_FREQ_MHZ,
            tx_eirp_dbm=DRONE_EIRP_DBM,
            rx_ant_gain_db=SNIFFER_ANT_GAIN_DB,
            rx_cable_loss_db=SNIFFER_CABLE_LOSS_DB,
            extra_losses_db=EXTRA_CLUTTER_LOSS_DB,
            model=MODEL,
            hb_m_for_cost231=TOWER_HEIGHT_M,
            hr_m_for_cost231=1.5,
            metropolitan=False,
        )

        best_rssi[i] = float(np.max(rssi))
        n_detect[i] = int(np.sum(rssi >= DETECTION_THRESHOLD_DBM))
        best_local = int(np.argmax(rssi))
        best_idx[i] = int(inds[best_local])

    # onde não houve candidatos, melhor RSSI fica -inf; trocamos por um valor bem baixo
    best_rssi = np.where(np.isfinite(best_rssi), best_rssi, WEIGHT_MIN_DBM - 30.0)
    return best_rssi, n_detect, best_idx

# -----------------------------
# GDOP (Geometric Dilution of Precision)
# -----------------------------

# Ajustes do heatmap de GDOP (normalização)
GDOP_MIN = 1.0       # bom (perto de 1)
GDOP_MAX = 30.0      # ruim (clip p/ não explodir no heatmap)
GDOP_LOG_SCALE = True

def enu_from_latlon_m(lat0_deg: float, lon0_deg: float, lat_deg: np.ndarray, lon_deg: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Aproximação local (ENU) boa para áreas pequenas (até ~dezenas de km).
    Retorna (east_m, north_m) do ponto (lat0,lon0) até (lat,lon).
    """
    R = 6378137.0  # WGS84 (m)
    lat0 = np.deg2rad(lat0_deg)
    dlat = np.deg2rad(lat_deg - lat0_deg)
    dlon = np.deg2rad(lon_deg - lon0_deg)
    north = dlat * R
    east = dlon * R * np.cos(lat0)
    return east, north

def gdop_from_unit_vectors(H: np.ndarray) -> float:
    """
    H: matriz Nx3 com vetores unitários (drone -> torres).
    GDOP = sqrt(trace((H^T H)^-1))
    """
    if H.shape[0] < 3:
        return np.nan
    try:
        M = H.T @ H
        # se quase singular (torres quase colineares), GDOP explode
        if np.linalg.cond(M) > 1e12:
            return np.inf
        Q = np.linalg.inv(M)
        return float(np.sqrt(np.trace(Q)))
    except np.linalg.LinAlgError:
        return np.inf

def normalize_gdop_weight(gdop: np.ndarray, gmin: float, gmax: float, log_scale: bool = True) -> np.ndarray:
    g = np.clip(gdop, gmin, gmax)
    if log_scale:
        a = np.log(g)
        lo = np.log(gmin)
        hi = np.log(gmax)
        w = (a - lo) / (hi - lo)
    else:
        w = (g - gmin) / (gmax - gmin)
    return np.clip(w, 0.0, 1.0)

# -----------------------------
# BUCKETS & MÉTRICAS
# -----------------------------

def load_flight_points(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype={"flight_id": str})
    # normaliza nomes
    df.columns = [c.strip() for c in df.columns]
    for needed in ["flight_id", "lon", "lat", "alt", "timestamp"]:
        if needed not in df.columns:
            raise ValueError(f"flight points CSV precisa da coluna '{needed}'")

    df["lon"] = to_float_series(df["lon"])
    df["lat"] = to_float_series(df["lat"])
    df["alt"] = to_float_series(df["alt"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    
    before = len(df)
    df = df.dropna(subset=["lon", "lat", "alt", "timestamp", "flight_id"]).copy()
    after = len(df)
    print(f"Dedup OK: {before} -> {after} pontos de voos (removidas {before-after} duplicatas)")
    
    if FILTER_FLIGHT_IDS is not None:
        df = df[df["flight_id"].isin(FILTER_FLIGHT_IDS)].copy()

    return df.sort_values(["flight_id", "timestamp"]).reset_index(drop=True)

def load_buckets(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    col_fid = pick_col(df, ["Flight ID", "flight_id", "FlightID", "flightId"])
    col_bs  = pick_col(df, ["Bucket Start", "bucket_start", "start", "BucketStart"])
    col_be  = pick_col(df, ["Bucket End", "bucket_end", "end", "BucketEnd"])

    if col_fid is None or col_bs is None or col_be is None:
        raise ValueError("Buckets CSV precisa ter colunas equivalentes a: Flight ID, Bucket Start, Bucket End")

    out = pd.DataFrame({
        "flight_id": df[col_fid].astype(str).str.strip(),
        "bucket_start": pd.to_datetime(df[col_bs], utc=True, errors="coerce"),
        "bucket_end": pd.to_datetime(df[col_be], utc=True, errors="coerce"),
    }).dropna(subset=["flight_id", "bucket_start", "bucket_end"])

    if FILTER_FLIGHT_IDS is not None:
        out = out[out["flight_id"].isin(FILTER_FLIGHT_IDS)].copy()

    return out.sort_values(["flight_id", "bucket_start"]).reset_index(drop=True)

def bucket_metrics_for_flight(
    flight_points: pd.DataFrame,
    buckets: pd.DataFrame,
    tower: TowerData,
) -> pd.DataFrame:
    rows = []
    # Agrupa pontos por voo para acelerar filtros
    grouped = {fid: g for fid, g in flight_points.groupby("flight_id", sort=False)}
    for _, b in buckets.iterrows():
        fid = b["flight_id"]
        if fid not in grouped:
            continue

        g = grouped[fid]
        mask = (g["timestamp"] >= b["bucket_start"]) & (g["timestamp"] < b["bucket_end"])
        gb = g.loc[mask].copy()
        if gb.empty:
            continue

        best_rssi, n_det, best_idx = detect_at_points(
            tower,
            gb["lat"].to_numpy(float),
            gb["lon"].to_numpy(float),
            gb["alt"].to_numpy(float),
            max_range_km=MAX_RANGE_KM,
        )
        gb["best_rssi_dbm"] = best_rssi
        gb["n_detecting"] = n_det
        gb["best_tower_idx"] = best_idx

        # métricas básicas
        n = len(gb)
        rssi_p50 = float(np.median(best_rssi))
        rssi_mean = float(np.mean(best_rssi))
        towers_mean = float(np.mean(n_det))
        tower_div = int(len(set(best_idx[best_idx >= 0])))

        # outages para k=1.. (aprox com deltas entre amostras)
        gb = gb.sort_values("timestamp")
        t = gb["timestamp"].astype("int64").to_numpy() / 1e9  # seconds
        dt = np.diff(t, prepend=t[0])

        outages: Dict[int, float] = {}
        cov: Dict[int, float] = {}
        for k in K_REDUNDANCY:
            ok = (gb["n_detecting"].to_numpy(int) >= k)
            cov[k] = float(np.mean(ok))
            # acumula "buracos" usando dt
            max_out = 0.0
            cur = 0.0
            for i in range(n):
                if not ok[i]:
                    cur += float(dt[i])
                    max_out = max(max_out, cur)
                else:
                    cur = 0.0
            outages[k] = max_out

        rows.append({
            "flight_id": fid,
            "bucket_start": b["bucket_start"].isoformat(),
            "bucket_end": b["bucket_end"].isoformat(),
            "n_points": n,
            "rssi_p50_dbm": rssi_p50,
            "rssi_mean_dbm": rssi_mean,
            "n_detecting_mean": towers_mean,
            "tower_diversity": tower_div,
            **{f"coverage_ge{k}": cov[k] for k in K_REDUNDANCY},
            **{f"max_outage_s_ge{k}": outages[k] for k in K_REDUNDANCY},
        })

    return pd.DataFrame(rows)


# -----------------------------
# HEATMAP DE COBERTURA
# -----------------------------

def heatmap_for_operator(
    tower: TowerData,
    operator_name: str,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    drone_alt_m: float,
    max_range_km: float,
) -> Tuple[List[List[float]], float, Tuple[float, float, float]]:
    """
    Retorna lista [lat, lon, weight] para HeatMap e taxa de cobertura no grid.
    """
    # filtra torres por operadora
    if operator_name == "__ALL__":
        inds_t = np.arange(len(tower.df))
    else:
        inds_t = np.where(tower.op == operator_name)[0]

    if len(inds_t) == 0:
        return [], 0.0

    # BallTree específico do subset 
    lat_t = tower.lat[inds_t]
    lon_t = tower.lon[inds_t]
    coords_rad = np.deg2rad(np.c_[lat_t, lon_t])
    tree = BallTree(coords_rad, metric="haversine")

    pts_rad = np.deg2rad(np.c_[lat_grid, lon_grid])
    r_rad = max_range_km / 6371.0
    ind_list = tree.query_radius(pts_rad, r=r_rad)

    best_rssi = np.full(len(lat_grid), -np.inf, dtype=float)
    n_detect = np.zeros(len(lat_grid), dtype=int)

    # processa ponto a ponto (com candidatos reduzidos)
    for i, inds in enumerate(ind_list):
        if len(inds) == 0:
            continue
        d_hor_km = haversine_km_vec(lat_t[inds], lon_t[inds], float(lat_grid[i]), float(lon_grid[i]))
        dz_m = np.full(len(inds), float(drone_alt_m - TOWER_HEIGHT_M))
        d3d_km = dist_3d_km(d_hor_km, dz_m)

        rssi = rssi_dbm_from_distance(
            d_km=d3d_km,
            f_mhz=REMOTEID_FREQ_MHZ,
            tx_eirp_dbm=DRONE_EIRP_DBM,
            rx_ant_gain_db=SNIFFER_ANT_GAIN_DB,
            rx_cable_loss_db=SNIFFER_CABLE_LOSS_DB,
            extra_losses_db=EXTRA_CLUTTER_LOSS_DB,
            model=MODEL,
            hb_m_for_cost231=TOWER_HEIGHT_M,
            hr_m_for_cost231=1.5,
            metropolitan=False,
        )
        n_detect[i] = int(np.sum(rssi >= DETECTION_THRESHOLD_DBM))
        best_rssi[i] = float(np.max(rssi))


    best_rssi = np.where(np.isfinite(best_rssi), best_rssi, WEIGHT_MIN_DBM - 30.0)

    cov_ge1 = float(np.mean(n_detect >= 1))
    cov_ge2 = float(np.mean(n_detect >= 2))
    cov_ge3 = float(np.mean(n_detect >= 3))

    #covered = (n_detect >= 1)  # mantém o heatmap padrão como ">=1"

    covered = best_rssi >= DETECTION_THRESHOLD_DBM
    cov_rate = float(np.mean(covered))

    # Heatmap: use apenas cobertos (visualmente mais claro)
    w = normalize_weight(best_rssi, WEIGHT_MIN_DBM, WEIGHT_MAX_DBM)
    pts = [[float(lat_grid[i]), float(lon_grid[i]), float(w[i])] for i in range(len(lat_grid)) if covered[i]]

    return pts, cov_rate, (cov_ge1, cov_ge2, cov_ge3)

def heatmap_gdop_for_operator(
    tower: TowerData,
    operator_name: str,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    drone_alt_m: float,
    max_range_km: float,
) -> Tuple[List[List[float]], float, float]:
    """
    Retorna lista [lat, lon, weight] para HeatMap de GDOP.
    Também retorna:
      - cov_ge3: fração do grid com >=3 torres detectáveis
      - gdop_p50: mediana do GDOP (somente onde calculável)
    """
    # filtra torres por operadora
    if operator_name == "__ALL__":
        inds_t = np.arange(len(tower.df))
    else:
        inds_t = np.where(tower.op == operator_name)[0]

    if len(inds_t) == 0:
        return [], 0.0, float("nan")

    lat_t = tower.lat[inds_t]
    lon_t = tower.lon[inds_t]
    coords_rad = np.deg2rad(np.c_[lat_t, lon_t])
    tree = BallTree(coords_rad, metric="haversine")

    pts_rad = np.deg2rad(np.c_[lat_grid, lon_grid])
    r_rad = max_range_km / 6371.0
    ind_list = tree.query_radius(pts_rad, r=r_rad)

    gdop = np.full(len(lat_grid), np.nan, dtype=float)
    ok3 = np.zeros(len(lat_grid), dtype=bool)

    for i, inds in enumerate(ind_list):
        if len(inds) < 3:
            continue

        # 1) Reusa seu critério de “visível/detectável”: RSSI >= threshold
        d_hor_km = haversine_km_vec(lat_t[inds], lon_t[inds], float(lat_grid[i]), float(lon_grid[i]))
        dz_m = np.full(len(inds), float(drone_alt_m - TOWER_HEIGHT_M))
        d3d_km = dist_3d_km(d_hor_km, dz_m)

        rssi = rssi_dbm_from_distance(
            d_km=d3d_km,
            f_mhz=REMOTEID_FREQ_MHZ,
            tx_eirp_dbm=DRONE_EIRP_DBM,
            rx_ant_gain_db=SNIFFER_ANT_GAIN_DB,
            rx_cable_loss_db=SNIFFER_CABLE_LOSS_DB,
            extra_losses_db=EXTRA_CLUTTER_LOSS_DB,
            model=MODEL,
            hb_m_for_cost231=TOWER_HEIGHT_M,
            hr_m_for_cost231=1.5,
            metropolitan=False,
        )

        vis = (rssi >= DETECTION_THRESHOLD_DBM)
        if np.sum(vis) < 3:
            continue

        ok3[i] = True
        inds_vis = inds[vis]

        # 2) Monta H com vetores unitários (ENU) do drone -> torres
        east_m, north_m = enu_from_latlon_m(float(lat_grid[i]), float(lon_grid[i]), lat_t[inds_vis], lon_t[inds_vis])

        # altitude relativa (assumindo alt do drone e altura típica da torre no mesmo referencial)
        up_m = (TOWER_HEIGHT_M - float(drone_alt_m))  # torre abaixo do drone => negativo (ok)
        up_vec = np.full_like(east_m, up_m)

        V = np.c_[east_m, north_m, up_vec]
        n = np.linalg.norm(V, axis=1, keepdims=True)
        n = np.maximum(n, 1e-9)
        H = V / n

        # 3) GDOP = sqrt(trace((H^T H)^-1))
        gdop[i] = gdop_from_unit_vectors(H)

    cov_ge3 = float(np.mean(ok3))
    gdop_valid = gdop[np.isfinite(gdop)]
    gdop_p50 = float(np.median(gdop_valid)) if len(gdop_valid) else float("nan")

    # Heatmap: só pontos com GDOP finito
    w = normalize_gdop_weight(gdop, GDOP_MIN, GDOP_MAX, log_scale=GDOP_LOG_SCALE)
    pts = [[float(lat_grid[i]), float(lon_grid[i]), float(w[i])]
           for i in range(len(lat_grid)) if np.isfinite(gdop[i])]

    return pts, cov_ge3, gdop_p50


# -----------------------------
# MAIN
# -----------------------------

def main():
    # 1) Torres
    tower = load_towers(TOWERS_CSV_PATH, TOWERS_SEP)
    print(f"Torres carregadas: {len(tower.df)}")
    print("Operadoras:", sorted(set(tower.op.tolist())))
    print("Tecnologias:", sorted(set(tower.tech.tolist())))

    # 2) Voos
    flight_points = None
    buckets = None
    if FLIGHT_POINTS_CSV is not None:
        try:
            flight_points = load_flight_points(FLIGHT_POINTS_CSV)
            print(f"Pontos de voo carregados: {len(flight_points)}")
        except FileNotFoundError:
            print("Aviso: FLIGHT_POINTS_CSV não encontrado; seguindo sem overlay/métricas.")
            flight_points = None

    if BUCKETS_CSV is not None and COMPUTE_BUCKET_METRICS and flight_points is not None:
        try:
            buckets = load_buckets(BUCKETS_CSV)
            print(f"Buckets carregados: {len(buckets)}")
        except FileNotFoundError:
            print("Aviso: BUCKETS_CSV não encontrado; seguindo sem métricas.")
            buckets = None


    # 2b) Anti-spoofing: Consistência Físico–Digital (RSSI x GPS do payload Remote ID)
    if flight_points is not None and COMPUTE_ANTISPOOF_METRICS:
        fp_payload = prepare_remoteid_payload_columns(flight_points)
        compute_physdig_consistency_metrics(fp_payload, tower, max_range_km=MAX_RANGE_KM)

        # 3) Área do mapa (torres + pontos de voo)
        lat_all = [tower.lat]
        lon_all = [tower.lon]
        #if flight_points is not None and len(flight_points) > 0:
        #    lat_all.append(flight_points["lat"].to_numpy(float))
        #    lon_all.append(flight_points["lon"].to_numpy(float))

        lat_all = np.concatenate(lat_all)
        lon_all = np.concatenate(lon_all)

        lat_min, lat_max = float(lat_all.min()), float(lat_all.max())
        lon_min, lon_max = float(lon_all.min()), float(lon_all.max())

        lat_mid = 0.5 * (lat_min + lat_max)
        lat_min -= margin_deg_lat(MAP_MARGIN_M)
        lat_max += margin_deg_lat(MAP_MARGIN_M)
        lon_min -= margin_deg_lon(MAP_MARGIN_M, lat_mid)
        lon_max += margin_deg_lon(MAP_MARGIN_M, lat_mid)

        # 4) Grid
        lat_grid, lon_grid = make_grid(lat_min, lat_max, lon_min, lon_max, GRID_STEP_M)
        print(f"Grid: {len(lat_grid)} pontos (step={GRID_STEP_M} m)")

        # 5) Mapa base
        center = [float(lat_mid), float(0.5 * (lon_min + lon_max))]
        m = folium.Map(location=center, zoom_start=15, tiles="OpenStreetMap")

        # 6) Camada de torres
        fg_towers = folium.FeatureGroup(name="Torres RID", show=True)
        for _, r in tower.df.iterrows():
            folium.CircleMarker(
                location=[float(r["lat"]), float(r["lon"])],
                radius=3,
                popup=f"{r['operadora']} | tower_id={r['tower_id']} | tech={r['tech']}",
                fill=True,
            ).add_to(fg_towers)
        fg_towers.add_to(m)

        # 7) Heatmap por operadora + ALL
        ops = sorted(set(tower.op.tolist()))
        ops_layers = ["__ALL__"] + ops

        alt_drone = float(flight_points["alt"].mean()) if flight_points is not None else float(HEATMAP_DRONE_ALT_M)

        for op_name in ops_layers:
            pts, cov_rate, (cov1, cov2, cov3) = heatmap_for_operator(
                tower=tower,
                operator_name=op_name,
                lat_grid=lat_grid,
                lon_grid=lon_grid,
                drone_alt_m=HEATMAP_DRONE_ALT_M, #alt_drone,
                max_range_km=MAX_RANGE_KM,
            )
            label = "Heatmap (ALL operadoras)" if op_name == "__ALL__" else f"Heatmap ({op_name})"
            fg = folium.FeatureGroup(name=f"{label} | cov={cov_rate*100:.1f}% | cov>=1:{cov1*100:.1f}% cov>=2:{cov2*100:.1f}% cov>=3:{cov3*100:.1f}%",
                show=(op_name=="__ALL__")
            )

            if len(pts) > 0:
                HeatMap(
                    pts,
                    radius=18,
                    blur=20,
                    min_opacity=0.2,
                    max_zoom=1,
                ).add_to(fg)
            fg.add_to(m)

            # --- Heatmap de GDOP (Incerteza geométrica) ---
            pts_gdop, cov3_gdop, p50_gdop = heatmap_gdop_for_operator(
                tower=tower,
                operator_name="__ALL__",     # recomendo ALL para “capacidade geométrica” máxima
                lat_grid=lat_grid,
                lon_grid=lon_grid,
                drone_alt_m=HEATMAP_DRONE_ALT_M,
                max_range_km=MAX_RANGE_KM,
            )

            fg_gdop = folium.FeatureGroup(
                name=f"GDOP (ALL) | cov>=3:{cov3_gdop*100:.1f}% | p50:{p50_gdop:.2f}",
                show=False
            )
            if len(pts_gdop) > 0:
                HeatMap(
                    pts_gdop,
                    radius=18,
                    blur=20,
                    min_opacity=0.2,
                    max_zoom=1,
                ).add_to(fg_gdop)
            fg_gdop.add_to(m)


        # 8) Overlay de pontos de voo
        if flight_points is not None and DRAW_FLIGHT_POINTS and len(flight_points) > 0:
            fp = flight_points.copy()
            if MAX_POINTS_TO_DRAW > 0 and len(fp) > MAX_POINTS_TO_DRAW:
                fp = fp.sample(MAX_POINTS_TO_DRAW, random_state=7).sort_values("timestamp")

            best_rssi, n_det, _ = detect_at_points(
                tower,
                fp["lat"].to_numpy(float),
                fp["lon"].to_numpy(float),
                fp["alt"].to_numpy(float),
                max_range_km=MAX_RANGE_KM,
            )
            fp["best_rssi_dbm"] = best_rssi
            fp["n_detecting"] = n_det

            fg_fp = folium.FeatureGroup(name=f"Pontos de voo (amostra={len(fp)})", show=False)
            for _, r in fp.iterrows():
                # cor por redundância simples
                if r["n_detecting"] >= 2:
                    color = "green"
                elif r["n_detecting"] >= 1:
                    color = "orange"
                else:
                    color = "red"

                folium.CircleMarker(
                    location=[float(r["lat"]), float(r["lon"])],
                    radius=2,
                    color=color,
                    fill=True,
                    fill_opacity=0.8,
                    popup=f"flight={r['flight_id']} | t={r['timestamp']} | alt={r['alt']:.1f} | "
                        f"n={int(r['n_detecting'])} | best_rssi={r['best_rssi_dbm']:.1f} dBm",
                ).add_to(fg_fp)
            fg_fp.add_to(m)

        # 9) Métricas por bucket 
        if buckets is not None and flight_points is not None and COMPUTE_BUCKET_METRICS:
            metrics = bucket_metrics_for_flight(flight_points, buckets, tower)
            out_csv = "bucket_metrics_remoteid.csv"
            metrics.to_csv(out_csv, index=False)
            print(f"Métricas por bucket salvas em: {out_csv} (linhas={len(metrics)})")

        folium.LayerControl(collapsed=False).add_to(m)

        out_html = "remoteid_heatmap_cobertura.html"
        m.save(out_html)
        print(f"OK! Mapa salvo em: {out_html}")
        print("Dicas de calibração:")
        print(" - Ajuste DRONE_EIRP_DBM e DETECTION_THRESHOLD_DBM conforme o seu Remote ID/sniffer")
        print(" - EXTRA_CLUTTER_LOSS_DB é o 'botão' principal para representar urbano/NLoS")
        print(" - MAX_RANGE_KM limita cálculo (performance) e implicitamente o alcance máximo")

if __name__ == "__main__":
    main()