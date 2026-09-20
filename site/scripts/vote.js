// site/scripts/vote.js
const PICKS = ["pick_1", "pick_2", "pick_3"];

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

  let submissions = [];
  try {
    const response = await fetch("/data/submissions.json", { cache: "no-store" });
    submissions = await response.json();
  } catch {
    error.textContent = "The project list is not available yet. Try again once the showcase is published.";
    error.hidden = false;
    return;
  }

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
  });
}

document.addEventListener("DOMContentLoaded", setupBallot);
