# Handoff OttoAlign2

**État vérifié le 2026-07-15**

## État actuel

Le chemin PTX non destructif est fonctionnel de bout en bout. Il lit les portions superposées, rend le décalage, clone un WAV indépendant pour chaque placement, relie seulement ce placement et sauvegarde la copie PTX réellement modifiée. Les originaux restent intacts.

La validation de production a utilisé :

- une référence PTX d’environ 42 minutes, 135 régions sur `REF PLANS`;
- une cible PTX de 404 placements sur `PFX 1` et `PFX 2`;
- 388 placements alignés et 16 ignorés pour chevauchement inférieur à 0,5 seconde;
- 388 nouveaux WAV indépendants, tous présents et en ligne;
- une session finale ouverte et écoutée avec succès dans Pro Tools;
- un placement dupliqué confirmé avec deux noms et deux identités de sortie distincts;
- une sauvegarde/relecture sans autre mutation demeurée byte-for-byte identique.

Les corrections associées comprennent le support des longs offsets PTX, les layouts virtuels de production, les headers `0x2106` de 142/151 octets, les variantes `regn`, la reconstruction des records fixes `0x2629`, l’installation d’un PCM rendu compatible et l’index média UInt32.

## Garanties du chemin PTX

- La session cible et les WAV sources ne sont jamais écrasés.
- Le fichier de sortie reste à côté du dossier `Audio Files` cible pendant sa construction.
- Chaque placement traité reçoit un nouveau fichier physique de même longueur de nom UTF-8 que sa source, une identité BWF/PTX renouvelée et un nom de clip unique.
- Seule la portion visible traitée change; le reste du WAV cloné est conservé.
- Une erreur fatale annule la session de sortie et supprime les médias créés pendant la transaction.
- Le serveur archive le PTX effectivement modifié, et non la session cible originale.

## AAF

La cible AAF est ouverte en mode `rw`, puis finalisée par `orchestrator.py`. Le nom `_ottoaligned` fonctionne aussi avec une extension `.WAV` en majuscules. Ce chemin est antérieur au relink PTX et n’offre pas la même isolation par placement lorsque plusieurs clips partagent un mob ou un média. Il doit donc être validé avec prudence pour tout nouveau cas AAF complexe.

## Tests automatisés

Le dossier `tests/` couvre actuellement :

- le codage base36 et les noms WAV PTX de longueur constante;
- les collisions de noms physiques et de noms de clips;
- le nommage AAF et l’ouverture de la cible AAF en lecture-écriture;
- le contrat de retour DSP pour une entrée courte;
- les corrections de délais entiers positifs et négatifs.

La suite complète doit être lancée depuis le dépôt avec `pt_api` disponible :

```bash
python -m unittest discover -s tests
```

## Limites à préserver dans les futures révisions

- WAV seulement; même fréquence d’échantillonnage pour chaque paire.
- Chevauchement minimal de 0,5 seconde.
- Recherche ±20 ms par défaut.
- Courbe calculée sur le premier canal et appliquée à tous les canaux.
- Un WAV complet par placement PTX aligné, donc croissance possible de l’espace disque.
- Le PTX dépend strictement des layouts pris en charge par la version publiée de `pt_api`.
- Les métadonnées AAF complexes et l’isolation des placements partageant un média ne sont pas garanties.
- État Flask en mémoire seulement; taille décompressée des ZIP non plafonnée séparément.

## Publication coordonnée

`requirements.txt` pointe vers `https://github.com/sebedard-creator/pt_api.git@master`. Publier dans cet ordre :

1. commit et push de `Y:\pt_api`;
2. vérification que le commit public contient la version attendue;
3. commit et push de `Y:\OttoAlign2`;
4. installation propre de `requirements.txt` dans un environnement neuf si un déploiement est prévu.

Les archives et sessions originales sous `test_sessions_original/` restent locales et ignorées par Git. Les sorties alignées, rapports et WAV OA générés ne doivent pas être commités.
