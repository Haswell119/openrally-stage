PISTE ASSETTO CORSA — evionnaz-test-stage
Généré par rally-stage-builder (usage simulation personnel).

Ce dossier suit la structure AC : copiez-le dans
    <Assetto Corsa>/content/tracks/

IL MANQUE UNE SEULE CHOSE : le modèle 3D compilé evionnaz-test-stage.kn5.
Générez-le UNE fois (outil Kunos, pas de Blender) :
  1. Ouvrez ksEditor (SDK Assetto Corsa).
  2. Import FBX -> evionnaz-test-stage.fbx (dans ce dossier).
     - Si la piste est 100x trop grande, réimportez à l'échelle 0.01.
  3. Assignez les matériaux/textures aux objets 1ROAD / 1KERB / 1WALL / 1GRASS
     (tarmac / bordure / rail / herbe).
  4. File > Save (persistence) puis EXPORT -> evionnaz-test-stage.kn5 DANS CE DOSSIER.

Ensuite, en jeu (voir STAGE_GUIDE.md) :
  - AI line : app AI -> conduire -> fast_lane.ai (dans data/ai/).
  - Pacenotes : CSP Copilot (auto depuis l'AI line).

Attribution obligatoire : (c) OpenStreetMap contributors (ODbL) ;
Source : swisstopo (swissALTI3D). Ne redistribuez pas la trace rally-maps.
