// site/scripts/vote.js
// Depends on site/scripts/data.js (fetchData) — include it first.
const PICKS = ["pick_1", "pick_2", "pick_3"];
const DEVICE_KEY = "diod-device";
const VOTED_KEY = "diod-voted";

// A random id per browser, sent with the ballot. The tally keeps the first
// valid ballot per id, so each device votes once. If storage is blocked the
// id still exists for this page load; the tally simply cannot link reloads.
function deviceId() {
  let id = null;
  try { id = localStorage.getItem(DEVICE_KEY); } catch {}
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID()
      : Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
    try { localStorage.setItem(DEVICE_KEY, id); } catch {}
  }
  return id;
}

function alreadyVoted() {
  try { return localStorage.getItem(VOTED_KEY) === "1"; } catch { return false; }
}

function buildOptions(select, submissions) {
  select.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Choose a project";
  select.appendChild(placeholder);

  submissions.forEach((s) => {
    const option = document.createElement("option");
    option.value = s.id;
    option.textContent = `${s.project_title} — ${s.team_name}`;
    select.appendChild(option);
  });
}

async function setupBallot() {
  const form = document.getElementById("ballot-form");
  const error = document.getElementById("ballot-error");
  if (!form) return;

  if (alreadyVoted()) {
    form.hidden = true;
    error.textContent = "You have already voted on this device. Thank you!";
    error.hidden = false;
    return;
  }

  let submissions = [];
  try {
    submissions = await fetchData("submissions.json");
    // An empty list (e.g. an early deploy-time snapshot) would build three
    // dropdowns with nothing to pick; say so instead.
    if (!Array.isArray(submissions) || submissions.length === 0) throw new Error("no projects");
  } catch {
    error.textContent = "The project list is not available yet. Try again once the showcase is published.";
    error.hidden = false;
    return;
  }

  form.elements.device.value = deviceId();
  PICKS.forEach((name) => {
    buildOptions(form.elements[name], submissions);
  });

  form.addEventListener("submit", (event) => {
    const chosen = PICKS.map((name) => form.elements[name].value);
    if (new Set(chosen).size !== PICKS.length) {
      event.preventDefault();
      error.textContent = "Pick three different projects.";
      error.hidden = false;
      return;
    }
    error.hidden = true;
    try { localStorage.setItem(VOTED_KEY, "1"); } catch {}
  });
}

document.addEventListener("DOMContentLoaded", setupBallot);
