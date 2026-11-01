# Analyse Foot — Premier League, LaLiga, Ligue 1

Application web d'analyse des matchs : pronostics, classements, fiches équipes, analyse détaillée d'un match et mesure de la fiabilité du modèle. Les données se mettent à jour automatiquement chaque lundi matin.

## Ce que fait l'application

| Rubrique | Contenu |
|---|---|
| **Pronostics** | Matchs des 14 prochains jours : probabilités 1 / N / 2, buts attendus, score le plus probable, +2,5 buts, « les deux marquent » |
| **Classement** | Classement officiel, forme sur 5 matchs, tendances du championnat (buts/match, % victoires à domicile, nuls…) |
| **Équipes** | Classement de puissance (Elo), indices d'attaque et de défense, stats domicile / extérieur / 5 derniers matchs |
| **Analyse match** | N'importe quelle affiche : probabilités, marchés (+1,5 / +2,5 / +3,5, les deux marquent, clean sheet), grille des scores, cotes « justes », face-à-face |
| **Fiabilité** | Test du modèle sur les matchs déjà joués (chaque prédiction faite uniquement avec les données disponibles avant le match) |

### Le modèle

- **Poisson / Dixon-Coles** : chaque équipe reçoit une force d'attaque et de défense, estimée sur les résultats passés (les matchs récents comptent davantage). On en déduit les buts attendus de chaque équipe, puis la probabilité de chaque score.
- **Elo** : note de puissance mise à jour après chaque match, en tenant compte de l'écart de buts et de l'avantage du terrain.
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
- Les données brutes sont conservées dans `data/raw/`. L'offre gratuite ne donne que la saison en cours : l'historique se construit donc d'une saison à l'autre, et le modèle gagne en précision au fil du temps.

## Structure

```
scripts/fetch_data.py   récupération des données (football-data.org)
scripts/analyze.py      calcul des analyses → site/data/*.json
scripts/model.py        modèle statistique (Poisson, Dixon-Coles, Elo, backtest)
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

- `DECAY_PER_DAY` : poids des matchs anciens (0,004 ≈ un match d'il y a 6 mois compte deux fois moins).
- `PRIOR_MATCHES` : prudence en début de saison (les forces sont ramenées vers la moyenne tant qu'il y a peu de matchs).

Après un changement, la rubrique **Fiabilité** permet de vérifier si le modèle s'améliore (score de Brier plus bas = mieux).
