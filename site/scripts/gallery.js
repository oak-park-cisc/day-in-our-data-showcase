// site/scripts/gallery.js
async function renderGallery() {
  const mount = document.getElementById("gallery");
  if (!mount) return;

  let submissions = [];
  try {
    const response = await fetch("/data/submissions.json", { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    submissions = await response.json();
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

  mount.innerHTML = submissions
    .map((s) => {
      const links = [
        s.repo_url && `<a href="${s.repo_url}">Code</a>`,
        s.demo_url && `<a href="${s.demo_url}">Demo</a>`,
        s.large_file_url && `<a href="${s.large_file_url}">Files</a>`,
      ]
        .filter(Boolean)
        .join(" ");
      const art = (s.artifacts || [])
        .map((a) => `<a href="${a.url}">${a.filename}</a>`)
        .join(" ");
      return `
        <article class="pane">
          <h3>${s.project_title}</h3>
          <p class="pane__team">${s.team_name}</p>
          <p>${s.description}</p>
          <p class="pane__solves"><strong>Solves for:</strong> ${s.solves_for}</p>
          <p class="pane__links">${links} ${art}</p>
        </article>`;
    })
    .join("");
}

document.addEventListener("DOMContentLoaded", renderGallery);
