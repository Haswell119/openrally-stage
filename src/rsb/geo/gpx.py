"""Chargement de traces GPX (points de piste) comme source de centerline.

Un GPX exporté depuis un roadbook / rally-maps (par l'utilisateur, jamais scrapé)
fournit le tracé RÉEL dense d'une ou plusieurs spéciales. On l'utilise
**directement** comme centerline (projection + rééchantillonnage + drape MNT),
sans routage OSM. Un GPX peut contenir **plusieurs tracks** (une par spéciale) :
on sélectionne alors la bonne via ``gpx_track`` (nom ou index).

⚠️ Un GPX rally-maps est du contenu tiers : à garder local (gitignoré), ne pas
redistribuer. Le ``stage.toml`` le référence par chemin.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.floating[Any]]


@dataclass(frozen=True)
class GpxTrack:
    """Une track GPX : nom + points (lon, lat) + altitudes éventuelles."""

    name: str | None
    lonlat: FloatArray  # (N, 2)
    ele: FloatArray | None  # (N,) ou None


def _localname(tag: str) -> str:
    """Nom d'élément sans namespace ('{...}trkpt' → 'trkpt')."""
    return tag.rsplit("}", 1)[-1]


def parse_tracks(path: str | Path) -> list[GpxTrack]:
    """Lit toutes les tracks d'un GPX (trkpt concaténés par ``<trk>``)."""
    root = ET.parse(path).getroot()
    tracks: list[GpxTrack] = []
    for trk in root.iter():
        if _localname(trk.tag) != "trk":
            continue
        name: str | None = None
        lons: list[float] = []
        lats: list[float] = []
        eles: list[float] = []
        for el in trk.iter():
            tag = _localname(el.tag)
            if tag == "name" and name is None:
                name = (el.text or "").strip() or None
            elif tag == "trkpt":
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
        if lats:
            ele_arr = np.asarray(eles, dtype=np.float64)
            ele = None if np.all(np.isnan(ele_arr)) else ele_arr
            tracks.append(GpxTrack(name, np.column_stack([lons, lats]), ele))
    return tracks


def list_gpx_tracks(path: str | Path) -> list[str]:
    """Noms des tracks d'un GPX (pour messages d'erreur / CLI)."""
    return [t.name or f"#{i}" for i, t in enumerate(parse_tracks(path))]


def _select_track(tracks: list[GpxTrack], track: str | int | None) -> GpxTrack:
    if not tracks:
        raise ValueError("GPX sans track")
    if track is None:
        if len(tracks) == 1:
            return tracks[0]
        names = [t.name or f"#{i}" for i, t in enumerate(tracks)]
        raise ValueError(f"GPX multi-tracks : préciser gpx_track parmi {names}")
    if isinstance(track, int) or (isinstance(track, str) and track.lstrip("-").isdigit()):
        return tracks[int(track)]
    matches = [t for t in tracks if track.lower() in (t.name or "").lower()]
    if not matches:
        names = [t.name or f"#{i}" for i, t in enumerate(tracks)]
        raise ValueError(f"aucune track GPX ne correspond à {track!r} (dispo : {names})")
    # homonymes (ex. un fragment court) → on garde la plus longue
    return max(matches, key=lambda t: len(t.lonlat))


def load_gpx_track(
    path: str | Path, track: str | int | None = None
) -> tuple[FloatArray, FloatArray | None]:
    """Retourne ``(lonlat (N, 2), ele (N,) | None)`` de la track sélectionnée.

    ``track`` : nom (sous-chaîne, insensible à la casse ; la plus longue en cas
    d'homonymes) ou index. ``None`` n'est valide que si le GPX a une seule track.
    """
    selected = _select_track(parse_tracks(path), track)
    if len(selected.lonlat) < 2:
        raise ValueError(f"track GPX {selected.name!r} : au moins 2 points requis")
    return selected.lonlat, selected.ele
