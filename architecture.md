# Architecture OttoAlign2

Ce document donne seulement le survol global. Les dÃ©tails binaires PTX appartiennent Ã  la documentation de `pt_api`.

## Composants

- `server.py` : interface Flask, rÃ©ception des deux ZIP, extraction sÃ©curisÃ©e, sÃ©lection non ambiguÃ« de la session et de son dossier frÃ¨re `Audio Files`, lancement des sous-processus, crÃ©ation du ZIP final et nettoyage.
- `align_engine.py` : lecture des timelines AAF/PTX, calcul des chevauchements, lecture des portions WAV, orchestration DSP et Ã©criture de la copie de session.
- `dsp_core.py` : GCC-PHAT, lissage temporel et interpolation cubique de la courbe de dÃ©lai.
- `orchestrator.py` : finalisation du chemin AAF historique.
- `pt_api` : lecture, mutation, relink physique et sauvegarde des sessions PTX.
- `static/` : interface web et interrogation pÃ©riodique de lâ€™Ã©tat du job.
- `temp/` : espace de travail local ignorÃ© par Git; le ZIP final et le journal y restent jusquâ€™au tÃ©lÃ©chargement ou au vidage du cache.

## Flux dâ€™exÃ©cution

1. Le client envoie une archive de rÃ©fÃ©rence et une archive cible.
2. `server.py` les extrait sous un identifiant de job et recherche exactement une session complÃ¨te dans chacune.
3. Le serveur lance `align_engine.py` avec le mÃªme interprÃ©teur Python que Flask.
4. Le moteur associe chaque clip cible à la référence offrant le plus grand chevauchement et ignore les chevauchements de moins de 0,05 seconde. Lorsque la session de référence et la session cible sont le même fichier PTX, les clips de la piste de référence (`Audio 1`) sont automatiquement filtrés pour garantir que la source ne soit jamais retouchée ni réalignée.
5. Les clips provenant d'un même fichier source (`physical_filename`) sont regroupés et se voient assigner une ancre globale (`best_anchor`) calculée via le meilleur SNR du groupe.
6. Pour chaque groupe, le moteur mesure le meilleur SNR et son ancre sur une corrélation sans interpolation FFT superflue (`interp=1`), car la correction rendue est entière. Il applique ensuite cette ancre commune aux fragments du groupe : cela préserve la cohérence de phase aux jointures et borne fortement le coût DSP. La fonction DSP générique conserve son mode dynamique interpolé lorsqu'elle est appelée sans ancre.
7. En PTX, le moteur clone le média complet, remplace seulement la portion PCM traitée, crée une identité média indépendante avec `pt_api.relink_clip()` et sauvegarde le PTX modifié. En AAF, il écrit un média `_ottoaligned` et modifie la copie AAF ouverte en lecture-écriture.
8. Pour l'AAF, `orchestrator.py` finalise la reconstruction. Pour le PTX, le fichier produit par le moteur est déjà la sortie définitive.
9. Le serveur crée `OttoAligned_Result.zip`, y place la session, ses médias requis et le rapport, puis efface les archives et dossiers extraits.

## FrontiÃ¨res de responsabilitÃ©

- Le serveur valide la forme des archives et lâ€™emplacement physique des bundles; il ne comprend pas le format interne PTX.
- Le moteur dÃ©cide quels clips traiter et protÃ¨ge la transaction globale : une erreur fatale supprime la session de sortie et les mÃ©dias quâ€™il vient de crÃ©er.
- `pt_api` garantit la cohÃ©rence binaire de chaque relink PTX, mais ne rÃ©alise aucun DSP.
- Le navigateur ne dÃ©tient pas lâ€™Ã©tat autoritaire; lâ€™Ã©tat courant des jobs rÃ©side dans la mÃ©moire du processus Flask.

## DÃ©pendances principales

- Python 3.11 (environnement validÃ©)
- Flask / Werkzeug
- NumPy / SciPy
- SoundFile
- pyaaf2
- `pt_api` installÃ© depuis le dÃ©pÃ´t public
## Compatibilité PTX

`align_engine.py` appelle directement `pt_api` 1.3.9 et aucun monkey patch ne modifie `ProToolsSession`. Avant chaque relink, son préflight lecture seule identifie les médias virtuels Premiere à header variable et les laisse intacts, avec un rapport détaillé. Le relink écrit de ces clips reste bloqué : Pro Tools a refusé les corpus `target4` avec `End of stream encountered`, y compris après comparaison avec un catalogue hybride importé nativement. OttoAlign peut donc traiter une session mixte, mais ne doit pas être présenté comme supportant le relink PTX Premiere.
