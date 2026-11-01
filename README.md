# Analyse Foot — 14 championnats européens

| Pays | Championnats |
|---|---|
| Espagne | LaLiga, LaLiga 2 |
| France | Ligue 1, Ligue 2 |
| Angleterre | Premier League, Championship, League One, League Two, National League |
| Allemagne | Bundesliga, 2. Bundesliga |
| Italie | Serie A, Serie B |
| Belgique | Pro League |

Couverture : les 5 grands championnats ont tout (calendrier complet, classement officiel, stats joueurs, xG, absences). La Championship a le calendrier complet et le classement officiel. Les autres divisions ont résultats, classement calculé, stats de jeu, cotes et pronostics des matchs de la semaine à venir (pas de stats joueurs). Le Maroc (Botola Pro) n'est pas couvert par une source gratuite sans inscription.

Application web d'analyse des matchs : pronostics, classements, fiches équipes, analyse détaillée d'un match et mesure de la fiabilité du modèle. Les données se mettent à jour automatiquement chaque lundi matin.

## Sources de données

| Source | Contenu | Clé |
|---|---|---|
| [football-data.org](https://www.football-data.org) | Saison en cours : calendrier, résultats, classement officiel | gratuite, obligatoire |
| [football-data.co.uk](https://www.football-data.co.uk) | 10 saisons : résultats, score à la mi-temps, tirs, tirs cadrés, corners, fautes, cartons, xG (saison en cours), cotes des bookmakers, prochains matchs avec cotes | aucune |
| [understat.com](https://understat.com) | 4 saisons : xG par match, PPDA (pressing), passes dans les 20 derniers mètres, points attendus ; stats des joueurs (minutes, buts, xG, passes décisives, xA, tirs, passes clés) ; compositions des derniers matchs | aucune |

Les deux sources sont reliées automatiquement : les noms d'équipes sont associés en comparant les matchs communs (même jour, même score).

## Ce que fait l'application

| Rubrique | Contenu |
|---|---|
| **Pronostics** | Matchs des 14 prochains jours : probabilités 1 / N / 2, buts attendus, score le plus probable, +2,5 buts, « les deux marquent », probabilités des bookmakers et écarts avec le modèle |
| **Classement** | Classement officiel, forme sur 5 matchs, tendances du championnat (buts, xG, tirs, corners, cartons par match…) |
| **Joueurs** | Classement des joueurs du championnat, triable par buts, xG, passes décisives, xA, finition (buts − xG), xG par 90 minutes, passes clés ; filtre par équipe |
| **Équipes** | Classement de puissance (Elo sur 10 saisons), indices d'attaque et de défense, stats domicile / extérieur, joueurs clés et part des occasions de chacun, absents du dernier match, indicateurs avancés (xG, PPDA, deep, points attendus, finition, forme xG), stats de jeu, classement final des 10 dernières saisons |
| **Analyse match** | N'importe quelle affiche : probabilités, marchés, grille des scores, cotes « justes », corners et cartons attendus, score probable selon chaque issue, comparaison des indicateurs avancés, joueurs clés et absences des deux équipes, face-à-face sur 10 saisons avec score à la mi-temps |
| **Fiabilité** | Test du modèle sur la saison en cours et sur toute la saison passée, comparé aux bookmakers |

### Le modèle

- **Poisson / Dixon-Coles** : chaque équipe reçoit une force d'attaque et de défense, estimée sur les 3 dernières saisons (les matchs récents comptent davantage, et les xG sont pris en compte quand ils existent). On en déduit les buts attendus de chaque équipe, puis la probabilité de chaque score.
- **Elo** : note de puissance calculée sur 10 saisons, mise à jour après chaque match, en tenant compte de l'écart de buts et de l'avantage du terrain.
- **Nuls calibrés** : le modèle de Poisson sous-estime légèrement les nuls ; un coefficient, réglé automatiquement sur l'historique récent de chaque championnat, corrige cet écart.
- Réglages choisis en testant le modèle sur les saisons 2024-25 et 2025-26 des trois championnats (2 132 matchs).
- **Absences** : un joueur important (au moins 15 % des occasions de son équipe, ou titulaire régulier) qui n'a pas joué le dernier match est signalé. La raison n'est pas connue (blessure, suspension, repos), et le pronostic n'en tient pas compte.
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

- Chaque **lundi et vendredi à 06:13 UTC**, GitHub récupère les résultats, le calendrier et les cotes, recalcule tout et republie le site. La mise à jour du vendredi sert surtout aux divisions inférieures, dont le programme et les cotes ne sont publiés qu'en milieu de semaine.
- Pour forcer une mise à jour (par exemple avant des matchs de semaine) : *Actions → Run workflow*, possible depuis l'application mobile GitHub.
- Pour changer la fréquence, modifiez la ligne `cron` dans `.github/workflows/update.yml` (exemple pour lundi et jeudi : `13 6 * * 1,4`).
- Les données sont conservées dans `data/raw/` (football-data.org) et `data/history/` (football-data.co.uk). Les saisons terminées ne sont téléchargées qu'une fois.

## Structure

```
scripts/fetch_data.py     récupération de la saison en cours (football-data.org)
scripts/fetch_history.py  récupération de l'historique et des cotes (football-data.co.uk)
scripts/history.py        lecture de l'historique, correspondance des équipes, stats de jeu
scripts/fetch_understat.py récupération des stats avancées et joueurs (understat.com)
scripts/understat.py      indicateurs avancés, joueurs, absences
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
- `XG_WEIGHT` : part des xG dans l'estimation des forces (0,7 = 70 % xG, 30 % buts réels).
- `HISTORY_DAYS` : profondeur d'historique utilisée pour les forces.

Après un changement, la rubrique **Fiabilité** permet de vérifier si le modèle s'améliore (score de Brier plus bas = mieux).
