/* Runs in the head, before the page paints: marks the page as scripted and applies the stored theme (light or dark; none means auto). */
(function () {
  var root = document.documentElement;
  root.classList.add("js");
  try {
    var choice = window.localStorage.getItem("craticula-theme");
    if (choice === "light" || choice === "dark") {
      root.setAttribute("data-theme", choice);
    }
  } catch (error) {
    root.removeAttribute("data-theme");
  }
})();
