// site/scripts/results.js
// Depends on site/scripts/escape.js (escapeHtml, safeUrl) — include it first.
//
// Two ID namespaces meet on this page: comparison.json keys everything by
// PUBLIC id (sub_001) because that's how residents voted; bracket.json and
// scores.json key everything by ANONYMOUS id (P-01) because the panel judged
// blind. /data/submissions.json is the only place both ids sit on the same
// record, so buildTitleMaps() reads it once and produces two lookup maps —
// one per namespace — that every renderer below uses to show a human title
// instead of a bare id.
//
// Every piece of participant- or model-supplied text (titles, team names,
// the caveat, persona names, reasoning) is routed through escapeHtml()
// before it reaches innerHTML. That data is hostile by default.

async function loadJSON(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(path);
  return response.json();
}

function buildTitleMaps(submissions) {
  const byPublic = {};
  const byAnon = {};
  (submissions || []).forEach((s) => {
    const entry = { title: s.project_title, team: s.team_name };
    if (s.id) byPublic[s.id] = entry;
    if (s.anon_id) byAnon[s.anon_id] = entry;
  });
  return { byPublic, byAnon };
}

function titleOf(map, id) {
  if (!id) return "";
  const entry = map[id];
  return entry && entry.title ? entry.title : id;
}

// ---- comparison ----

function renderAgreement(comparison, byPublic) {
  const rho = comparison.spearman;
  const hasRho = rho !== null && rho !== undefined;
  const headline = hasRho
    ? `Spearman correlation <strong>${rho.toFixed(2)}</strong> across ${escapeHtml(
        String(comparison.n ?? 0)
      )} ballots.`
    : "Not enough variation to measure agreement.";
  const caveat = comparison.caveat
    ? `<p class="agreement__caveat">${escapeHtml(comparison.caveat)}</p>`
    : "";
  document.getElementById("agreement").innerHTML = `
    <p class="agreement${hasRho ? "" : " agreement--empty"}">${headline}</p>
    ${caveat}`;

  const crowdRanking = comparison.crowd_ranking || [];
  const panelRanking = comparison.panel_ranking || [];
  const crowdCounts = comparison.crowd_counts || {};
  const panelMeans = comparison.panel_means || {};
  const rows = crowdRanking
    .map((id, i) => {
      const panelAt = panelRanking[i];
      const count = crowdCounts[id];
      // panelMeans is keyed by the project named in THIS row's "Panel chose"
      // cell (panelAt), not by the crowd's pick (id) — those are two
      // different projects whenever the rankings disagree.
      const mean = panelAt ? panelMeans[panelAt] : undefined;
      return `<tr>
        <td class="rank">${i + 1}</td>
        <td>${escapeHtml(titleOf(byPublic, id))}</td>
        <td>${count === undefined ? "—" : escapeHtml(String(count))}</td>
        <td>${panelAt ? escapeHtml(titleOf(byPublic, panelAt)) : "—"}</td>
        <td>${mean === null || mean === undefined ? "—" : mean.toFixed(2)}</td>
      </tr>`;
    })
    .join("");
  document.getElementById("side-by-side").innerHTML = `
    <caption>Crowd ranking beside the panel's</caption>
    <thead><tr><th>#</th><th>Residents chose</th><th>Votes</th><th>Panel chose</th><th>Panel mean</th></tr></thead>
    <tbody>${rows}</tbody>`;

  const perPersona = Object.entries(comparison.per_persona || {})
    .sort((a, b) => (b[1] ?? -2) - (a[1] ?? -2))
    .map(([persona, value]) => {
      const label = escapeHtml(String(persona).replace(/-/g, " "));
      const display = value === null || value === undefined ? "—" : value.toFixed(2);
      return `<tr><td>${label}</td><td>${display}</td></tr>`;
    })
    .join("");
  document.getElementById("per-persona").innerHTML = `
    <caption>Which judge best predicted the crowd</caption>
    <thead><tr><th>Persona</th><th>Agreement with residents</th></tr></thead>
    <tbody>${perPersona || '<tr><td colspan="2">No persona data yet.</td></tr>'}</tbody>`;
}

// ---- bracket (art glass) ----

function entrantMarkup(anonId, byAnon, seeds, cls) {
  if (!anonId) return "";
  const entry = byAnon[anonId] || {};
  const title = escapeHtml(entry.title || anonId);
  const team = entry.team ? `<span class="entrant__team">${escapeHtml(entry.team)}</span>` : "";
  const seed = seeds && seeds[anonId] != null
    ? `<span class="entrant__meta">Seed ${escapeHtml(String(seeds[anonId]))}</span>`
    : "";
  return `
    <div class="entrant ${cls}">
      <span class="entrant__title">${title}</span>
      ${team}
      ${seed}
    </div>`;
}

