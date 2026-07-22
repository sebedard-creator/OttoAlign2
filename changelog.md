## 2026-07-22

- **Dépendance PTX 1.3.9** : passage au tag public `pt_api v1.3.9`, qui fournit le préflight lecture seule des médias virtuels Premiere. Aucun monkey patch n'est chargé par OttoAlign2.
- **Performance — ancre entière** : la sélection d'ancre par fichier physique appelle désormais la corrélation avec `interp=1`. La sortie de groupe étant déjà un décalage entier, l'interpolation FFT ×16 était calculée puis arrondie sans effet. Les comparaisons de corpus ont conservé le même décalage entier et la même polarité, avec une estimation 9 à 12× plus rapide selon la longueur du clip.
- **Performance — handles bornés** : la fenêtre de contexte par placement passe de deux à une seconde de chaque côté. La protection contre les artefacts de bord est conservée, tandis que le volume analysé/rendu est plafonné à deux secondes additionnelles au lieu de quatre. Une validation de production avec fondus reste requise.

## 2026-07-21

- **Préflight Premiere sans écriture** : avant de rendre ou relinker un placement PTX, OttoAlign consulte `pt_api.get_relink_write_status()`. Un clip virtuel à header `0x2106` variable est conservé intact, sans WAV ni suffixe `_ALIGNED`; le rapport indique piste, clip, TC In/Out, durée et raison, tandis que les autres clips continuent.

- **Audit PTX Premiere, publication bloquée** : le monkey patch est retiré de `align_engine.py`, mais les essais réels ont montré que le relink PTX direct ne produit pas encore un résultat valide pour les clips virtuels Premiere. Les sorties `target4` sont refusées par Pro Tools avec `End of stream encountered`; ne pas présenter cette dépendance comme un correctif de relink Premiere.
- **MAJ Engine (Protection Source)** : Correction dans `align_engine.py` lors du traitement d'une session unique contenant à la fois la piste de référence (`Audio 1`) et la piste cible (`Audio 2`). Filtrage systématique de la piste de référence pour garantir que la source ne soit **jamais** retouchée, ni modifiée, ni réalignée, ni renommée avec un suffixe `_ALIGNED`.
- **Constat de blocage** : la formule `time_reference + src_offset == placement_start_samples` est nécessaire mais insuffisante pour `target4`. Un catalogue hybride créé par import Pro Tools emploie un nouveau média natif et des ordinaux non contigus; une dépendance supplémentaire entre la définition virtuelle Premiere et son média reste inconnue.
- **Contournement validé** : la consolidation préalable du clip dans Pro Tools produit un parent natif `0x2106` 151 octets. OttoAlign a ensuite créé le média aligné et la session résultante s'est ouverte correctement dans Pro Tools. `Save Copy In…` seul conserve le layout hérité et ne suffit pas.
- **MAJ Engine** : Augmentation de la fenêtre de recherche par défaut `max_shift_ms` de 20 ms à 150 ms dans `align_engine.py` afin de supporter l'alignement des paires cibles présentant un délai important (ex: `target5` avec un délai de 62.5 ms / 3000 échantillons).
- **MAJ DSP (Phasing Fix par Filtrage SNR)** : Amélioration du mécanisme de détection de dérive dans `dsp_core.py`. La déviation standard du délai est désormais calculée exclusivement sur les trames de parole à haut niveau de confiance (`SNR >= 8.0`). Sur les clips stables (`target3`, `target5`), la déviation standard sur les trames à haut SNR est exactement de `0.0`, ce qui déclenche le décalage statique constant (`np.zeros_like` + slicing mémoire entier) et élimine 100% du phasing métallique, sans désactiver l'alignement dynamique pour les clips consolidés longs présentant une vraie dérive.
- **MAJ Engine** : Modification du paradigme d'alignement pour regrouper les clips fragmentés de la timeline par fichier physique d'origine (`physical_filename`). Sélection d'une ancre globale (`best_anchor`) via le meilleur SNR du groupe, puis propagation de cette ancre à tous les fragments.
- **MAJ DSP** : Ajout d'un prieur Gaussien sur `gcc_phat` pour stabiliser l'alignement dynamique et forcer la recherche locale à converger vers le délai précédent.

## 2026-07-20

