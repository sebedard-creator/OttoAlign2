# Architecture OttoAlign2

Ce document donne seulement le survol global. Les détails binaires PTX appartiennent à la documentation de `pt_api`.

## Composants

- `server.py` : interface Flask, réception des deux ZIP, extraction sécurisée, sélection non ambiguë de la session et de son dossier frère `Audio Files`, lancement des sous-processus, création du ZIP final et nettoyage.
- `align_engine.py` : lecture des timelines AAF/PTX, calcul des chevauchements, lecture des portions WAV, orchestration DSP et écriture de la copie de session.
- `dsp_core.py` : GCC-PHAT, lissage temporel et interpolation cubique de la courbe de délai.
- `orchestrator.py` : finalisation du chemin AAF historique.
- `pt_api` : lecture, mutation, relink physique et sauvegarde des sessions PTX.
- `static/` : interface web et interrogation périodique de l’état du job.
- `temp/` : espace de travail local ignoré par Git; le ZIP final et le journal y restent jusqu’au téléchargement ou au vidage du cache.

## Flux d’exécution

1. Le client envoie une archive de référence et une archive cible.
2. `server.py` les extrait sous un identifiant de job et recherche exactement une session complète dans chacune.
3. Le serveur lance `align_engine.py` avec le même interpréteur Python que Flask.
4. Le moteur associe chaque clip cible à la référence offrant le plus grand chevauchement et ignore les chevauchements de moins de 0,5 seconde.
5. `dsp_core.py` estime une courbe de délai sur le premier canal; cette courbe est appliquée à tous les canaux cibles.
6. En PTX, le moteur clone le média complet, remplace seulement la portion PCM traitée, crée une identité média indépendante avec `pt_api.relink_clip()` et sauvegarde le PTX modifié. En AAF, il écrit un média `_ottoaligned` et modifie la copie AAF ouverte en lecture-écriture.
7. Pour l’AAF, `orchestrator.py` finalise la reconstruction. Pour le PTX, le fichier produit par le moteur est déjà la sortie définitive.
8. Le serveur crée `OttoAligned_Result.zip`, y place la session, ses médias requis et le rapport, puis efface les archives et dossiers extraits.

## Frontières de responsabilité

- Le serveur valide la forme des archives et l’emplacement physique des bundles; il ne comprend pas le format interne PTX.
- Le moteur décide quels clips traiter et protège la transaction globale : une erreur fatale supprime la session de sortie et les médias qu’il vient de créer.
- `pt_api` garantit la cohérence binaire de chaque relink PTX, mais ne réalise aucun DSP.
- Le navigateur ne détient pas l’état autoritaire; l’état courant des jobs réside dans la mémoire du processus Flask.

## Dépendances principales

- Python 3.11 (environnement validé)
- Flask / Werkzeug
- NumPy / SciPy
- SoundFile
- pyaaf2
- `pt_api` installé depuis le dépôt public
