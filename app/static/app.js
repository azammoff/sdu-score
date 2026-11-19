"use strict";
/* SDU Score — a small single-page site on top of the REST API (hash routing, no build step). */

const view = document.getElementById("view");
const cache = {};

// ------------------------------------------------------------------ helpers
async function api(path) {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    let msg = `Ошибка ${res.status}`;
    try { msg = (await res.json()).error.message; } catch (_) { /* keep default */ }
    throw new Error(msg);
  }
  return res.json();
}
async function cached(path) {
  if (!cache[path]) cache[path] = api(path);
  return cache[path];
}
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const html = (strings, ...values) => strings.reduce((out, s, i) => out + s + (i < values.length ? values[i] : ""), "");

function hue(text) {
  let h = 0;
  for (const ch of String(text)) h = (h * 31 + ch.codePointAt(0)) % 360;
  return h;
}
function badge(name, size = "") {
  const words = String(name).replace(/^fc\s+/i, "").split(/[\s.\-]+/).filter(Boolean);
  const initials = (words.length > 1 ? words[0][0] + words[1][0] : (words[0] || "?").slice(0, 2));
  return `<span class="badge ${size}" style="background:hsl(${hue(name)} 55% 38%)">${esc(initials)}</span>`;
}
const teamLink = (id, name) => `<a href="#/team/${id}" class="team-cell">${badge(name)}<span>${esc(name)}</span></a>`;
const playerLink = (id, name) => `<a href="#/player/${id}">${esc(name)}</a>`;

const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
function fmtDay(iso) {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}
const fmtShort = (iso) => { const d = new Date(iso); return `${d.getDate()} ${MONTHS[d.getMonth()]} ’${String(d.getFullYear()).slice(2)}`; };

const STAGE_RU = {
  "Qualification": "Квалификация", "Opening match": "Матч открытия", "Super Cup": "Суперкубок",
  "Round of 16": "1/8 финала", "Quarter-final": "1/4 финала", "Semi-final": "1/2 финала",
  "3rd place": "Матч за 3 место", "Final": "Финал", "Play-off": "Плей-офф",
};
function stageName(stage) {
  if (!stage) return "Матчи";
  if (STAGE_RU[stage]) return STAGE_RU[stage];
  const tour = /^Tour (\d+)/.exec(stage);
  return tour ? `${tour[1]} тур` : stage;
}
function matchLabel(m) {
  const parts = [stageName(m.stage)];
  if (m.group_name) parts.push(`группа ${m.group_name}`);
  if (m.leg) parts.push(`${m.leg}-й матч`);
  return parts.join(" · ");
}
function winner(m) {
  if (m.status !== "finished") return null;
  if (m.home_score !== m.away_score) return m.home_score > m.away_score ? "home" : "away";
  if (m.home_penalties != null && m.away_penalties != null && m.home_penalties !== m.away_penalties)
    return m.home_penalties > m.away_penalties ? "home" : "away";
  return "draw";
}
const STATUS_RU = { scheduled: "Запланирован", live: "LIVE", finished: "Завершён", cancelled: "Отменён",
  upcoming: "Скоро", ongoing: "Идёт" };

function card(title, body, extra = "") {
  return `<section class="card"><div class="card-head">${title}${extra ? `<small>${extra}</small>` : ""}</div>${body}</section>`;
}
const empty = (text) => `<div class="empty">${esc(text)}</div>`;
const loading = () => { view.innerHTML = `<div class="muted pad">Загрузка…</div>`; };

