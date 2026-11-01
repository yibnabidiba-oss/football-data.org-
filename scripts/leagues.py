"""Championnats suivis.

  fd        : couvert par football-data.org (calendrier complet, classement officiel). Le code
              du championnat est alors la clé du dictionnaire (PL, PD, FL1, BL1, SA, ELC).
  csv       : fichier football-data.co.uk (historique, stats de jeu, cotes, prochains matchs).
  understat : nom du championnat sur understat.com (xG, joueurs), si couvert.
  tier      : niveau de la division (1 = première division).
"""

LEAGUES = {
    # Espagne
    "PD": {"slug": "liga", "name": "LaLiga", "country": "Espagne", "tier": 1, "csv": "SP1", "fd": True, "understat": "La_liga"},
    "SP2": {"slug": "liga-2", "name": "LaLiga 2", "country": "Espagne", "tier": 2, "csv": "SP2"},
    # France
    "FL1": {"slug": "ligue-1", "name": "Ligue 1", "country": "France", "tier": 1, "csv": "F1", "fd": True, "understat": "Ligue_1"},
    "F2": {"slug": "ligue-2", "name": "Ligue 2", "country": "France", "tier": 2, "csv": "F2"},
    # Angleterre
    "PL": {"slug": "premier-league", "name": "Premier League", "country": "Angleterre", "tier": 1, "csv": "E0", "fd": True, "understat": "EPL"},
    "ELC": {"slug": "championship", "name": "Championship", "country": "Angleterre", "tier": 2, "csv": "E1", "fd": True},
    "E2": {"slug": "league-one", "name": "League One", "country": "Angleterre", "tier": 3, "csv": "E2"},
    "E3": {"slug": "league-two", "name": "League Two", "country": "Angleterre", "tier": 4, "csv": "E3"},
    "EC": {"slug": "national-league", "name": "National League", "country": "Angleterre", "tier": 5, "csv": "EC"},
    # Allemagne
    "BL1": {"slug": "bundesliga", "name": "Bundesliga", "country": "Allemagne", "tier": 1, "csv": "D1", "fd": True, "understat": "Bundesliga"},
    "D2": {"slug": "2-bundesliga", "name": "2. Bundesliga", "country": "Allemagne", "tier": 2, "csv": "D2"},
    # Italie
    "SA": {"slug": "serie-a", "name": "Serie A", "country": "Italie", "tier": 1, "csv": "I1", "fd": True, "understat": "Serie_A"},
    "I2": {"slug": "serie-b", "name": "Serie B", "country": "Italie", "tier": 2, "csv": "I2"},
    # Belgique
    "B1": {"slug": "pro-league", "name": "Pro League", "country": "Belgique", "tier": 1, "csv": "B1"},
}
