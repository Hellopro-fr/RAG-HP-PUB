# PHP front Ecritel — workflow

**Règle stricte : on ne crée PAS de Pull Request pour les fichiers PHP front Ecritel.**
Le développeur (rravelonarisoa@hellopro.fr) uploade ces fichiers manuellement via FTP sur le serveur Ecritel. Les PRs sur ces fichiers polluent l'historique git sans valeur ajoutée (pas de CI, pas de déploiement automatique, fichier non tracké en prod).

## Fichiers concernés (PHP front Ecritel)

| Chemin local repo | Statut git | Workflow |
|---|---|---|
| `site/hellopro_fr/*.php` | non tracké | Upload FTP manuel |
| `site/annuaire_hp/fonctions/*.php` | non tracké | Upload FTP manuel |
| `site/moteur_recherche/*.php` (search_ajax.php, etc.) | non tracké | Upload FTP manuel |
| `site/design_system/js/*.js` | non tracké | Upload FTP manuel |
| `site/fichiers_communs_bo_front/**/*.json` | non tracké | Upload FTP manuel |
| `site/script/**/*.php` (crons) | tracké git | PR OK (déployé via script.hellopro.fr) |
| `site/moteur_recherche/*.md` (docs/specs) | tracké git | PR OK (mémoire technique) |

## Procédure correcte pour modifier un fichier Ecritel

1. **Modifier le fichier local** dans le repo (édition directe)
2. **NE PAS créer de PR** sur le fichier `.php` lui-même
3. **Créer un doc `.md`** dans `site/moteur_recherche/` (ex: `FIX_XXX_YYYY-MM-DD.md`) qui contient :
   - Le diff appliqué (en bloc markdown)
   - Le contexte / motivation
   - Les tests post-deploy
4. **PR avec uniquement le `.md`** (spec / review-only)
5. **Upload manuel FTP** du `.php` modifié vers Ecritel par le développeur
6. **Test sur prod** + validation

## Exemple

- ❌ Ne pas faire : PR contenant `site/hellopro_fr/moteur_recherche.php` ajouté/modifié
- ✅ Faire : PR contenant `site/moteur_recherche/BASCULE_DEFAULT_HYBRID_2026-05-22.md` (doc avec diff), upload manuel du `.php`
