# Handoff OttoAlign2

**État vérifié le 2026-07-22**

## État actuel

1. La piste source `Audio 1` reste exclue lorsqu'une même session contient la référence et la cible : elle n'est ni réalignée, ni renommée, ni réécrite.
2. OttoAlign2 appelle directement `pt_api` 1.3.9. Aucun monkey patch ne surcharge `ProToolsSession`.
3. **Préflight Premiere sûr** : avant tout rendu PTX, `align_engine.py` appelle `get_relink_write_status()` pour chaque placement. Le corpus `target4` est détecté comme `premiere_virtual_media` avec header `0x2106` de 173 octets; ce placement reste intact dans la copie PTX, sans WAV créé ni suffixe `_ALIGNED`. Le rapport liste piste, clip, TC In, TC Out (borne de fin), durée et raison; les autres placements continuent.
4. **Blocage d'écriture Premiere** : les headers variables et les clips virtuels sont lisibles, mais `target4_api1381.ptx`, `target4_aligned.ptx`, le contrôle de référence virtuelle et le contrôle de catalogue hybride sont tous refusés par Pro Tools avec `End of stream encountered`. Un `Save Copy In…` conserve lui aussi le header Premiere 173 octets et le clip virtuel; il ne règle pas le problème. Le skip préventif est sûr, mais ne constitue pas un relink PTX Premiere.
5. **Contournement validé** : après `Consolidate Clip`, `target4_consolidated_reference.ptx` utilise un parent natif et un header `0x2106` de 151 octets. OttoAlign a créé `OA00000001.wav`/`target3_01_ALIGNED`, et `target4_consolidated_otto.ptx` s'est ouvert correctement dans Pro Tools. Le témoin n'avait pas de handles supplémentaires; le workflow « consolidation élargie puis retrim » reste à valider si nécessaire.
6. Les corpus `target3`, `target4` et `target5` non consolidés se rechargent dans le parseur Python, ce qui ne constitue pas une validation Pro Tools. Les résultats publiables sont les chemins natifs, le contournement consolidé et une session mixte où les clips Premiere détectés sont explicitement laissés intacts.
7. Le calcul DSP conserve le filtrage SNR et la fenêtre `max_shift_ms = 150` ms déjà validés.
8. La sélection de l'ancre de groupe utilise `interp=1` : la correction rendue est déjà un décalage entier, donc l'ancienne interpolation FFT ×16 n'apportait aucun bénéfice à la sortie. Les comparaisons réelles courtes ont conservé le même décalage entier et la même polarité, avec un gain de temps mesuré de 9 à 12× sur l'estimation. La validation « real world » reste requise.

## Dépendance

`requirements.txt` pointe vers le tag `v1.3.9`. Ne pas présenter cette dépendance comme un correctif de relink Premiere; OttoAlign2 peut toutefois être déployé pour les sessions mixtes à condition de présenter explicitement les clips Premiere détectés comme ignorés.

La lecture de contexte (« handles ») est limitée à une seconde disponible de chaque côté du placement. Cette limite réduit la taille des FFT et les E/S sur les clips fragmentés; elle devra être confirmée sur une session de production avec fondus réels.

## Documents historiques

`patch_api.md` reste le relevé historique du diagnostic. Ses parties compatibles et sûres sont intégrées dans `pt_api`; le code temporaire qui supprimait silencieusement des événements pendant une lecture n'a pas été repris.
