# Architecture OttoAlign2

## Stack Technique
- **Backend:** Python 3.11
- **Web Server:** Flask (serveur web asynchrone intégré)
- **DSP Core:** NumPy, SciPy (GCC-PHAT algorithm, CubicSpline interpolation)
- **Audio I/O:** Soundfile (24-bit bit-perfect read/write)
- **AAF Parsing:** pyaaf2
- **Frontend:** Vanilla HTML/CSS/JS

## Structure du Projet
- `server.py` : Point d'entrée. Exécute le serveur web Flask, gère les requêtes API (upload/download), lance les tâches d'alignement en arrière-plan (background thread) et exécute le nettoyage des dossiers temporaires.
- `align_engine.py` : Moteur d'extraction et de remplacement. Parcourt l'AAF de référence et l'AAF cible, identifie TOUS les clips sur TOUTES les pistes cibles (Track 1, Track 2, etc.) qui chevauchent la référence temporelle, et appelle `dsp_core.py`.
- `dsp_core.py` : Moteur de calcul pur. Applique le GCC-PHAT et l'interpolation sub-sample pour déterminer et appliquer la correction de phase.
- `orchestrator.py` : Script de reconstruction AAF pour s'assurer que les clips cibles pointent vers les nouveaux fichiers audio `_ottoaligned.wav`.
- `static/` : Interface Web.
  - `index.html` : UI (avec bouton de nettoyage de cache et Easter Egg).
  - `style.css` : Design sombre.
  - `app.js` : Logique client (polling du statut, requêtes API).
- `temp/` : Dossier local ignoré par Git où sont décompressés les ZIP et générés les fichiers intermédiaires. Le serveur supprime automatiquement les sous-dossiers et fichiers lourds de cette directory dès qu'un alignement est terminé, ne conservant que le fichier ZIP final et les logs.

## Pipeline d'exécution
1. L'utilisateur upload 2 archives ZIP (Target & Reference) via l'interface web.
2. `server.py` crée une job dans `temp/ottoalign_{job_id}` et lance un thread.
3. Les archives sont décompressées.
4. `server.py` lance `align_engine.py` en sous-processus.
5. `align_engine.py` lit l'AAF cible, détecte toutes ses pistes, récupère l'audio de référence correspondant et aligne l'audio cible bit pour bit.
6. `orchestrator.py` génère le AAF final pointant vers les fichiers audio alignés.
7. `server.py` zippe le tout dans `OttoAligned_Result.zip`.
8. `server.py` supprime les fichiers extraits lourds (cleanup).
9. L'utilisateur télécharge l'archive finale.
