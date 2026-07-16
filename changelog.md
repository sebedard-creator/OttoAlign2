# Changelog

## 2026-07-16

- Compatibilité avec `pt_api` 1.3.8 : catalogues PTX dont les noms WAV se terminent par quatre octets nuls et identités média `0x1001` contenant une séquence interprétable comme un faux bloc vide.
- Validation complète sur une nouvelle cible : 236 placements, 226 alignés, 10 ignorés selon les règles existantes, 226 WAV indépendants en ligne et aucun média de timeline manquant. Le catalogue PTX est passé de 71 à 297 entrées et la sauvegarde no-op demeure byte-for-byte identique.

## 2026-07-15

- Lecture des timelines PTX longues et de leurs offsets source 16/24/32 bits via la nouvelle version de `pt_api`; disparition de la coupure historique vers `10:07:41`.
- Lecture des clips PTX avec `get_timeline_clips(include_fades=False)` afin de ne pas dépendre des géométries de fade pour le matching audio.
- Remplacement du renommage PTX intrusif par un flux non destructif : clone WAV indépendant, PCM rendu compatible, nouvelle identité média et relink d’un seul placement.
- Prise en charge des placements parent/racine et virtuels de production, y compris les noms dupliqués sur la timeline.
- Lecture paresseuse de la seule portion qui chevauche la référence; application de la même courbe de délai à tous les canaux.
- Validation des fréquences, des bornes média, du chevauchement minimal de 0,5 seconde et de `max_shift_ms`; la valeur configurée est maintenant transmise au DSP.
- Cible AAF ouverte en lecture-écriture; nommage `_ottoaligned` robuste aux extensions WAV en majuscules.
- Nettoyage transactionnel de la session et des médias créés lorsqu’une erreur fatale survient; suppression d’une branche de compatibilité PTX devenue morte.
- Serveur renforcé : extraction ZIP protégée contre le path traversal, sélection exacte du bundle session/`Audio Files`, sous-processus lancé avec `sys.executable`, et archivage du vrai PTX modifié.
- `requirements.txt` déclare explicitement `pt_api` depuis le dépôt public `master`.
- Ajout d’une suite de tests unitaires pour le nommage, l’ouverture AAF et le cœur DSP.
- Validation complète sur une référence d’environ 42 minutes : 404 placements cibles, 388 alignés, 16 ignorés car trop courts, 388 médias indépendants en ligne. La session finale s’est ouverte et a joué correctement dans Pro Tools.

## 2026-07-14

- Ajout initial du parsing PTX via `pt_api`.
- Les clips de référence mutés ne sont plus exclus du matching.
- Ajout du rapport `OttoAlign_Report.txt`.

## 2026-07-08

- Transition vers Flask et ajout du bouton de vidage du cache.
- Traitement multipiste, SoundFile pour le PCM 24 bits et nettoyage automatique des dossiers temporaires.

## Précédemment

- GCC-PHAT, interpolation CubicSpline et parseur AAF.