// ------------------------------------------------------------------ match list
function matchRow(m, { showDate = false } = {}) {
  const w = winner(m);
  const cls = (side) => (w === side ? "win" : w && w !== "draw" ? "lose" : "");
  const pens = m.home_penalties != null ? `<div class="pens">пен. ${m.home_penalties}:${m.away_penalties}</div>` : "";
  const score = m.status === "scheduled" ? ["–", "–"] : [m.home_score, m.away_score];
  const meta = showDate ? fmtShort(m.kickoff) : (m.status === "finished" ? "FT" : STATUS_RU[m.status]);
  return html`<a class="match-row" href="#/match/${m.id}">
    <div class="meta">${esc(meta)}<br>${m.status === "live" ? '<span class="pill live">LIVE</span>' : ""}</div>
    <div class="teams-col">
      <div class="t ${cls("home")}">${badge(m.home_team_name)}<span>${esc(m.home_team_name)}</span></div>
      <div class="t ${cls("away")}">${badge(m.away_team_name)}<span>${esc(m.away_team_name)}</span></div>
    </div>
    <div class="score-col"><div class="${cls("home")}">${score[0]}</div><div class="${cls("away")}">${score[1]}</div>${pens}</div>
  </a>`;
}
function matchesByDay(matches) {
  if (!matches.length) return empty("Матчей нет");
  let out = "", day = "";
  for (const m of matches) {
    const d = fmtDay(m.kickoff);
    if (d !== day) { out += `<div class="day">${d} · ${esc(matchLabel(m))}</div>`; day = d; }
    out += matchRow(m);
  }
  return out;
}

// ------------------------------------------------------------------ standings
function computeForm(matches) {
  const form = {};
  const sorted = [...matches].filter((m) => m.status === "finished").sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  for (const m of sorted) {
    const w = winner(m);
    const r = (side) => (w === "draw" ? "D" : w === side ? "W" : "L");
    (form[m.home_team_id] ||= []).push({ r: r("home"), id: m.id });
    (form[m.away_team_id] ||= []).push({ r: r("away"), id: m.id });
  }
  return form;
}
function standingsTable(rows, form = {}, highlight = 1) {
  if (!rows.length) return empty("Таблица пока пуста");
  const body = rows.map((r) => html`<tr>
      <td><span class="pos ${r.position <= highlight ? "top" : ""}">${r.position}</span></td>
      <td class="l">${teamLink(r.team_id, r.team_name)}</td>
      <td>${r.played}</td><td>${r.wins}</td><td>${r.draws}</td><td>${r.losses}</td>
      <td>${r.goals_for}:${r.goals_against}</td><td>${r.goal_difference > 0 ? "+" : ""}${r.goal_difference}</td>
      <td><b>${r.points}</b></td>
      <td class="l"><span class="form">${(form[r.team_id] || []).slice(-5).map((f) => `<a href="#/match/${f.id}"><i class="${f.r}">${{ W: "В", D: "Н", L: "П" }[f.r]}</i></a>`).join("")}</span></td>
    </tr>`).join("");
  return `<div class="table-wrap"><table>
    <thead><tr><th>#</th><th class="l">Команда</th><th>И</th><th>В</th><th>Н</th><th>П</th><th>Голы</th><th>±</th><th>О</th><th class="l">Форма</th></tr></thead>
    <tbody>${body}</tbody></table></div>`;
}
function scorersList(rows, { showTeam = true } = {}) {
  if (!rows.length) return empty("Голов пока нет");
  return rows.map((r) => html`<div class="list-row">
      <span class="pos ${r.rank <= 3 ? "top" : ""}">${r.rank}</span>
      ${badge(r.team_name)}
      <div class="grow">${playerLink(r.player_id, r.player_name)}${showTeam ? `<div class="muted">${esc(r.team_name)}</div>` : ""}</div>
      <span class="muted" title="Ассисты">${r.assists} A</span>
      <span class="num" title="Голы">${r.goals} ⚽</span>
    </div>`).join("");
}

