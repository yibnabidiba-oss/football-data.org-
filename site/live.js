/* Analyse Foot — recommandations et direct.
   Chargé avant app.js : expose window.FootLive, utilisé par app.js. */
(() => {
  "use strict";

  // ------------------------------------------------------------------ recommandations
  // Taux de réussite mesurés sur 10 346 matchs (saisons 2024-25 et 2025-26, 14 championnats),
  // avec des pronostics calculés uniquement à partir des matchs déjà joués.
  //   [favori gagne, double chance du favori]
  const TRACK = {
    book: { high: [0.700, 0.889], mid: [0.565, 0.814], low: [0.429, 0.717] },
    model: { high: [0.711, 0.894], mid: [0.523, 0.787], low: [0.426, 0.705] },
  };
  const CONF_LABEL = { high: "élevée", mid: "moyenne", low: "faible" };
  // Le modèle surestime les marchés de buts aux extrêmes (70 % annoncés = 62 % réels) :
  // on ramène ces probabilités vers 50 % avant de s'en servir pour conseiller.
  const shrink = (p) => 0.5 + (p - 0.5) * 0.65;

  function recommend(p, market, names) {
    const src = market ? "book" : "model";
    const P = market ? [market.p_home, market.p_draw, market.p_away] : [p.p_home, p.p_draw, p.p_away];
    const f = Math.max(...P), i = P.indexOf(f);
    const conf = f >= 0.6 ? "high" : f >= 0.5 ? "mid" : "low";
    const j = P[0] >= P[2] ? 0 : 2;
    const dc = { label: `${names[j]} ou nul`, p: P[j] + P[1], hist: TRACK[src][conf][1] };
    const win = { label: i === 1 ? "Match nul" : `Victoire ${names[i]}`, p: f, hist: TRACK[src][conf][0] };
    const main = conf === "low" || i === 1 ? dc : win;
    const alt = main === win ? dc : null;
    const o25 = market?.over25 ?? shrink(p.over25);
    const goalOpts = [
      { label: "Plus de 2,5 buts", p: o25 },
      { label: "Moins de 2,5 buts", p: 1 - o25 },
      { label: "Les deux équipes marquent", p: shrink(p.btts) },
      { label: "Au moins une équipe ne marque pas", p: 1 - shrink(p.btts) },
    ].sort((a, b) => b.p - a.p);
    const goals = goalOpts[0].p >= 0.6 ? goalOpts[0] : null;
    return { src, conf, main, alt, goals, open: conf === "low" };
  }

  // ------------------------------------------------------------------ direct : source ESPN
  const ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer";
  const STOP = new Set(["fc", "cf", "afc", "sc", "ac", "as", "ssc", "us", "rc", "cd", "ud", "sd", "club", "de", "la",
    "the", "fk", "sv", "vfb", "vfl", "tsg", "calcio", "football", "futbol", "cfc", "1", "kv", "krc", "kaa", "rsc", "sporting"]);
  const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((w) => w && !STOP.has(w));

  function sim(a, b) {
    const A = norm(a), B = norm(b);
    if (!A.length || !B.length) return 0;
    let s = 0;
    for (const x of A) {
      if (B.includes(x)) s += 1;
      else if (B.some((y) => (y.length >= 3 && x.startsWith(y)) || (x.length >= 3 && y.startsWith(x))
        || (x.length >= 4 && y.length >= 4 && x.slice(0, 4) === y.slice(0, 4)))) s += 0.6;
    }
    return s / Math.max(A.length, B.length);
  }

  async function fetchScoreboard(slug, day) {
    const r = await fetch(`${ESPN}/${slug}/scoreboard?dates=${day.replace(/-/g, "")}`, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  const stat = (comp, name) => {
    const s = (comp.statistics || []).find((x) => x.name === name);
    return s ? Number(s.displayValue) : null;
  };

  function parseEvent(ev) {
    const c = ev.competitions[0];
    const st = c.status || {};
    const type = st.type || {};
    const side = (ha) => c.competitors.find((x) => x.homeAway === ha);
    const H = side("home"), A = side("away");
    const det = c.details || [];
    const teamEvents = (tid) => det.filter((d) => d.team?.id === tid);
    const reds = (tid) => teamEvents(tid).filter((d) => d.redCard || /red card/i.test(d.type?.text || "")).length;
    const goals = det.filter((d) => d.scoringPlay).map((d) => ({
      team: d.team?.id === H.team.id ? "h" : "a", minute: d.clock?.displayValue || "",
      who: d.athletesInvolved?.[0]?.displayName || "", type: d.type?.text || "But", own: !!d.ownGoal, pen: !!d.penaltyKick,
    }));
    let minute = parseInt(st.displayClock, 10);
    if (Number.isNaN(minute)) minute = Math.floor((st.clock || 0) / 60);
    if (/HALFTIME/.test(type.name || "")) minute = 45;
    const pack = (x) => ({
      espn: x.team, name: x.team.displayName, score: Number(x.score || 0), red: reds(x.team.id),
      poss: stat(x, "possessionPct"), shots: stat(x, "totalShots"), sot: stat(x, "shotsOnTarget"),
      corners: stat(x, "wonCorners"), fouls: stat(x, "foulsCommitted"),
    });
    return {
      id: ev.id, date: ev.date, state: type.state, // pre | in | post
      detail: type.shortDetail || type.description || "", clock: st.displayClock || "",
      halftime: /HALFTIME/.test(type.name || ""), minute, home: pack(H), away: pack(A), goals,
    };
  }

  // ESPN -> match de l'app (même jour, noms les plus proches)
  function matchToApp(ev, candidates, teams) {
    const tsim = (espnTeam, id) => {
      const t = teams[id] || {};
      return Math.max(...[t.name, t.short].map((n) => Math.max(sim(espnTeam.displayName, n),
        sim(espnTeam.shortDisplayName, n), sim(espnTeam.name, n))));
    };
    let best = null;
    const t0 = new Date(ev.date).getTime();
    for (const m of candidates) {
      if (Math.abs(new Date(m.date).getTime() - t0) > 36 * 3600e3) continue;
      const s = tsim(ev.home.espn, m.home) + tsim(ev.away.espn, m.away);
      if (!best || s > best.s) best = { s, m };
    }
    return best && best.s >= 0.5 ? best.m : null;
  }

  // ------------------------------------------------------------------ direct : probabilités
  const fact = [1];
  for (let i = 1; i <= 15; i++) fact[i] = fact[i - 1] * i;
  const pois = (k, l) => Math.exp(-l) * l ** k / fact[k];

  /* lh, la : buts attendus sur 90 min avant le match. Le reste du match suit une loi de
     Poisson proportionnelle au temps restant, corrigée par les cartons rouges. */
  function liveProbs(lh, la, ev) {
    const gh = ev.home.score, ga = ev.away.score;
    const t = ev.state === "pre" ? 0 : Math.min(ev.minute || 0, 94);
    const frac = ev.state === "post" ? 0 : Math.max(0.02, (95 - t) / 95);
    const rh = lh * frac * 0.72 ** ev.home.red * 1.2 ** ev.away.red;
    const ra = la * frac * 0.72 ** ev.away.red * 1.2 ** ev.home.red;
    let ph = 0, pd = 0, pa = 0, btts = 0;
    const tot = gh + ga, over = { 0: 0, 1: 0, 2: 0 };
    for (let i = 0; i <= 10; i++) for (let j = 0; j <= 10; j++) {
      const v = pois(i, rh) * pois(j, ra), fh = gh + i, fa = ga + j;
      if (fh > fa) ph += v; else if (fh === fa) pd += v; else pa += v;
      if (fh > 0 && fa > 0) btts += v;
      for (const k of [0, 1, 2]) if (i + j > k) over[k] += v;
    }
    const s = ph + pd + pa, none = Math.exp(-(rh + ra));
    return {
      p_home: ph / s, p_draw: pd / s, p_away: pa / s, btts: btts / s, total: tot,
      more1: over[0] / s, more2: over[1] / s, more3: over[2] / s,
      next_home: rh + ra > 0 ? rh / (rh + ra) * (1 - none) : 0,
      next_away: rh + ra > 0 ? ra / (rh + ra) * (1 - none) : 0, next_none: none,
      rem_h: rh, rem_a: ra,
    };
  }

  // Lecture du jeu à partir des stats (indicatif, n'entre pas dans les probabilités)
  function reading(ev, nH, nA) {
    const out = [];
    const { home: h, away: a } = ev;
    if (h.sot != null && a.sot != null && h.sot + a.sot >= 3) {
      const d = h.sot - a.sot;
      if (Math.abs(d) >= 3) out.push(`${d > 0 ? nH : nA} domine devant le but : ${Math.max(h.sot, a.sot)} tirs cadrés contre ${Math.min(h.sot, a.sot)}.`);
    }
    if (h.poss != null && a.poss != null && Math.abs(h.poss - a.poss) >= 20) {
      out.push(`${h.poss > a.poss ? nH : nA} a le ballon (${Math.round(Math.max(h.poss, a.poss))} % de possession).`);
    }
    const lead = h.score - a.score;
    if (lead !== 0 && h.sot != null && a.sot != null) {
      const [ld, tr, sl, st] = lead > 0 ? [nH, nA, h.sot, a.sot] : [nA, nH, a.sot, h.sot];
      if (st > sl + 2) out.push(`${ld} mène, mais ${tr} cadre davantage : l'égalisation reste possible.`);
    }
    if (h.red || a.red) out.push(`Carton rouge : ${[h.red && `${nH} (${h.red})`, a.red && `${nA} (${a.red})`].filter(Boolean).join(", ")}. Les probabilités en tiennent compte.`);
    return out;
  }

  function liveAdvice(lp, ev, nH, nA) {
    const items = [];
    const P = [lp.p_home, lp.p_draw, lp.p_away], f = Math.max(...P), i = P.indexOf(f);
    const res = [`Victoire ${nH}`, "Match nul", `Victoire ${nA}`][i];
    if (f >= 0.75) items.push({ label: res, p: f });
    else {
      const j = P[0] >= P[2] ? 0 : 2;
      items.push({ label: `${[nH, "", nA][j]} ou nul`, p: P[j] + P[1] });
    }
    if (ev.state === "in") {
      items.push({ label: `Encore au moins un but (plus de ${lp.total},5)`, p: lp.more1 });
      if (lp.more2 >= 0.5) items.push({ label: `Plus de ${lp.total + 1},5 buts`, p: lp.more2 });
      if (!(ev.home.score > 0 && ev.away.score > 0)) items.push({ label: "Les deux équipes marquent", p: lp.btts });
    }
    return items.sort((a, b) => b.p - a.p);
  }

  window.FootLive = { recommend, CONF_LABEL, fetchScoreboard, parseEvent, matchToApp, liveProbs, reading, liveAdvice };
})();
