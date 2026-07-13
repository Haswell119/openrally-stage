# Attribution des données

`rally-stage-builder` produit des spéciales à partir de **données ouvertes**.
L'utilisation de ces données impose des obligations d'attribution que **tout
contenu généré** (previews, bundles, pistes exportées, captures) doit respecter.

## OpenStreetMap — réseau routier (ODbL)

Le tracé (centerline) est routé le long du réseau routier réel fourni par
**OpenStreetMap** via [osmnx](https://github.com/gboeing/osmnx).

- Données © **OpenStreetMap contributors**.
- Licence : **Open Database License (ODbL) 1.0** — <https://opendatacommons.org/licenses/odbl/>.
- **L'attribution est OBLIGATOIRE.** Toute production dérivée doit afficher
  « © OpenStreetMap contributors ».
- Si vous redistribuez une base de données dérivée, les clauses *share-alike*
  de l'ODbL s'appliquent.

Référence : <https://www.openstreetmap.org/copyright>

## swisstopo — modèle numérique de terrain swissALTI3D

L'altitude (Z), le dévers (camber) et le mesh de terrain proviennent du MNT
**swissALTI3D** de l'Office fédéral de topographie **swisstopo**.

- Collection STAC : `ch.swisstopo.swissalti3d`, GeoTIFF 0,5 m, CRS EPSG:2056 (LV95).
- Licence : **Open Government Data** de swisstopo — utilisation libre, la
  **mention de la source est appréciée** et recommandée :
  « Source : Office fédéral de topographie swisstopo ».
- Détails : <https://www.swisstopo.admin.ch/fr/geodata/height/alti3d.html> et
  les conditions OGD <https://www.geo.admin.ch/fr/conditions-generales-d-utilisation-des-geodonnees-des-autorites-federales.html>.

## rally-maps.com / roadbooks — référence HUMAINE uniquement

`rally-maps.com`, les roadbooks et cartes de rallye servent **uniquement de
référence humaine** pour choisir les routes à emprunter.

- **Aucun scraping / accès automatisé** de ces sources n'est effectué ni permis.
- **Ne redistribuez aucun contenu** issu de rally-maps.com ou de roadbooks.

## SWISSIMAGE (orthophoto) — futur, optionnel

Si la classification de surface par orthophoto est activée plus tard, l'ortho
**SWISSIMAGE** de swisstopo suit les mêmes conditions OGD (mention de la source
appréciée).
