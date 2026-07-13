"""Chargement de traces GPX (points de piste) comme source de centerline.

Un GPX exporté depuis un roadbook / rally-maps (par l'utilisateur, jamais scrapé)
fournit le tracé RÉEL dense de la spéciale. On l'utilise **directement** comme
centerline (projection + rééchantillonnage + drape MNT), sans routage OSM.

⚠️ Un GPX rally-maps est du contenu tiers : à garder local (gitignoré), ne pas
redistribuer. Le ``stage.toml`` le référence par chemin.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.floating[Any]]


def _localname(tag: str) -> str:
    """Nom d'élément sans namespace ('{...}trkpt' → 'trkpt')."""
    return tag.rsplit("}", 1)[-1]


def load_gpx_track(path: str | Path) -> tuple[FloatArray, FloatArray | None]:
    """Lit les ``trkpt`` d'un GPX. Retourne ``(lonlat (N, 2), ele (N,) | None)``.

    Les points de tous les ``trkseg`` sont concaténés dans l'ordre du fichier.
    L'altitude ``<ele>`` est retournée si présente, sinon None (on drape sur le MNT).
    """
    root = ET.parse(path).getroot()
    lons: list[float] = []
    lats: list[float] = []
    eles: list[float] = []
    for el in root.iter():
        if _localname(el.tag) != "trkpt":
            continue
        try:
            lats.append(float(el.attrib["lat"]))
            lons.append(float(el.attrib["lon"]))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"trkpt GPX invalide : {el.attrib}") from exc
        ele_val = np.nan
        for child in el:
            if _localname(child.tag) == "ele" and child.text:
                ele_val = float(child.text)
        eles.append(ele_val)

    if len(lats) < 2:
        raise ValueError(f"GPX {path} : au moins 2 trkpt requis (trouvé {len(lats)})")

    lonlat = np.column_stack([np.asarray(lons), np.asarray(lats)])
    ele_arr = np.asarray(eles, dtype=np.float64)
    ele = None if np.all(np.isnan(ele_arr)) else ele_arr
    return lonlat, ele