// ------------------------------------------------------------------ pages
async function pageHome() {
  const [latest, scorers, tournaments] = await Promise.all([
    api("/matches?newest_first=true&limit=40"),
    api("/stats/top-scorers?limit=10"),
    cached("/tournaments"),
  ]);
  const finals = await api("/matches?stage=Final&limit=100");
  const leagues = tournaments.filter((t) => t.name.includes("League"));
  const leagueTables = await Promise.all(leagues.map((t) => api(`/tournaments/${t.id}/standings?stage_prefix=Tour`).catch(() => [])));
  const champions = [];
  for (const t of tournaments) {
    let champ = null;
    const final = finals.filter((m) => m.tournament_id === t.id).pop();
    if (final) { const w = winner(final); if (w && w !== "draw") champ = w === "home" ? [final.home_team_id, final.home_team_name] : [final.away_team_id, final.away_team_name]; }
    const li = leagues.indexOf(t);
    if (!champ && li >= 0 && leagueTables[li][0]) champ = [leagueTables[li][0].team_id, leagueTables[li][0].team_name];
    if (champ) champions.push({ t, champ });
  }
  const champsHtml = champions.map(({ t, champ }) => html`<div class="list-row">
      <span class="icon">🏆</span>
      <div class="grow"><a href="#/tournament/${t.id}">${esc(short(t))}</a></div>
      ${teamLink(champ[0], champ[1])}
    </div>`).join("");
  view.innerHTML = html`
    <div class="hero">${badge("SDU Score", "lg")}<div><h1>SDU Score</h1>
      <div class="sub">Результаты, таблицы и статистика студенческого футбола SDU · ${tournaments.length} турниров</div></div></div>
    <div class="grid-2">
      <div>${card("Последние матчи", matchesByDay(latest))}</div>
      <div>
        ${card("Бомбардиры за всё время", scorersList(scorers))}
        ${card("Чемпионы", champsHtml || empty("Нет данных"))}
      </div>
    </div>`;
}

function short(t) {
  return `${t.name.includes("Cup") ? "SFC" : t.name.includes("League") ? "SFL" : t.name} ${t.season}`;
}

async function pageTournaments() {
  const tournaments = await cached("/tournaments");
  view.innerHTML = card("Все турниры", tournaments.map((t) => html`<a class="list-row" href="#/tournament/${t.id}">
      ${badge(short(t))}<div class="grow"><b>${esc(t.name)}</b> <span class="muted">${esc(t.season)}</span>
      <div class="muted">${fmtDay(t.start_date)} — ${fmtDay(t.end_date)}</div></div>
      <span class="pill ${t.status === "finished" ? "ok" : ""}">${STATUS_RU[t.status]}</span></a>`).join(""));
}

async function pageTournament(id, tab = "matches") {
  const [t, matches] = await Promise.all([api(`/tournaments/${id}`), api(`/tournaments/${id}/matches`)]);
  const tabs = [["matches", "Матчи"], ["table", "Таблица"], ["scorers", "Бомбардиры"]];
  let body = "";
  if (tab === "matches") {
    const stages = t.stages.length ? t.stages : [null];
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    const current = params.get("stage") || "";
    const chips = `<div class="chips">${[["", "Все"], ...stages.filter(Boolean).map((s) => [s, stageName(s)])]
      .map(([v, l]) => `<button data-stage="${esc(v)}" class="${v === current ? "active" : ""}">${esc(l)}</button>`).join("")}</div>`;
    const shown = matches.filter((m) => !current || m.stage === current).reverse();
    body = card("Матчи", chips + matchesByDay(shown), `${matches.length} матчей`);
  } else if (tab === "table") {
    const hasTours = t.stages.some((s) => s.startsWith("Tour"));
    const parts = [];
    if (hasTours) {
      const rows = await api(`/tournaments/${id}/standings?stage_prefix=Tour`);
      parts.push(card(t.name.includes("Cup") ? "Групповой этап" : "Регулярный чемпионат", standingsTable(rows, computeForm(matches.filter((m) => (m.stage || "").startsWith("Tour"))), 1)));
    }
    if (t.groups.length) {
      const tables = await Promise.all(t.groups.map((g) => api(`/tournaments/${id}/standings?group=${encodeURIComponent(g)}`)));
      t.groups.forEach((g, i) => parts.push(card(`Группа ${esc(g)}`, standingsTable(tables[i], computeForm(matches.filter((m) => m.group_name === g)), 2))));
    }
    if (!parts.length) parts.push(card("Таблица", standingsTable(await api(`/tournaments/${id}/standings`), computeForm(matches))));
    const playoff = matches.filter((m) => ["Round of 16", "Quarter-final", "Semi-final", "3rd place", "Final"].includes(m.stage));
    if (playoff.length) parts.push(card("Плей-офф", matchesByDay(playoff.reverse())));
    body = parts.join("");
  } else {
    body = card("Бомбардиры", scorersList(await api(`/tournaments/${id}/top-scorers?limit=30`)));
  }
  view.innerHTML = html`
    <div class="hero">${badge(short(t), "lg")}<div><h1>${esc(t.name)} ${esc(t.season)}</h1>
      <div class="sub">${fmtDay(t.start_date)} — ${fmtDay(t.end_date)} · ${t.team_count} команд · ${t.match_count} матчей
      · <span class="pill ${t.status === "finished" ? "ok" : ""}">${STATUS_RU[t.status]}</span></div></div></div>
    <div class="tabs">${tabs.map(([k, l]) => `<button data-tab="${k}" class="${k === tab ? "active" : ""}">${l}</button>`).join("")}</div>
    ${body}`;
  view.querySelectorAll("[data-tab]").forEach((b) => b.onclick = () => { location.hash = `#/tournament/${id}/${b.dataset.tab}`; });
  view.querySelectorAll("[data-stage]").forEach((b) => b.onclick = () => {
    location.hash = `#/tournament/${id}/matches` + (b.dataset.stage ? `?stage=${encodeURIComponent(b.dataset.stage)}` : "");
  });
  markSidebar(id);
}

