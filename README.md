# Analyse Foot — Premier League, LaLiga, Ligue 1

Application web d'analyse des matchs : pronostics, classements, fiches équipes, analyse détaillée d'un match et mesure de la fiabilité du modèle. Les données se mettent à jour automatiquement chaque lundi matin.

## Sources de données

| Source | Contenu | Clé |
|---|---|---|
| [football-data.org](https://www.football-data.org) | Saison en cours : calendrier, résultats, classement officiel | gratuite, obligatoire |
| [football-data.co.uk](https://www.football-data.co.uk) | 10 saisons : résultats, score à la mi-temps, tirs, tirs cadrés, corners, fautes, cartons, xG (saison en cours), cotes des bookmakers, prochains matchs avec cotes | aucune |

Les deux sources sont reliées automatiquement : les noms d'équipes sont associés en comparant les matchs communs (même jour, même score).

## Ce que fait l'application

| Rubrique | Contenu |
|---|---|
| **Pronostics** | Matchs des 14 prochains jours : probabilités 1 / N / 2, buts attendus, score le plus probable, +2,5 buts, « les deux marquent », probabilités des bookmakers et écarts avec le modèle |
| **Classement** | Classement officiel, forme sur 5 matchs, tendances du championnat (buts, xG, tirs, corners, cartons par match…) |
| **Équipes** | Classement de puissance (Elo sur 10 saisons), indices d'attaque et de défense, stats domicile / extérieur, stats de jeu (xG, tirs, corners, cartons, mi-temps), classement final des 10 dernières saisons |
| **Analyse match** | N'importe quelle affiche : probabilités, marchés, grille des scores, cotes « justes », corners et cartons attendus, comparaison des stats de jeu, face-à-face sur 10 saisons avec score à la mi-temps |
| **Fiabilité** | Test du modèle sur la saison en cours et sur toute la saison passée, comparé aux bookmakers |

### Le modèle

- **Poisson / Dixon-Coles** : chaque équipe reçoit une force d'attaque et de défense, estimée sur les 3 dernières saisons (les matchs récents comptent davantage, et les xG sont pris en compte quand ils existent). On en déduit les buts attendus de chaque équipe, puis la probabilité de chaque score.
- **Elo** : note de puissance calculée sur 10 saisons, mise à jour après chaque match, en tenant compte de l'écart de buts et de l'avantage du terrain.
- Réglages choisis en testant le modèle sur les saisons 2024-25 et 2025-26 des trois championnats.
- Les probabilités restent des estimations. Un modèle statistique de ce type trouve le bon résultat 1N2 dans environ 50 % des cas ; la rubrique Fiabilité montre le résultat réel.

## Mise en ligne (15 minutes, gratuit)

1. **Clé API** : créez un compte gratuit sur [football-data.org](https://www.football-data.org/client/register). La clé arrive par e-mail.
2. **Dépôt GitHub** : créez un nouveau dépôt (par exemple `foot-analyse`) et envoyez-y tous les fichiers de ce dossier.
3. **Secret** : dans le dépôt, *Settings → Secrets and variables → Actions → New repository secret*
   - Nom : `FOOTBALL_DATA_API_KEY`
   - Valeur : votre clé
4. **Pages** : *Settings → Pages → Source : GitHub Actions*.
5. **Premier lancement** : onglet *Actions → Mise à jour et publication → Run workflow*.

Au bout de 2 à 3 minutes, le site est en ligne à l'adresse `https://<votre-compte>.github.io/foot-analyse/`.

Sans clé, le site fonctionne quand même avec des données simulées (clubs fictifs, bandeau jaune en haut).

## Mise à jour automatique

- Chaque **lundi à 06:13 UTC**, GitHub récupère les résultats et le calendrier, recalcule tout et republie le site.
- Pour forcer une mise à jour (par exemple avant des matchs de semaine) : *Actions → Run workflow*, possible depuis l'application mobile GitHub.
- Pour changer la fréquence, modifiez la ligne `cron` dans `.github/workflows/update.yml` (exemple pour lundi et jeudi : `13 6 * * 1,4`).
- Les données sont conservées dans `data/raw/` (football-data.org) et `data/history/` (football-data.co.uk). Les saisons terminées ne sont téléchargées qu'une fois.

## Structure

```
scripts/fetch_data.py     récupération de la saison en cours (football-data.org)
scripts/fetch_history.py  récupération de l'historique et des cotes (football-data.co.uk)
scripts/history.py        lecture de l'historique, correspondance des équipes, stats de jeu
scripts/analyze.py        calcul des analyses → site/data/*.json
scripts/model.py          modèle statistique (Poisson, Dixon-Coles, Elo, backtest)
scripts/demo_data.py    données simulées pour tester sans clé
site/                   application web (HTML, CSS, JavaScript, sans dépendance)
tests/                  tests du modèle
.github/workflows/      mise à jour hebdomadaire et publication
```

## Tester sur un ordinateur

```bash
python scripts/demo_data.py
python scripts/analyze.py --demo
python -m http.server -d site 8000
```

Puis ouvrez http://localhost:8000. Avec une vraie clé : `FOOTBALL_DATA_API_KEY=xxxx python scripts/fetch_data.py && python scripts/analyze.py`.

## Réglages du modèle

Dans `scripts/model.py` :

- `DECAY_PER_DAY` : poids des matchs anciens (0,002 ≈ un match d'il y a un an compte deux fois moins).
- `PRIOR_MATCHES` : prudence quand une équipe a peu de matchs (promus).
- `XG_WEIGHT` : part des xG dans l'estimation des forces (0,5 = moitié buts réels, moitié xG).
- `HISTORY_DAYS` : profondeur d'historique utilisée pour les forces.

Après un changement, la rubrique **Fiabilité** permet de vérifier si le modèle s'améliore (score de Brier plus bas = mieux).
