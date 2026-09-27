// site/scripts/copy.js: "Copy" buttons on guide code blocks.
// Progressive enhancement: buttons ship hidden and appear only where the
// Clipboard API exists, so a page without JS just shows selectable code.
(function () {
  if (!navigator.clipboard) return;
  document.querySelectorAll(".code").forEach(function (figure) {
    var button = figure.querySelector(".copy");
    var code = figure.querySelector("pre code");
    if (!button || !code) return;
    button.hidden = false;
    button.setAttribute("aria-label", "Copy code to clipboard");
    button.addEventListener("click", function () {
      navigator.clipboard.writeText(code.textContent).then(
        function () { button.textContent = "Copied"; },
        function () { button.textContent = "Select and copy"; }
      );
      setTimeout(function () { button.textContent = "Copy"; }, 2000);
    });
  });
})();