async function pageMatch(id) {
  const m = await api(`/matches/${id}`);
  const tournament = (await cached("/tournaments")).find((t) => t.id === m.tournament_id);
  const w = winner(m);
  const events = [...m.events].sort((a, b) => (a.minute ?? 999) - (b.minute ?? 999) || a.id - b.id);
  let h = 0, a = 0, halfShown = false;
  halfShown = !events.some((e) => e.minute && e.minute <= 20);  // no divider if nothing happened before half-time
  const rows = events.map((e) => {
    const playerSide = e.team_id === m.home_team_id ? "home" : "away";
    let icon = "", extra = "";
    if (e.type === "goal" || e.type === "own_goal") {
      const scoringSide = e.type === "goal" ? playerSide : (playerSide === "home" ? "away" : "home");
      scoringSide === "home" ? h++ : a++;
      icon = "⚽";
      extra = `<b>${h}:${a}</b>`;
    } else icon = e.type === "yellow_card" ? '<span class="card-y"></span>' : '<span class="card-r"></span>';
    const og = e.type === "own_goal" ? ' <span class="og">(автогол)</span>' : "";
    const assist = e.assist_player_name ? `<span class="assist">пас: ${playerLink(e.assist_player_id, e.assist_player_name)}</span>` : "";
    const who = `<span class="who">${playerSide === "home" ? `<span>${playerLink(e.player_id, e.player_name)}${og}${assist}</span><span class="icon">${icon}</span>` : `<span class="icon">${icon}</span><span>${playerLink(e.player_id, e.player_name)}${og}${assist}</span>`}</span>`;
    let half = "";
    if (!halfShown && e.minute && e.minute > 20) { half = `<div class="ht">Перерыв</div>`; halfShown = true; }  // 2 × 20 min
    return html`${half}<div class="ev">
      <div class="home">${playerSide === "home" ? who : ""}</div>
      <div class="min">${e.minute ? `${e.minute}'` : "—"}${extra ? `<div>${extra}</div>` : ""}</div>
      <div class="away">${playerSide === "away" ? who : ""}</div></div>`;
  }).join("");
  const h2h = (await api(`/matches?team_id=${m.home_team_id}&limit=1000&newest_first=true`))
    .filter((x) => x.id !== m.id && [x.home_team_id, x.away_team_id].includes(m.away_team_id));
  const pens = m.home_penalties != null ? `<div class="status">Серия пенальти ${m.home_penalties}:${m.away_penalties}</div>` : "";
  view.innerHTML = html`
    <section class="card">
      <div class="card-head"><a href="#/tournament/${m.tournament_id}">${esc(tournament ? `${tournament.name} ${tournament.season}` : "Турнир")}</a>
        <small>${esc(matchLabel(m))} · ${fmtDay(m.kickoff)}</small></div>
      <div class="scoreboard">
        <a class="side" href="#/team/${m.home_team_id}">${badge(m.home_team_name, "xl")}${esc(m.home_team_name)}</a>
        <div><div class="big">${m.status === "scheduled" ? "– : –" : `${m.home_score} : ${m.away_score}`}</div>
          <div class="status">${STATUS_RU[m.status]}${w && w !== "draw" ? "" : ""}</div>${pens}</div>
        <a class="side" href="#/team/${m.away_team_id}">${badge(m.away_team_name, "xl")}${esc(m.away_team_name)}</a>
      </div>
    </section>
    <div class="grid-2">
      <div>${card("События матча", events.length ? `<div class="timeline">${rows}</div>` : empty("Событий нет"))}</div>
      <div>${card("Личные встречи", h2h.length ? h2h.slice(0, 10).map((x) => matchRow(x, { showDate: true })).join("") : empty("Раньше не встречались"))}</div>
    </div>`;
  markSidebar(m.tournament_id);
}

async function pageTeam(id) {
  const [team, stats, matches, scorers, tournaments] = await Promise.all([
    api(`/teams/${id}`), api(`/teams/${id}/stats`), api(`/teams/${id}/matches`),
    api(`/teams/${id}/top-scorers?limit=15`), cached("/tournaments"),
  ]);
  const recent = [...matches].reverse();
  const form = computeForm(matches)[team.id] || [];
  const their = tournaments.filter((t) => team.tournament_ids.includes(t.id));
  view.innerHTML = html`
    <div class="hero">${badge(team.name, "xl")}<div><h1>${esc(team.name)}</h1>
      <div class="sub">${team.faculty ? esc(team.faculty.name) + " · " : ""}${their.length} турниров · ${team.players.length} игроков
      ${form.length ? ` · форма <span class="form">${form.slice(-5).map((f) => `<i class="${f.r}">${{ W: "В", D: "Н", L: "П" }[f.r]}</i>`).join("")}</span>` : ""}</div></div></div>
    ${card("Статистика за всё время", `<div class="stat-grid">
      ${[["Матчи", stats.played], ["Победы", stats.wins], ["Ничьи", stats.draws], ["Поражения", stats.losses],
        ["Забито", stats.goals_for], ["Пропущено", stats.goals_against], ["Сухие", stats.clean_sheets],
        ["Жёлтые", stats.yellow_cards], ["Красные", stats.red_cards]]
        .map(([l, v]) => `<div class="stat"><b>${v}</b><span>${l}</span></div>`).join("")}</div>`)}
    <div class="grid-2">
      <div>${card("Матчи", recent.length ? recent.slice(0, 40).map((m) => matchRow(m, { showDate: true })).join("") : empty("Матчей нет"), `${matches.length}`)}</div>
      <div>
        ${card("Лучшие бомбардиры", scorersList(scorers, { showTeam: false }))}
        ${card("Турниры", their.map((t) => `<a class="list-row" href="#/tournament/${t.id}">${badge(short(t))}<div class="grow">${esc(t.name)} ${esc(t.season)}</div></a>`).join("") || empty("—"))}
      </div>
    </div>`;
}

async function pagePlayer(id) {
  const player = await api(`/players/${id}`);
  const [stats, matches, team] = await Promise.all([
    api(`/players/${id}/stats`), api(`/players/${id}/matches`), api(`/teams/${player.team_id}`),
  ]);
  view.innerHTML = html`
    <div class="hero">${badge(player.full_name, "xl")}<div><h1>${esc(player.full_name)}</h1>
      <div class="sub">${teamLink(team.id, team.name)}${player.position ? ` · ${esc(player.position)}` : ""}${player.jersey_number ? ` · #${player.jersey_number}` : ""}</div>
      ${stats.teams.length > 1 ? `<div class="sub">Также играл за: ${stats.teams.slice(1).map((t) => `<a href="#/team/${t.id}">${esc(t.name)}</a>`).join(", ")}</div>` : ""}</div></div>
    ${card("Статистика", `<div class="stat-grid">
      ${[["Голы", stats.goals], ["Ассисты", stats.assists], ["Гол+пас", stats.goals + stats.assists], ["Матчи с событиями", stats.matches_with_events],
        ["Жёлтые", stats.yellow_cards], ["Красные", stats.red_cards], ["Автоголы", stats.own_goals]]
        .map(([l, v]) => `<div class="stat"><b>${v}</b><span>${l}</span></div>`).join("")}</div>`)}
    ${card("Матчи", matches.length ? matches.map((m) => matchRow(m, { showDate: true })).join("") : empty("Нет матчей"))}`;
}

async function pageTeams() {
  const teams = await cached("/teams");
  view.innerHTML = card("Команды", `<div class="team-grid">${teams.map((t) => `<a href="#/team/${t.id}">${badge(t.name)}<span>${esc(t.name)}</span></a>`).join("")}</div>`, `${teams.length}`);
}

// ------------------------------------------------------------------ sidebar, search, router
async function renderSidebar() {
  const box = document.getElementById("side-tournaments");
  try {
    const tournaments = await cached("/tournaments");
    box.innerHTML = tournaments.map((t) => `<a href="#/tournament/${t.id}" data-tid="${t.id}"><span>${esc(t.name.includes("Cup") ? "SDU Cup" : "SDU League")}</span><span class="year">${esc(t.season)}</span></a>`).join("");
  } catch (e) {
    box.innerHTML = `<div class="muted pad">${esc(e.message)}</div>`;
  }
}
function markSidebar(tid) {
  document.querySelectorAll("#side-tournaments a").forEach((a) => a.classList.toggle("active", a.dataset.tid === String(tid)));
}

const search = document.getElementById("search");
const results = document.getElementById("search-results");
let searchTimer;
search.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = search.value.trim();
  if (q.length < 2) { results.hidden = true; return; }
  searchTimer = setTimeout(async () => {
    const [teams, players] = await Promise.all([
      api(`/teams?search=${encodeURIComponent(q)}`), api(`/players?search=${encodeURIComponent(q)}`),
    ]);
    const teamNames = Object.fromEntries((await cached("/teams")).map((t) => [t.id, t.name]));
    results.innerHTML =
      (teams.length ? `<div class="group">Команды</div>` + teams.slice(0, 6).map((t) => `<a href="#/team/${t.id}">${badge(t.name)}${esc(t.name)}</a>`).join("") : "") +
      (players.length ? `<div class="group">Игроки</div>` + players.slice(0, 10).map((p) => `<a href="#/player/${p.id}">${badge(p.full_name)}<span>${esc(p.full_name)} <span class="muted">· ${esc(teamNames[p.team_id] || "")}</span></span></a>`).join("") : "") ||
      `<div class="group">Ничего не найдено</div>`;
    results.hidden = false;
  }, 250);
});
document.addEventListener("click", (e) => { if (!e.target.closest(".search")) results.hidden = true; });
results.addEventListener("click", () => { results.hidden = true; search.value = ""; });

const routes = [
  [/^#?\/?$/, pageHome],
  [/^#\/tournaments$/, pageTournaments],
  [/^#\/tournament\/(\d+)(?:\/(matches|table|scorers))?/, pageTournament],
  [/^#\/match\/(\d+)$/, pageMatch],
  [/^#\/team\/(\d+)$/, pageTeam],
  [/^#\/teams$/, pageTeams],
  [/^#\/player\/(\d+)$/, pagePlayer],
];
async function router() {
  const hash = location.hash || "#/";
  document.querySelectorAll(".topnav a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === hash));
  for (const [re, page] of routes) {
    const m = re.exec(hash.split("?")[0]);
    if (m) {
      loading();
      try { await page(...m.slice(1).filter((x) => x !== undefined)); }
      catch (e) { view.innerHTML = card("Ошибка", `<div class="empty">${esc(e.message)}</div>`); }
      window.scrollTo(0, 0);
      if (!/tournament|match/.test(hash)) markSidebar(null);
      return;
    }
  }
  view.innerHTML = card("Страница не найдена", empty("Такой страницы нет"));
}
window.addEventListener("hashchange", router);
renderSidebar();
router();