function voteMarkup(vote, reasoning, byAnon) {
  const persona = escapeHtml(String(vote.persona || "").replace(/-/g, " "));
  const pick = escapeHtml(titleOf(byAnon, vote.winner));
  const swapText = vote.swap_confirmed
    ? "Held after the position swap."
    : "Did not hold after the position swap.";
  const text = reasoning && vote.persona in reasoning ? reasoning[vote.persona] : "";
  const reasoningHtml = text
    ? `<p class="vote__reasoning">${escapeHtml(text)}</p>`
    : "";
  return `<li>
    <p class="vote__persona">${persona}</p>
    <p class="vote__pick">Picked ${pick}<span class="vote__swap">${swapText}</span></p>
    ${reasoningHtml}
  </li>`;
}

function renderMatchup(matchup, roundIndex, matchupIndex, byAnon, seeds) {
  const isBye = matchup.bye || !matchup.b;
  if (isBye) {
    return `<li class="matchup">
      <div class="pane pane--bye">
        ${entrantMarkup(matchup.a, byAnon, seeds, "pane--advancing")}
      </div>
      <p class="matchup__note">Bye</p>
    </li>`;
  }

  const detailsId = `details-r${roundIndex + 1}-m${matchupIndex + 1}`;
  const aCls = matchup.winner === matchup.a ? "pane--advancing" : "pane--out";
  const bCls = matchup.winner === matchup.b ? "pane--advancing" : "pane--out";
  const votes = matchup.votes || [];
  const reasoning = matchup.reasoning || {};
  const votesHtml = votes.length
    ? votes.map((v) => voteMarkup(v, reasoning, byAnon)).join("")
    : "<li>No ballots recorded for this matchup.</li>";

  return `<li class="matchup">
    <button type="button" class="pane" aria-expanded="false" aria-controls="${detailsId}">
      ${entrantMarkup(matchup.a, byAnon, seeds, aCls)}
      ${entrantMarkup(matchup.b, byAnon, seeds, bCls)}
    </button>
    <div class="details" id="${detailsId}" hidden>
      <ul class="votes">${votesHtml}</ul>
    </div>
  </li>`;
}

function renderRound(round, roundIndex, byAnon, seeds) {
  const matchups = (round || [])
    .map((m, mi) => renderMatchup(m, roundIndex, mi, byAnon, seeds))
    .join("");
  return `<div class="round">
    <p class="round__label">Round ${roundIndex + 1}</p>
    <ul class="round__matchups">${matchups}</ul>
  </div>`;
}

function renderBracket(bracket, byAnon) {
  const mount = document.getElementById("glass");

  if (bracket.mode === "ranked_list") {
    const ranking = bracket.ranking || [];
    if (!ranking.length) {
      mount.innerHTML = `<p class="bracket__empty">No panel ranking yet.</p>`;
      return;
    }
    const items = ranking
      .map((id) => `<li>${escapeHtml(titleOf(byAnon, id))}</li>`)
      .join("");
    mount.innerHTML = `
      <p class="bracket__note">Fewer than four projects were entered, so the panel published a ranking rather than a bracket.</p>
      <ol class="ranked-list">${items}</ol>`;
    return;
  }

  const rounds = bracket.rounds || [];
  if (!rounds.length && !bracket.champion) {
    mount.innerHTML = `<p class="bracket__empty">No bracket yet.</p>`;
    return;
  }

  const seeds = bracket.seeds || {};
  const roundsHtml = rounds.map((round, ri) => renderRound(round, ri, byAnon, seeds)).join("");
  const championHtml = bracket.champion
    ? `<div class="round round--champion">
        <p class="round__label">Champion</p>
        <div class="pane pane--champion">
          ${entrantMarkup(bracket.champion, byAnon, seeds, "")}
        </div>
      </div>`
    : "";

  mount.innerHTML = `<div class="rounds">${roundsHtml}${championHtml}</div>`;
  attachToggles(mount);
}

// Pure toggle: flips the button/details pair's expanded state. Kept separate
// from DOM wiring so it can be exercised directly with plain mock objects.
function toggleDetails(button, details) {
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  details.hidden = expanded;
}

function attachToggles(mount) {
  mount.querySelectorAll(".pane[aria-controls]").forEach((button) => {
    button.addEventListener("click", () => {
      const details = document.getElementById(button.getAttribute("aria-controls"));
      if (details) toggleDetails(button, details);
    });
  });
}

// ---- init ----

async function init() {
  let submissions;
  let bracket;
  let comparison;
  try {
    [submissions, bracket, comparison] = await Promise.all([
      loadJSON("/data/submissions.json"),
      loadJSON("/data/results/bracket.json"),
      loadJSON("/data/results/comparison.json"),
    ]);
  } catch {
    const message = '<p class="bracket__empty">Results are not available yet.</p>';
    document.getElementById("agreement").innerHTML = message;
    document.getElementById("glass").innerHTML = message;
    return;
  }

  const { byPublic, byAnon } = buildTitleMaps(submissions);
  renderAgreement(comparison, byPublic);
  renderBracket(bracket, byAnon);
}

document.addEventListener("DOMContentLoaded", init);
