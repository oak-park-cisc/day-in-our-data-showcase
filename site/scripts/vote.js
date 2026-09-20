// site/scripts/vote.js
const PICKS = ["pick_1", "pick_2", "pick_3"];

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

  const options =
    '<option value="">Choose a project</option>' +
    submissions
      .map((s) => `<option value="${s.id}">${s.project_title} — ${s.team_name}</option>`)
      .join("");
  PICKS.forEach((name) => {
    form.elements[name].innerHTML = options;
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