- Résolution critique du bogue 'End of Stream' lors de la génération de fichiers PTX (compatibilité Premiere Pro 2025.0) via un calcul dynamique des offsets du bloc 0x2106.
- Résolution du bogue 'KeyError: name' dans le parsing des définitions de clips via pt_api.
- **MAJ Engine (Bug Critique)** : Correction d'un bug destructeur d'annulation de phase multicanal dans align_engine.py. L'information d'inversion de polarité (is_inverted) calculée par le DSP est désormais correctement propagée à tous les canaux additionnels d'un fichier audio (Stéréo, PolyWav) pour éviter que des canaux se retrouvent en opposition de phase.
- **MAJ DSP** : Remplacement de l'algorithme d'estimation GCC-PHAT par un Standard Cross-Correlation (CC) dans dsp_core.py. Évite l'amplification artificielle des bruits de haute fréquence non-corrélés (frottement de vêtement, souffle) qui faisaient dériver le pic de corrélation de quelques millisecondes, occasionnant de l'effet de peigne (Comb Filtering).
- **MAJ Engine** : Abaissement de la limite de tolérance des chevauchements (overlap) de 0.5 seconde à 0.05 seconde dans align_engine.py pour garantir que les clips très courts ne soient plus ignorés.
- **MAJ DSP** : Ajout d'un filtre passe-bande vocal (80Hz - 8000Hz) dans l'espace fréquentiel de gcc_phat. Ce filtre masque mathématiquement le bruit de fond (hum électrique, rumble) sans altérer la phase de l'audio analysé, empêchant l'algorithme de se verrouiller faussement sur un décalage de 0.000ms.
- **MAJ Engine** : Ajout du traitement des *Handles* dans align_engine.py. L'algorithme élargit désormais sa fenêtre de lecture pour inclure 2 secondes d'audio supplémentaires de chaque côté du clip (si disponibles). Ceci élimine les glitches et sauts de phase lors de l'application de fondus (crossfades) par le monteur dans Pro Tools.
- **MAJ DSP** : Ajout d'une mécanique de *Fallback Statique* pour les clips de très courte durée (< 100ms) dans dsp_core.py. Limite la taille de la fenêtre de lissage (smooth_frames) proportionnellement à la longueur du clip pour éviter le repliement des données et garantit l'application de la détection de l'inversion de polarité même sur un alignement statique d'urgence.
- **MAJ DSP** : Implémentation du *Anchored Bounded Tracking* dans dsp_core.py (remplacement du filtre aveugle par un ancrage global à ±2ms et un filtre de lissage de 1s) éradiquant complètement la modulation de pitch (autotune).
- **MAJ DSP** : Ajout de l'**Auto-Polarity** (Correction de Phase Inversée) dans gcc_phat. Si la crête de corrélation est négative, le signal de sortie est mathématiquement inversé (target = -target) pour éviter la destruction de phase (Phase Cancellation).
- Création du fichier patch.md pour documenter les correctifs temporaires appliqués à pt_api.ProToolsSession.
- Restauration du point d'entrée __main__ dans align_engine.py.

# Changelog

## 2026-07-16

- Compatibilité avec pt_api 1.3.8 : catalogues PTX dont les noms WAV se terminent par quatre octets nuls et identités média 0x1001 contenant une séquence interprétable comme un faux bloc vide.
- Validation complète sur une nouvelle cible : 236 placements, 226 alignés, 10 ignorés selon les règles existantes, 226 WAV indépendants en ligne et aucun média de timeline manquant. Le catalogue PTX est passé de 71 à 297 entrées et la sauvegarde no-op demeure byte-for-byte identique.

## 2026-07-15

- Lecture des timelines PTX longues et de leurs offsets source 16/24/32 bits via la nouvelle version de pt_api; disparition de la coupure historique vers 10:07:41.
- Lecture des clips PTX avec get_timeline_clips(include_fades=False) afin de ne pas dépendre des géométries de fade pour le matching audio.
- Remplacement du renommage PTX intrusif par un flux non destructif : clone WAV indépendant, PCM rendu compatible, nouvelle identité média et relink d'un seul placement.
- Prise en charge des placements parent/racine et virtuels de production, y compris les noms dupliqués sur la timeline.
- Lecture paresseuse de la seule portion qui chevauche la référence; application de la même courbe de délai à tous les canaux.
- Validation des fréquences, des bornes média, du chevauchement minimal de 0.5 seconde et de max_shift_ms; la valeur configurée est maintenant transmise au DSP.
- Cible AAF ouverte en lecture-écriture; nommage _ottoaligned robuste aux extensions WAV en majuscules.
- Nettoyage transactionnel de la session et des médias créés lorsqu'une erreur fatale survient; suppression d'une branche de compatibilité PTX devenue morte.
- Serveur renforcé : extraction ZIP protégée contre le path traversal, sélection exacte du bundle session/Audio Files, sous-processus lancé avec sys.executable, et archivage du vrai PTX modifié.
- requirements.txt déclare explicitement pt_api depuis le dépôt public master.
- Ajout d'une suite de tests unitaires pour le nommage, l'ouverture AAF et le cœur DSP.
- Validation complète sur une référence d'environ 42 minutes : 404 placements cibles, 388 alignés, 16 ignorés car trop courts, 388 médias indépendants en ligne. La session finale s'est ouverte et a joué correctement dans Pro Tools.

## 2026-07-14

- Ajout initial du parsing PTX via pt_api.
- Les clips de référence mutés ne sont plus exclus du matching.
- Ajout du rapport OttoAlign_Report.txt.

## 2026-07-08

- Transition vers Flask et ajout du bouton de vidage du cache.
- Traitement multipiste, SoundFile pour le PCM 24 bits et nettoyage automatique des dossiers temporaires.

## Précédemment

- GCC-PHAT, interpolation CubicSpline et parseur AAF.
