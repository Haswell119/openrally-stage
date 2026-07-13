"""T10 — Exporteur Race Track Builder (RTB) : stub (adaptateur alternatif).

Race Track Builder est un éditeur tiers capable de générer des pistes Assetto
Corsa. Cet adaptateur reste un **stub** : la chaîne recommandée passe par Blender
+ ``io_import_accsv`` (voir ``blender_headless`` et ``STAGE_GUIDE.md``).

Piste d'implémentation future : RTB importe des splines/heightmaps ; on pourrait
exporter la centerline (avec largeur/dévers) et le mesh terrain vers les formats
d'entrée RTB. La *stage bundle* étant agnostique de l'éditeur, seul cet
adaptateur serait à écrire — le reste du pipeline ne change pas.
"""

from __future__ import annotations

from pathlib import Path


def export_rtb(bundle_dir: str | Path, out_dir: str | Path) -> None:
    """Stub : export Race Track Builder non implémenté.

    Utilisez la chaîne Blender (``export.blender_headless``) documentée dans
    ``STAGE_GUIDE.md``.
    """
    raise NotImplementedError(
        "Export RTB non implémenté (stub). La stage bundle étant agnostique de "
        "l'éditeur, seul cet adaptateur reste à écrire. Voir STAGE_GUIDE.md."
    )
