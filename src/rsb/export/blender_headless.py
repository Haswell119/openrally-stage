"""T10 — Exporteur Blender (adaptateur) : documente le maillon manuel bundle → KN5.

Cet adaptateur **ne dépend pas** de l'IR au-delà des fichiers de la bundle : il
prépare le passage vers Blender + ``leBluem/io_import_accsv`` puis KN5.

⚠️ **Le dernier maillon est MANUEL** (Blender + SDK ksEditor). Ce module :

* génère un **script Blender** (``bpy``) qui importe ``centerline_ac.csv`` (dont
  l'ordre de colonnes AC — X, Z, Y — correspond déjà à l'importeur
  ``io_import_accsv``) et le mesh ``terrain.obj``, puis pose le **nommage AC**
  (surface roulable ``1ROAD``, portes point-à-point ``AC_AB_START_L/R`` /
  ``AC_AB_FINISH_L/R``, spawn ``AC_PIT_0``) ;
* documente la génération KN5 / AI line / pacenotes (voir ``STAGE_GUIDE.md``).

L'export KN5 lui-même n'est pas automatisé ici (nécessite Blender + l'addon +
ksEditor installés) : ``to_kn5`` lève ``NotImplementedError`` avec les pointeurs.

Références (vérifiées) : github.com/leBluem/io_import_accsv,
assettocorsamods.net (build your first track), acrallycentral.com (CSP Copilot).
"""

from __future__ import annotations

from pathlib import Path

_BLENDER_SCRIPT_TEMPLATE = '''\
"""Script Blender généré par rally-stage-builder pour la spéciale « {name} ».

Usage :
    blender --background --python this_script.py
    # (ou coller dans l'éditeur de scripts Blender, addon io_import_accsv installé)

Prérequis : addon leBluem/io_import_accsv installé (télécharger l'asset de RELEASE
« io_import_accsv.zip », PAS le « Source code (zip) »).

NB : centerline_ac.csv respecte déjà la convention AC de l'importeur (colonnes
X, Z, Y → sommet Blender (E_local, N_local, Z_local)). Vérifiez le nom exact de
l'opérateur d'import selon la version de l'addon (menu : File > Import >
« AC side_x.CSV (.csv) »).
"""
import bpy

BUNDLE = r"{bundle_dir}"
CSV = BUNDLE + r"/centerline_ac.csv"
TERRAIN = BUNDLE + r"/terrain.obj"

# --- 1. importer le tracé (centerline) via io_import_accsv --------------------
try:
    bpy.ops.import_csv.read(filepath=CSV)          # opérateur de l'addon
except Exception as exc:                            # noqa: BLE001
    raise RuntimeError(
        "Import CSV échoué : vérifiez que l'addon io_import_accsv est activé et "
        "le nom d'opérateur (import_csv.read). Détail : %s" % exc
    )

# --- 2. importer le mesh de terrain (corridor MNT) ---------------------------
bpy.ops.wm.obj_import(filepath=TERRAIN)

# --- 3. NOMMAGE Assetto Corsa (à finaliser à la main dans Blender) -----------
# Surface roulable : renommer l'objet route en « 1ROAD » (préfixe chiffre >0 =
# physique/collisionnable). Types de surface AC par défaut : ROAD/GRASS/KERB/SAND
# (+ WALL). Ex. terrain → « 1GRASS ». NE PAS combiner 2 clés dans un même nom.
#
# Spéciale POINT-À-POINT (A→B) : placer des empties nommés
#   AC_AB_START_L / AC_AB_START_R   (porte de départ)
#   AC_AB_FINISH_L / AC_AB_FINISH_R (arrivée)
#   AC_PIT_0                         (spawn, mode Practice)
# aux extrémités du tracé (voir bundle.json → local_origin pour recaler en LV95).
print("Import terminé. Renommez les objets selon les conventions AC (voir STAGE_GUIDE.md).")
'''


def blender_import_script(bundle_dir: str | Path, name: str = "stage") -> str:
    """Retourne un script Blender (``bpy``) import, prêt à adapter, pour la bundle."""
    return _BLENDER_SCRIPT_TEMPLATE.format(bundle_dir=str(Path(bundle_dir)), name=name)


def write_blender_script(bundle_dir: str | Path, name: str = "stage") -> Path:
    """Écrit ``blender_import.py`` dans le dossier de la bundle. Retourne le chemin."""
    d = Path(bundle_dir)
    out = d / "blender_import.py"
    out.write_text(blender_import_script(d, name), encoding="utf-8")
    return out


def to_kn5(*_args: object, **_kwargs: object) -> None:
    """Export KN5 : MANUEL (Blender + ksEditor). Non automatisé — voir STAGE_GUIDE.md.

    Chaîne recommandée : Blender → FBX → ksEditor (SDK AC, réimport à l'échelle
    0.01, matériaux/shaders, File > Save Persistence → ``<track>.fbx.ini``) →
    export ``<track>.kn5``. Alternative : export direct Blender→KN5 (expérimental).
    """
    raise NotImplementedError(
        "Export KN5 non automatisé (maillon manuel Blender + ksEditor). "
        "Voir STAGE_GUIDE.md ; utilisez write_blender_script() pour préparer l'import."
    )
