/* Analyse Foot — interface (aucune dépendance). Les données viennent de data/*.json. */
(() => {
  "use strict";
  const VIEWS = ["matchs", "classement", "equipes", "analyse", "fiabilite"];
  const MAX_GOALS = 10;
  const app = document.getElementById("app");
  const state = { meta: null, slug: null, view: "matchs", data: {}, team: null, home: null, away: null };

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* stockage indisponible */ } },
  };

  // ------------------------------------------------------------------ utilitaires
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (p, d = 0) => (p * 100).toFixed(d).replace(".", ",") + " %";
  const num = (x, d = 2) => Number(x).toFixed(d).replace(".", ",");
  const D = () => state.data[state.slug];
  const nm = (id) => D().teams[id]?.short || D().teams[id]?.name || "?";
  const fmtDay = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  const fmtTime = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });
  const fmtShort = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "2-digit" });
  const fmtFull = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short" });
  const shortDate = (iso) => fmtShort.format(new Date(iso.length === 10 ? iso + "T12:00:00Z" : iso));

  // ------------------------------------------------------------------ modèle (identique à scripts/model.py)
  const fact = [1]; for (let i = 1; i <= MAX_GOALS; i++) fact[i] = fact[i - 1] * i;
  const pois = (k, l) => Math.exp(-l) * l ** k / fact[k];
  function tau(x, y, lh, la, rho) {
    if (x === 0 && y === 0) return 1 - lh * la * rho;
    if (x === 0 && y === 1) return 1 + lh * rho;
    if (x === 1 && y === 0) return 1 + la * rho;
    if (x === 1 && y === 1) return 1 - rho;
    return 1;
  }
  function markets(lh, la, rho, drawK = 1) {
    const m = []; let tot = 0;
    for (let i = 0; i <= MAX_GOALS; i++) {
      m.push([]);
      for (let j = 0; j <= MAX_GOALS; j++) { const v = pois(i, lh) * pois(j, la) * tau(i, j, lh, la, rho) * (i === j ? drawK : 1); m[i].push(v); tot += v; }
    }
    let h = 0, d = 0, o15 = 0, o25 = 0, o35 = 0, btts = 0, csh = 0, csa = 0; const scores = [];
    for (let i = 0; i <= MAX_GOALS; i++) for (let j = 0; j <= MAX_GOALS; j++) {
      const v = (m[i][j] /= tot);
      if (i > j) h += v; else if (i === j) d += v;
      if (i + j > 1.5) o15 += v; if (i + j > 2.5) o25 += v; if (i + j > 3.5) o35 += v;
      if (i > 0 && j > 0) btts += v; if (j === 0) csh += v; if (i === 0) csa += v;
      scores.push({ score: `${i}-${j}`, p: v });
    }
    scores.sort((a, b) => b.p - a.p);
    const best = {};
    for (const sc of scores) {
      const [i, j] = sc.score.split("-").map(Number);
      const k = i > j ? "home" : i === j ? "draw" : "away";
      if (!best[k]) best[k] = sc;
    }
    return { xg_home: lh, xg_away: la, p_home: h, p_draw: d, p_away: 1 - h - d, over15: o15, over25: o25, over35: o35,
      btts, home_clean_sheet: csh, away_clean_sheet: csa, top_scores: scores.slice(0, 6), best_by_outcome: best, matrix: m };
  }
  function predict(home, away) {
    const p = D().model;
    const lh = p.mu_home * (p.att[home] ?? 1) * (p.def[away] ?? 1);
    const la = p.mu_away * (p.att[away] ?? 1) * (p.def[home] ?? 1);
    return markets(lh, la, p.rho || 0, p.draw_k || 1);
  }

  // ------------------------------------------------------------------ composants
  const formChips = (form) => `<span class="form">${form.map((f) =>
    `<i class="${f.r}" title="${esc(f.venue === "D" ? "Dom." : "Ext.")} ${esc(nm(f.opp))} ${esc(f.score)}">${{ W: "V", D: "N", L: "D" }[f.r]}</i>`).join("")}</span>`;

  function bar(p) {
    const w = (x) => Math.max(x * 100, 0).toFixed(1) + "%";
    const lab = (x) => (x >= 0.12 ? Math.round(x * 100) + "%" : "");
    return `<div class="bar" role="img" aria-label="Victoire domicile ${pct(p.p_home)}, nul ${pct(p.p_draw)}, victoire extérieur ${pct(p.p_away)}">
      <span class="h" style="width:${w(p.p_home)}">${lab(p.p_home)}</span><span class="d" style="width:${w(p.p_draw)}">${lab(p.p_draw)}</span><span class="a" style="width:${w(p.p_away)}">${lab(p.p_away)}</span></div>
      <div class="bar-legend"><span>1 · domicile</span><span>N</span><span>extérieur · 2</span></div>`;
  }

  // Score le plus probable DANS l'issue la plus probable (évite le "1-1" systématique)
  function likelyScore(p) {
    const o = [["home", p.p_home], ["draw", p.p_draw], ["away", p.p_away]].sort((a, b) => b[1] - a[1])[0][0];
    return p.best_by_outcome?.[o] || p.top_scores[0];
  }

  function pickLabel(p, home, away) {
    const opts = [[p.p_home, `Victoire ${nm(home)}`], [p.p_draw, "Match nul"], [p.p_away, `Victoire ${nm(away)}`]].sort((a, b) => b[0] - a[0]);
    if (opts[0][0] < 0.45) { // pas de favori net : double chance
      const dc = p.p_home >= p.p_away ? [p.p_home + p.p_draw, `${nm(home)} ou nul`] : [p.p_away + p.p_draw, `${nm(away)} ou nul`];
      return `${dc[1]} (${pct(dc[0])})`;
    }
    return `${opts[0][1]} (${pct(opts[0][0])})`;
  }

  function marketLine(p, o, home, away) {
    const r = (x) => Math.round(x * 100);
    const labels = [`victoire ${nm(home)}`, "le nul", `victoire ${nm(away)}`];
    const mp = [p.p_home, p.p_draw, p.p_away], bp = [o.p_home, o.p_draw, o.p_away];
    const diffs = mp.map((v, i) => v - bp[i]);
    const i = diffs.indexOf(Math.max(...diffs));
    const edge = diffs[i] >= 0.05
      ? `<span class="chip edge">Le modèle croit plus que les bookmakers à ${esc(labels[i])} (+${r(diffs[i])} pts)</span>` : "";
    return `<div class="mkt"><span>Bookmakers</span><b>${r(o.p_home)} % · ${r(o.p_draw)} % · ${r(o.p_away)} %</b></div>${edge ? `<div class="chips">${edge}</div>` : ""}`;
  }

  // ------------------------------------------------------------------ vues
  function viewMatchs() {
    const d = D();
    if (!d.upcoming.length) return `<p class="empty">Aucun match programmé dans les 14 prochains jours.</p>`;
    const groups = new Map();
    for (const m of d.upcoming) {
      const key = fmtDay.format(new Date(m.date));
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(m);
    }
    let html = `<div class="section-head"><h2>Prochains matchs</h2><p class="sub">${d.upcoming.length} matchs · touchez un match pour l'analyse détaillée</p></div>`;
    for (const [day, ms] of groups) {
      html += `<section class="day"><div class="eyebrow">${esc(day)}</div><div class="cards">`;
      for (const m of ms) {
        const p = m.pred;
        html += `<button class="match" data-home="${m.home}" data-away="${m.away}">
          <div class="match-top"><span>${fmtTime.format(new Date(m.date))}${m.status === "POSTPONED" ? " · reporté" : ""}</span><span>J${m.matchday ?? "–"}</span></div>
          <div class="teams"><span class="team">${esc(nm(m.home))}</span>
            <span class="xg">${num(p.xg_home, 1)} – ${num(p.xg_away, 1)}<small>BUTS ATTENDUS</small></span>
            <span class="team away">${esc(nm(m.away))}</span></div>
          ${bar(p)}
          ${m.market ? marketLine(p, m.market, m.home, m.away) : ""}
          <div class="chips"><span class="chip pick">${esc(pickLabel(p, m.home, m.away))}</span>
            <span class="chip">Score probable <b>${likelyScore(p).score}</b></span>
            <span class="chip">+2,5 buts <b>${pct(p.over25)}</b></span>
            <span class="chip">Les deux marquent <b>${pct(p.btts)}</b></span></div>
        </button>`;
      }
      html += `</div></section>`;
    }
    return html;
  }

  function viewClassement() {
    const d = D(), t = d.trends, n = d.table.length;
    let html = `<div class="section-head"><h2>Classement</h2><p class="sub">${t.played || 0} matchs joués cette saison</p></div>`;
    if (t.played) {
      html += `<div class="trends">
        <div class="trend"><div class="v">${num(t.goals_avg)}</div><div class="k">buts par match</div></div>
        <div class="trend"><div class="v">${pct(t.home_win)}</div><div class="k">victoires à domicile</div></div>
        <div class="trend"><div class="v">${pct(t.draw)}</div><div class="k">matchs nuls</div></div>
        <div class="trend"><div class="v">${pct(t.away_win)}</div><div class="k">victoires à l'extérieur</div></div>
        <div class="trend"><div class="v">${pct(t.over25)}</div><div class="k">matchs à +2,5 buts</div></div>
        <div class="trend"><div class="v">${pct(t.btts)}</div><div class="k">les deux équipes marquent</div></div>
        ${t.game?.xg ? `<div class="trend"><div class="v">${num(t.game.xg)}</div><div class="k">xG par match</div></div>` : ""}
        ${t.game?.shots ? `<div class="trend"><div class="v">${num(t.game.shots, 1)}</div><div class="k">tirs par match</div></div>` : ""}
        ${t.game?.corners ? `<div class="trend"><div class="v">${num(t.game.corners, 1)}</div><div class="k">corners par match</div></div>` : ""}
        ${t.game?.cards ? `<div class="trend"><div class="v">${num(t.game.cards, 1)}</div><div class="k">cartons jaunes par match</div></div>` : ""}</div>`;
    }
    html += `<div class="scroll"><table><thead><tr><th class="l">#</th><th class="l">Équipe</th><th>J</th><th>G</th><th>N</th><th>P</th><th>Buts</th><th>Diff</th><th>Pts</th><th class="l">Forme</th></tr></thead><tbody>`;
    for (const r of d.table) {
      const zone = r.position <= 4 ? "zone-top" : r.position > n - 3 ? "zone-bottom" : "";
      const st = d.team_stats[r.team];
      html += `<tr class="clickable ${zone}" data-team="${r.team}"><td class="l pos">${r.position}</td><td class="l"><b>${esc(nm(r.team))}</b></td>
        <td>${r.played}</td><td>${r.won}</td><td>${r.draw}</td><td>${r.lost}</td><td>${r.gf}:${r.ga}</td>
        <td>${r.gd > 0 ? "+" : ""}${r.gd}</td><td class="pts">${r.points}</td><td class="l">${st ? formChips(st.form) : ""}</td></tr>`;
    }
    html += `</tbody></table></div><p class="note">Liseré vert : 4 premières places. Liseré rouge : 3 dernières places. Touchez une équipe pour sa fiche.</p>`;
    return html;
  }

  function viewEquipes() {
    const d = D();
    const order = [...d.season_teams].sort((a, b) => d.team_stats[b].elo - d.team_stats[a].elo);
    if (!state.team || !d.team_stats[state.team]) state.team = order[0];
    const max = d.team_stats[order[0]].elo, min = d.team_stats[order[order.length - 1]].elo;
    const list = order.map((t, i) => {
      const s = d.team_stats[t], w = 8 + 92 * (s.elo - min) / Math.max(max - min, 1);
      return `<button class="power-row ${t === state.team ? "on" : ""}" data-team="${t}"><span class="rk">${i + 1}</span>
        <span><span class="nm">${esc(nm(t))}</span><div class="meter"><span style="width:${w.toFixed(0)}%"></span></div></span>
        <span class="el">${Math.round(s.elo)}</span></button>`;
    }).join("");
    return `<div class="section-head"><h2>Équipes</h2><p class="sub">Classement de puissance (note Elo) · touchez une équipe</p></div>
      <div class="team-layout"><div class="power">${list}</div>${teamPanel(state.team)}</div>`;
  }

  function teamPanel(t) {
    const d = D(), s = d.team_stats[t], n = d.season_teams.length;
    const row = (label, b) => `<tr><td class="l">${label}</td><td>${b.played}</td><td>${b.won}-${b.draw}-${b.lost}</td><td>${b.gf}:${b.ga}</td>
      <td>${num(b.ppg)}</td><td>${b.played ? pct(b.over25) : "–"}</td><td>${b.played ? pct(b.btts) : "–"}</td><td>${b.played ? pct(b.clean_sheets) : "–"}</td></tr>`;
    const next = d.upcoming.find((m) => m.home === t || m.away === t);
    const form = s.form.slice().reverse().map((f) => `<div><span class="form"><i class="${f.r}">${{ W: "V", D: "N", L: "D" }[f.r]}</i></span>
      <span>${f.venue === "D" ? "vs" : "à"} ${esc(nm(f.opp))} <b>${esc(f.score)}</b></span><span class="when">${shortDate(f.date)}</span></div>`).join("");
    return `<section class="panel"><div class="section-head"><h3>${esc(d.teams[t].name)}</h3>
        <span class="eyebrow">${s.rank_elo}<sup>e</sup> sur ${n} en puissance</span></div>
      <div class="kpis">
        <div class="kpi"><div class="v">${num(s.all.ppg)}</div><div class="k">points par match</div></div>
        <div class="kpi"><div class="v">${Math.round(s.att * 100)}</div><div class="k">indice d'attaque</div><div class="r">${s.rank_att}<sup>e</sup> de la ligue</div></div>
        <div class="kpi"><div class="v">${Math.round(100 / s.def)}</div><div class="k">indice de défense</div><div class="r">${s.rank_def}<sup>e</sup> de la ligue</div></div>
        <div class="kpi"><div class="v">${num(s.all.gf_avg)} / ${num(s.all.ga_avg)}</div><div class="k">buts marqués / encaissés par match</div></div>
      </div>
      <p class="note">Indices : 100 = moyenne du championnat. 130 en attaque = marque environ 30 % de plus qu'une équipe moyenne face au même adversaire.</p>
      <div class="scroll"><table><thead><tr><th class="l"></th><th>J</th><th>V-N-D</th><th>Buts</th><th>Pts/m</th><th>+2,5</th><th>2 marquent</th><th>Sans encaisser</th></tr></thead><tbody>
        ${row("Total", s.all)}${row("Domicile", s.home)}${row("Extérieur", s.away)}${row("5 derniers", s.last5)}</tbody></table></div>
      ${gameBlock(s.game)}
      ${pastBlock(s.past)}
      <div class="formlist"><div class="eyebrow">Derniers matchs</div>${form || '<p class="empty">Aucun match joué.</p>'}</div>
      ${next ? `<button class="btn" data-home="${next.home}" data-away="${next.away}" id="next-match">Analyser le prochain match : ${esc(nm(next.home))} – ${esc(nm(next.away))}</button>` : ""}
    </section>`;
  }

  function gameBlock(g) {
    if (!g) return "";
    const pair = (label, k, d = 1) => g[k + "_for"] != null
      ? `<tr><td class="l">${label}</td><td>${num(g[k + "_for"], d)}</td><td>${num(g[k + "_against"], d)}</td></tr>` : "";
    const kv = (label, v) => v != null ? `<div><span>${label}</span><b>${pct(v)}</b></div>` : "";
    return `<div class="sub-block"><div class="eyebrow">Stats de jeu cette saison · par match</div>
      <div class="scroll" style="border:0"><table><thead><tr><th class="l"></th><th>Pour</th><th>Contre</th></tr></thead><tbody>
        ${pair("xG (buts attendus)", "xg", 2)}${pair("Tirs", "shots")}${pair("Tirs cadrés", "sot")}${pair("Corners", "corners")}
        ${pair("Fautes", "fouls")}${pair("Cartons jaunes", "yellow", 2)}${pair("Cartons rouges", "red", 2)}</tbody></table></div>
      <div class="kv">${kv("Tirs transformés en buts", g.conversion)}${kv("Mène à la mi-temps", g.ht_lead)}
        ${kv("Gagne quand il mène à la pause", g.ht_lead_won)}${kv("Mené à la pause : nul ou victoire", g.ht_comeback)}
        ${kv("Buts marqués en 2<sup>e</sup> période", g.goals_2nd_half)}</div></div>`;
  }

  function pastBlock(past) {
    if (!past || !past.length) return "";
    const cols = past.slice(-10).map((p) => {
      if (p.pos == null) return `<div class="ps out" title="${p.season} : pas dans ce championnat"><span class="pb" style="height:4%"></span><b>–</b><small>${p.season.slice(2)}</small></div>`;
      const h = 12 + 88 * (p.n - p.pos) / Math.max(p.n - 1, 1);
      return `<div class="ps ${p.pos === 1 ? "champ" : ""}" title="${p.season} : ${p.pos}e, ${p.pts} pts, ${p.gf}:${p.ga}"><span class="pb" style="height:${h.toFixed(0)}%"></span><b>${p.pos}<sup>e</sup></b><small>${p.season.slice(2)}</small></div>`;
    }).join("");
    return `<div class="sub-block"><div class="eyebrow">Classement final des saisons passées</div><div class="past">${cols}</div>
      <p class="note">« – » : l'équipe jouait dans une autre division cette saison-là.</p></div>`;
  }

  function h2hBlock(h, a) {
    const d = D();
    const all = d.h2h.filter((r) => (r[1] === h && r[2] === a) || (r[1] === a && r[2] === h));
    if (!all.length) return `<p class="empty">Aucune confrontation depuis ${d.history_seasons?.[0] || "le début des données"}.</p>`;
    let wh = 0, dr = 0, wa = 0, goals = 0, o25 = 0, btts = 0, vh = 0, vd = 0, va = 0, vn = 0;
    for (const r of all) {
      const gh = r[1] === h ? r[3] : r[4], ga = r[1] === h ? r[4] : r[3];
      wh += gh > ga; dr += gh === ga; wa += gh < ga;
      goals += r[3] + r[4]; o25 += r[3] + r[4] > 2; btts += r[3] > 0 && r[4] > 0;
      if (r[1] === h) { vn++; vh += r[3] > r[4]; vd += r[3] === r[4]; va += r[3] < r[4]; }
    }
    const n = all.length;
    const since = all[0][0].slice(0, 4);
    const list = all.slice(-10).reverse().map((r) => `<div><span class="when">${shortDate(r[0])}</span><span>${esc(nm(r[1]))} – ${esc(nm(r[2]))}</span>
      <b>${r[3]}-${r[4]}${r[5] != null ? ` <small class="ht">(${r[5]}-${r[6]})</small>` : ""}</b></div>`).join("");
    return `<div class="h2h-sum">
        <div class="h"><div class="v">${wh}</div><div class="k">${esc(nm(h))}</div></div>
        <div class="d"><div class="v">${dr}</div><div class="k">nuls</div></div>
        <div class="a"><div class="v">${wa}</div><div class="k">${esc(nm(a))}</div></div></div>
      <p class="note">${n} matchs depuis ${since} · ${num(goals / n, 1)} buts par match · +2,5 buts : ${pct(o25 / n)} · les deux marquent : ${pct(btts / n)}${vn ? ` · chez ${esc(nm(h))} : ${vh} V, ${vd} N, ${va} D` : ""}.</p>
      <div class="h2h">${list}</div><p class="note">Entre parenthèses : score à la mi-temps.</p>`;
  }

  function viewAnalyse() {
    const d = D(), teams = [...d.season_teams].sort((a, b) => nm(a).localeCompare(nm(b), "fr"));
    if (!state.home || !d.team_stats[state.home]) state.home = d.upcoming[0]?.home || teams[0];
    if (!state.away || !d.team_stats[state.away] || state.away === state.home) state.away = d.upcoming[0]?.away || teams.find((t) => t !== state.home);
    const opts = (sel) => teams.map((t) => `<option value="${t}" ${t === sel ? "selected" : ""}>${esc(nm(t))}</option>`).join("");
    const h = state.home, a = state.away, p = predict(h, a);
    const sh = d.team_stats[h], sa = d.team_stats[a];

    const mk = (label, v) => `<div class="mk"><span>${label}</span><b>${pct(v)}</b><div class="track"><span style="width:${(v * 100).toFixed(1)}%"></span></div></div>`;
    const N = 6;
    let heat = `<table class="heat"><thead><tr><th class="axis">${esc(D().teams[h].tla)} ↓ / ${esc(D().teams[a].tla)} →</th>`;
    for (let j = 0; j < N; j++) heat += `<th>${j}</th>`;
    heat += `</tr></thead><tbody>`;
    const top = p.top_scores[0].p;
    for (let i = 0; i < N; i++) {
      heat += `<tr><th>${i}</th>`;
      for (let j = 0; j < N; j++) {
        const v = p.matrix[i][j], k = Math.round(Math.min(v / top, 1) * 85);
        const col = i > j ? "--home" : i < j ? "--away" : "--draw";
        heat += `<td style="background:color-mix(in srgb, var(${col}) ${k}%, var(--chip));color:${k > 50 ? "#fff" : "inherit"}">${(v * 100).toFixed(1)}</td>`;
      }
      heat += `</tr>`;
    }
    heat += `</tbody></table>`;

    const fixture = d.upcoming.find((m) => m.home === h && m.away === a);
    const gh = sh.game, ga = sa.game;
    let extra = "";
    if (gh?.corners_for != null && ga?.corners_for != null) {
      const corners = (gh.corners_for + ga.corners_against) / 2 + (ga.corners_for + gh.corners_against) / 2;
      const cards = (gh.yellow_for + ga.yellow_against) / 2 + (ga.yellow_for + gh.yellow_against) / 2;
      extra = `<div class="chips"><span class="chip">Corners attendus <b>≈ ${num(corners, 1)}</b></span><span class="chip">Cartons jaunes attendus <b>≈ ${num(cards, 1)}</b></span></div>
        <p class="note">Estimation à partir des moyennes de la saison des deux équipes.</p>`;
    }
    const gRow = (label, k, d = 1) => gh?.[k] != null && ga?.[k] != null ? `<tr><td class="l">${label}</td><td>${num(gh[k], d)}</td><td>${num(ga[k], d)}</td></tr>` : "";

    return `<div class="section-head"><h2>Analyse match</h2><p class="sub">Choisissez deux équipes : le calcul se fait instantanément</p></div>
      <div class="pickers"><label for="sel-home">Domicile<select id="sel-home">${opts(h)}</select></label>
        <button class="swap" id="swap" aria-label="Inverser domicile et extérieur" title="Inverser">⇄</button>
        <label for="sel-away">Extérieur<select id="sel-away">${opts(a)}</select></label></div>
      <section class="panel">
        <div class="big-probs"><div class="h"><div class="v">${pct(p.p_home)}</div><div class="k">${esc(nm(h))}</div></div>
          <div class="d"><div class="v">${pct(p.p_draw)}</div><div class="k">Nul</div></div>
          <div class="a"><div class="v">${pct(p.p_away)}</div><div class="k">${esc(nm(a))}</div></div></div>
        ${bar(p)}
        ${fixture?.market ? marketLine(p, fixture.market, h, a) : ""}
        <div class="chips"><span class="chip pick">${esc(pickLabel(p, h, a))}</span>
          <span class="chip">Score probable <b>${likelyScore(p).score}</b></span>
          <span class="chip">Buts attendus <b>${num(p.xg_home)} – ${num(p.xg_away)}</b></span>
          <span class="chip">Cote juste 1/N/2 <b>${num(1 / p.p_home)} · ${num(1 / p.p_draw)} · ${num(1 / p.p_away)}</b></span></div>
      </section>
      <div class="grid2">
        <section class="panel"><h3>Marchés</h3><div class="markets">
          ${mk("Plus de 1,5 but", p.over15)}${mk("Plus de 2,5 buts", p.over25)}${mk("Plus de 3,5 buts", p.over35)}
          ${mk("Les deux équipes marquent", p.btts)}${mk(`${esc(nm(h))} ne prend pas de but`, p.home_clean_sheet)}${mk(`${esc(nm(a))} ne prend pas de but`, p.away_clean_sheet)}</div>${extra}</section>
        <section class="panel"><h3>Scores les plus probables</h3>
          <div class="outcome-scores">
            <div><span class="k">Si ${esc(nm(h))} gagne</span><b>${p.best_by_outcome.home?.score ?? "–"}</b></div>
            <div><span class="k">Si match nul</span><b>${p.best_by_outcome.draw?.score ?? "–"}</b></div>
            <div><span class="k">Si ${esc(nm(a))} gagne</span><b>${p.best_by_outcome.away?.score ?? "–"}</b></div></div>
          <div class="markets">${p.top_scores.map((s) => mk(`${esc(nm(h))} ${s.score} ${esc(nm(a))}`, s.p)).join("")}</div>
          <p class="note">Un score exact pris seul est toujours peu probable (rarement plus de 15 %). Le 1-1 ressort souvent en tête parce qu'un nul se joue sur 3 scores (0-0, 1-1, 2-2), alors qu'une victoire se répartit sur beaucoup de scores (1-0, 2-0, 2-1, 3-1…). Pour savoir qui gagne, fiez-vous aux pourcentages 1 / N / 2.</p></section>
      </div>
      <section class="panel"><div class="section-head"><h3>Probabilité de chaque score (%)</h3><span class="sub">lignes : ${esc(nm(h))} · colonnes : ${esc(nm(a))}</span></div>
        <div style="overflow-x:auto">${heat}</div></section>
      <div class="grid2">
        <section class="panel"><h3>Comparaison</h3><div class="scroll" style="border:0"><table class="cmp"><thead><tr><th class="l"></th><th>${esc(D().teams[h].tla)}</th><th>${esc(D().teams[a].tla)}</th></tr></thead><tbody>
          <tr><td class="l">Classement puissance</td><td>${sh.rank_elo}<sup>e</sup></td><td>${sa.rank_elo}<sup>e</sup></td></tr>
          <tr><td class="l">Indice d'attaque</td><td>${Math.round(sh.att * 100)}</td><td>${Math.round(sa.att * 100)}</td></tr>
          <tr><td class="l">Indice de défense</td><td>${Math.round(100 / sh.def)}</td><td>${Math.round(100 / sa.def)}</td></tr>
          <tr><td class="l">Pts/match (dom. / ext.)</td><td>${num(sh.home.ppg)}</td><td>${num(sa.away.ppg)}</td></tr>
          <tr><td class="l">Buts marqués/match</td><td>${num(sh.home.gf_avg)}</td><td>${num(sa.away.gf_avg)}</td></tr>
          <tr><td class="l">Buts encaissés/match</td><td>${num(sh.home.ga_avg)}</td><td>${num(sa.away.ga_avg)}</td></tr>
          ${gRow("xG pour / match", "xg_for", 2)}${gRow("xG contre / match", "xg_against", 2)}
          ${gRow("Tirs cadrés / match", "sot_for")}${gRow("Corners / match", "corners_for")}${gRow("Cartons jaunes / match", "yellow_for", 2)}
        </tbody></table></div>
        <div class="formlist"><div class="eyebrow">Forme (5 derniers matchs)</div>
          <div><span>${esc(nm(h))}</span><span></span>${formChips(sh.form)}</div>
          <div><span>${esc(nm(a))}</span><span></span>${formChips(sa.form)}</div></div><p class="note">Points et buts : stats « domicile » pour ${esc(nm(h))}, « extérieur » pour ${esc(nm(a))}. Stats de jeu : toute la saison.</p></section>
        <section class="panel"><h3>Face-à-face</h3>${h2hBlock(h, a)}</section>
      </div>`;
  }

  function bookBlock(b) {
    const rows = [];
    if (b.bookmakers) rows.push(["Saison en cours", b.bookmakers]);
    if (b.previous?.bookmakers) rows.push([`Saison ${b.previous.season}`, b.previous.bookmakers]);
    if (!rows.length) return "";
    const tr = rows.map(([lab, k]) => `<tr><td class="l">${lab}<br><small class="muted">${k.n} matchs</small></td>
      <td><b>${pct(k.model_accuracy_1x2)}</b><br><small class="muted">Brier ${num(k.model_brier, 3)}</small></td>
      <td><b>${pct(k.accuracy_1x2)}</b><br><small class="muted">Brier ${num(k.brier, 3)}</small></td></tr>`).join("");
    return `<section class="panel"><h3>Face aux bookmakers</h3>
      <div class="scroll" style="border:0"><table><thead><tr><th class="l">Période</th><th>Modèle</th><th>Bookmakers</th></tr></thead><tbody>${tr}</tbody></table></div>
      <p class="note">Les bookmakers sont la référence la plus difficile à battre : leurs cotes intègrent les blessures, les compositions et l'argent des parieurs. Un modèle proche d'eux est déjà un bon modèle. « Modèle » et « Bookmakers » : part des résultats 1N2 bien prédits sur les mêmes matchs.</p></section>`;
  }

  function viewFiabilite() {
    const b = D().backtest;
    if (!b || !b.n) return `<h2>Fiabilité</h2><p class="empty">Pas encore assez de matchs joués pour mesurer la fiabilité (à partir de la 6<sup>e</sup> journée).</p>`;
    const better = b.brier < b.brier_baseline;
    const W = 320, H = 240, P = 34;
    const x = (v) => P + v * (W - P - 10), y = (v) => H - P - v * (H - P - 10);
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Calibration : probabilité annoncée contre fréquence observée">`;
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      svg += `<line x1="${x(0)}" x2="${x(1)}" y1="${y(t)}" y2="${y(t)}" stroke="var(--line)" stroke-width="1"/>`;
      svg += `<text x="${P - 6}" y="${y(t) + 4}" text-anchor="end">${t * 100}%</text><text x="${x(t)}" y="${H - P + 16}" text-anchor="middle">${t * 100}%</text>`;
    }
    svg += `<line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--muted)" stroke-dasharray="4 4" stroke-width="1.2"/>`;
    const pts = b.calibration.filter((c) => c.n >= 5);
    svg += `<polyline fill="none" stroke="var(--accent)" stroke-width="2" points="${pts.map((c) => `${x(c.predicted).toFixed(1)},${y(c.observed).toFixed(1)}`).join(" ")}"/>`;
    for (const c of pts) svg += `<circle cx="${x(c.predicted).toFixed(1)}" cy="${y(c.observed).toFixed(1)}" r="${(3 + Math.sqrt(c.n) / 2).toFixed(1)}" fill="var(--accent)" stroke="var(--surface)" stroke-width="1.5"><title>Annoncé ${pct(c.predicted)} · observé ${pct(c.observed)} · ${c.n} cas</title></circle>`;
    svg += `<text x="${x(0.5)}" y="${H - 2}" text-anchor="middle">probabilité annoncée</text></svg>`;

    const rows = b.recent.map((r) => {
      const ps = [r.p_home, r.p_draw, r.p_away], i = ps.indexOf(Math.max(...ps));
      const lab = [`1 · ${nm(r.home)}`, "N", `2 · ${nm(r.away)}`][i];
      return `<tr><td class="l">${shortDate(r.date)}</td><td class="l">${esc(nm(r.home))} – ${esc(nm(r.away))}</td><td class="l">${esc(lab)} (${pct(ps[i])})</td><td>${r.score}</td><td class="${r.hit ? "ok" : "ko"}">${r.hit ? "✓" : "✗"}</td></tr>`;
    }).join("");

    return `<div class="section-head"><h2>Fiabilité du modèle</h2><p class="sub">Test sur ${b.n} matchs de la saison, chaque prédiction calculée uniquement avec les matchs déjà joués à cette date</p></div>
      <div class="trends">
        <div class="trend"><div class="v">${pct(b.accuracy_1x2)}</div><div class="k">résultat 1N2 bien prédit</div></div>
        <div class="trend"><div class="v">${pct(b.accuracy_over25)}</div><div class="k">+/− 2,5 buts bien prédit</div></div>
        <div class="trend"><div class="v">${pct(b.accuracy_btts)}</div><div class="k">« les deux marquent » bien prédit</div></div>
        <div class="trend"><div class="v">${num(b.brier, 3)}</div><div class="k">score de Brier (réf. ${num(b.brier_baseline, 3)})</div></div></div>
      <p class="note">Repère : les meilleurs modèles publics trouvent le bon résultat 1N2 dans environ 50 à 55 % des cas. Le score de Brier mesure l'erreur des probabilités (plus bas = mieux) ; la référence utilise seulement les fréquences moyennes du championnat. Ici le modèle est ${better ? "meilleur" : "moins bon"} que la référence.</p>
      ${bookBlock(b)}
      <div class="grid2">
        <section class="panel calib"><h3>Les probabilités sont-elles justes ?</h3>${svg}
          <p class="note">Quand le modèle annonce 60 %, l'événement devrait arriver environ 6 fois sur 10 : plus les points suivent la diagonale, mieux c'est.</p></section>
        <section class="panel"><h3>Dernières prédictions</h3><div class="scroll recent" style="border:0;max-height:420px;overflow:auto"><table>
          <thead><tr><th class="l">Date</th><th class="l">Match</th><th class="l">Favori</th><th>Score</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></section>
      </div>`;
  }

  // ------------------------------------------------------------------ rendu et navigation
  const renderers = { matchs: viewMatchs, classement: viewClassement, equipes: viewEquipes, analyse: viewAnalyse, fiabilite: viewFiabilite };

  function render() {
    const d = D();
    document.getElementById("season").textContent = `${d.name} ${d.season}`;
    document.getElementById("demo").hidden = !d.demo;
    document.getElementById("updated").textContent = `Données mises à jour le ${fmtFull.format(new Date(d.updated_at))}.`;
    document.querySelectorAll("#leagues button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.slug === state.slug)));
    document.querySelectorAll("#views a").forEach((a) => {
      a.classList.toggle("on", a.dataset.view === state.view);
      a.href = `#${state.slug}-${a.dataset.view}`;
    });
    app.innerHTML = renderers[state.view]();
  }

  async function load(slug) {
    if (!state.data[slug]) {
      const r = await fetch(`data/${slug}.json`, { cache: "no-cache" });
      if (!r.ok) throw new Error(`data/${slug}.json introuvable`);
      state.data[slug] = await r.json();
    }
  }

  async function go(slug, view, { push = true } = {}) {
    if (slug !== state.slug) { state.team = state.home = state.away = null; }
    state.slug = slug; state.view = view;
    store.set("foot.league", slug);
    if (push && location.hash !== `#${slug}-${view}`) history.replaceState(null, "", `#${slug}-${view}`);
    try { await load(slug); render(); } catch (e) { app.innerHTML = `<p class="empty">Impossible de charger les données : ${esc(e.message)}.</p>`; }
    window.scrollTo({ top: 0 });
  }

  function parseHash() {
    const h = location.hash.slice(1);
    const view = VIEWS.find((v) => h === v || h.endsWith("-" + v));
    const slug = view && h !== view ? h.slice(0, -(view.length + 1)) : null;
    return { view, slug: state.meta.leagues.some((l) => l.slug === slug) ? slug : null };
  }

  // Délégation d'événements
  document.addEventListener("click", (e) => {
    const lg = e.target.closest("#leagues button");
    if (lg) return go(lg.dataset.slug, state.view);
    const v = e.target.closest("#views a");
    if (v) { e.preventDefault(); return go(state.slug, v.dataset.view); }
    const m = e.target.closest("[data-home][data-away]");
    if (m) { state.home = m.dataset.home; state.away = m.dataset.away; return go(state.slug, "analyse"); }
    const t = e.target.closest("[data-team]");
    if (t) { state.team = t.dataset.team; if (state.view !== "equipes") return go(state.slug, "equipes"); render();
      if (window.innerWidth < 820) document.querySelector(".team-layout .panel")?.scrollIntoView({ block: "start" });
      return; }
    if (e.target.closest("#swap")) { [state.home, state.away] = [state.away, state.home]; render(); }
  });
  document.addEventListener("change", (e) => {
    if (e.target.id === "sel-home") state.home = e.target.value;
    else if (e.target.id === "sel-away") state.away = e.target.value;
    else return;
    if (state.home === state.away) state.away = D().season_teams.find((t) => t !== state.home);
    render();
  });
  window.addEventListener("hashchange", () => {
    const { view, slug } = parseHash();
    if (view && (view !== state.view || (slug && slug !== state.slug))) go(slug || state.slug, view, { push: false });
  });

  (async function init() {
    try {
      const r = await fetch("data/meta.json", { cache: "no-cache" });
      state.meta = await r.json();
    } catch {
      app.innerHTML = `<p class="empty">Aucune donnée pour l'instant. Lancez la mise à jour (voir le README).</p>`;
      return;
    }
    const L = state.meta.leagues;
    document.getElementById("leagues").innerHTML = L.map((l) =>
      `<button role="tab" data-slug="${l.slug}" aria-selected="false">${esc(l.name)}</button>`).join("");
    const { view, slug } = parseHash();
    const saved = store.get("foot.league");
    const start = slug || (L.some((l) => l.slug === saved) ? saved : L[0].slug);
    go(start, view || "matchs");
  })();
})();
