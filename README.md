# OttoAlign2

> L’interface web, les journaux et les rapports sont en français. Le code conserve des noms techniques en anglais.

![Interface OttoAlign2](OttoAlign2.png)

## Vue d’ensemble

OttoAlign2 aligne automatiquement les clips d’une session cible AAF ou PTX sur l’audio d’une session de référence. Le moteur estime une courbe de délai par GCC-PHAT, la lisse, puis applique un retard fractionnaire par interpolation cubique. Il vise les workflows de postproduction où plusieurs microphones couvrent la même source; il ne remplace ni l’écoute critique ni une validation finale dans le DAW.

## Fonctionnalités

- Traitement de toutes les pistes et de tous les clips cibles possédant un chevauchement avec la référence.
- Lecture paresseuse : seule la portion réellement superposée est chargée, même si le fichier source dure plusieurs dizaines de minutes.
- Fréquence d’échantillonnage lue dans chaque WAV; les deux médias d’une paire doivent avoir la même fréquence.
- Courbe calculée sur le premier canal, puis appliquée à l’identique à tous les canaux du média cible.
- Recherche de délai configurable, limitée par défaut à ±20 ms.
- Rapport `OttoAlign_Report.txt` listant les clips alignés, ignorés et leur correction moyenne.
- Extraction ZIP protégée contre les chemins sortant du répertoire de travail; limite HTTP de 2 Go pour la requête complète.

### Traitement PTX non destructif

Pour chaque placement PTX admissible, OttoAlign2 :

1. lit seulement la portion visible qui chevauche la référence;
2. copie le WAV source complet dans un rendu temporaire et remplace uniquement cette portion audio;
3. demande à `pt_api.relink_clip()` de créer un nouveau WAV indépendant, avec une nouvelle identité média BWF/PTX;
4. retargete uniquement le placement concerné et lui attribue un nom de clip unique (`_ALIGNED`, `_ALIGNED_2`, etc.).

Le PTX original et ses WAV ne sont jamais écrasés. Les échantillons hors de la portion traitée restent ceux du fichier source. Le nouveau WAV conserve le conteneur et le sous-type PCM du média Pro Tools, tout en renouvelant les métadonnées nécessaires au relink.

La validation de production couvre une référence d’environ 42 minutes, 404 placements cibles sur deux pistes, 388 placements alignés et 16 clips ignorés parce que leur chevauchement était inférieur à 0,5 seconde. Les 388 WAV générés étaient en ligne; la session complète s’est ouverte et a joué correctement dans Pro Tools. Un même clip source placé plusieurs fois a bien reçu des identités média distinctes.

### Traitement AAF

Le chemin AAF historique écrit des WAV suffixés `_ottoaligned`, modifie les locators dans une copie AAF ouverte en lecture-écriture, puis passe la sortie à `orchestrator.py`. Il est maintenu, mais la validation Pro Tools exhaustive décrite ci-dessus porte sur le chemin PTX.

## Installation et utilisation

L’environnement actuellement validé utilise Python 3.11.

```bash
python -m pip install -r requirements.txt
python server.py
```

Ouvrir ensuite `http://localhost:8081`.

Chaque archive doit contenir exactement une session complète `.aaf` ou `.ptx`, avec un dossier `Audio Files` placé à côté de cette session. Les dossiers peuvent être imbriqués dans le ZIP, mais la paire session/dossier doit être non ambiguë.

Le résultat `OttoAligned_Result.zip` contient :

- `OttoAligned.ptx` ou `OttoAligned.aaf`;
- le dossier `Audio Files` nécessaire à la sortie;
- `OttoAlign_Report.txt`.

Pour une cible PTX, le ZIP contient les WAV originaux de la cible et les nouveaux WAV alignés, puisque la session peut encore référencer les deux familles. Le serveur supprime ensuite les données extraites et conserve le ZIP final jusqu’au téléchargement ou au vidage du cache.

## Limites explicites

- Les médias physiques doivent être des WAV. Le chemin PTX exige les layouts et métadonnées Pro Tools documentés par la version de `pt_api` installée.
- Un chevauchement inférieur à 0,5 seconde est ignoré.
- Les médias de référence et cible d’une paire doivent avoir la même fréquence d’échantillonnage; aucun rééchantillonnage n’est effectué.
- Le délai est calculé depuis le premier canal. La même courbe est imposée aux autres canaux; aucun alignement indépendant par canal n’est effectué.
- La fenêtre de recherche par défaut est ±20 ms. Un décalage réel plus grand ne sera pas trouvé sans augmenter `max_shift_ms` lors d’un appel direct au moteur.
- Le DSP peut introduire des zéros aux frontières lorsque la courbe demande des échantillons situés hors de la portion disponible.
- Le PTX génère un WAV complet indépendant par placement aligné. Cette sécurité évite qu’un média partagé change ailleurs dans la timeline, mais peut augmenter fortement la taille du résultat.
- Un appel direct refuse d’écraser une session de sortie ou un WAV `_ottoaligned` déjà existant.
- Les fichiers PTX de sortie doivent rester à côté de leur propre dossier `Audio Files`; les noms internes du catalogue PTX ne sont jamais interprétés comme des chemins système.
- En AAF, Clip Gain, Clip Mute, effets, transitions complexes et métadonnées propres au DAW ne sont pas garantis. Les placements partageant le même mob/média ne bénéficient pas de l’isolation par placement offerte par le relink PTX; un nom de sortie `_ottoaligned` déjà présent est refusé plutôt que d’être écrasé.
- Les jobs sont conservés en mémoire par le processus Flask. Un redémarrage perd leur état, et ce serveur local n’est pas une architecture distribuée ou multi-instance.
- La limite de 2 Go s’applique à la requête compressée; aucune limite distincte n’est actuellement imposée à la taille décompressée des archives.

## Dépendance `pt_api`

`requirements.txt` installe `pt_api` depuis la branche publique `master`. Lors d’une publication coordonnée, il faut donc pousser et vérifier `pt_api` avant d’installer ou de déployer cette révision d’OttoAlign2.

---

*Conçu par Sébastien Bédard*
