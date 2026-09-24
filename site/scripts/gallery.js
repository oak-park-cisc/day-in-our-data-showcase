// site/scripts/gallery.js
// Depends on site/scripts/escape.js (escapeHtml, safeUrl) and data.js (fetchData) — include both first.
async function renderGallery() {
  const mount = document.getElementById("gallery");
  if (!mount) return;

  let submissions = [];
  try {
    submissions = await fetchData("submissions.json");
  } catch {
    mount.innerHTML =
      '<p class="gallery__empty">The showcase opens once the first team enters a project.</p>';
    return;
  }

  if (!submissions.length) {
    mount.innerHTML =
      '<p class="gallery__empty">No projects yet. Yours can be the first.</p>';
    return;
  }

  function link(url, label) {
    const safe = safeUrl(url);
    if (!safe) return "";
    return `<a href="${escapeHtml(safe)}">${escapeHtml(label)}</a>`;
  }

  mount.innerHTML = submissions
    .map((s) => {
      const links = [
        s.repo_url && link(s.repo_url, "Code"),
        s.demo_url && link(s.demo_url, "Demo"),
        s.large_file_url && link(s.large_file_url, "Files"),
      ]
        .filter(Boolean)
        .join(" ");
      const art = (s.artifacts || [])
        .map((a) => link(a.url, a.filename))
        .filter(Boolean)
        .join(" ");
      return `
        <article class="pane">
          <h3>${escapeHtml(s.project_title)}</h3>
          <p class="pane__team">${escapeHtml(s.team_name)}</p>
          <p>${escapeHtml(s.description)}</p>
          <p class="pane__solves"><strong>Solves for:</strong> ${escapeHtml(s.solves_for)}</p>
          <p class="pane__links">${links} ${art}</p>
        </article>`;
    })
    .join("");
}

document.addEventListener("DOMContentLoaded", renderGallery);
