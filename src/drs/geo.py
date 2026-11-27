"""Geodesy helpers (metres)."""
import numpy as np

R_EARTH_M = 6_371_000.0


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH_M * np.arcsin(np.sqrt(a))


def local_xy_m(lat, lon, lat0: float, lon0: float):
    """Equirectangular projection to metres around (lat0, lon0). Error < 0.1% over a few km."""
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    x = np.radians(lon - lon0) * R_EARTH_M * np.cos(np.radians(lat0))
    y = np.radians(lat - lat0) * R_EARTH_M
    return x, y
