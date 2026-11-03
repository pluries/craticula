/* The site's own script: the theme switch, search, copy buttons and the phone menu. Every string from the index or the address is shown as text. */
(function () {
  var root = document.documentElement;
  var THEME_KEY = "craticula-theme";
  var THEMES = ["auto", "light", "dark"];

  function currentTheme() {
    var set = root.getAttribute("data-theme");
    return set === "light" || set === "dark" ? set : "auto";
  }

  function showTheme(button) {
    var name = currentTheme();
    button.setAttribute("aria-label", "Theme: " + name.charAt(0).toUpperCase() + name.slice(1) + ". Change theme");
    button.setAttribute("title", "Theme: " + name);
  }

  function setupTheme() {
    var buttons = document.querySelectorAll(".theme-button");
    buttons.forEach(function (button) {
      showTheme(button);
      button.addEventListener("click", function () {
        var next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
        if (next === "auto") {
          root.removeAttribute("data-theme");
        } else {
          root.setAttribute("data-theme", next);
        }
        try {
          if (next === "auto") {
            window.localStorage.removeItem(THEME_KEY);
          } else {
            window.localStorage.setItem(THEME_KEY, next);
          }
        } catch (error) {
          button.setAttribute("data-unsaved", "true");
        }
        buttons.forEach(showTheme);
      });
    });
  }

  function setupMenu() {
    var toggle = document.querySelector(".menu-toggle");
    if (!toggle) {
      return;
    }
    function setOpen(open) {
      root.classList.toggle("menu-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    }
    toggle.addEventListener("click", function () {
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        setOpen(false);
        toggle.focus();
      }
    });
  }

  function setupCopy() {
    document.querySelectorAll(".prose pre").forEach(function (block) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "copy-button";
      button.textContent = "Copy";
      button.setAttribute("aria-label", "Copy this code");
      button.addEventListener("click", function () {
        var code = block.querySelector("code");
        var text = (code || block).textContent;
        function report(label, state) {
          button.textContent = label;
          button.setAttribute("data-state", state);
          window.setTimeout(function () {
            button.textContent = "Copy";
            button.removeAttribute("data-state");
          }, 1800);
        }
        if (!navigator.clipboard) {
          report("Copy failed", "failed");
          return;
        }
        navigator.clipboard.writeText(text).then(function () {
          report("Copied", "copied");
        }, function () {
          report("Copy failed", "failed");
        });
      });
      block.appendChild(button);
    });
  }

  var index = null;
  var failed = false;
  var overlay = null;
  var input = null;
  var list = null;
  var opener = null;
  var hits = [];
  var selected = 0;
  var status = null;

  function loadIndex() {
    if (index || failed) {
      return Promise.resolve();
    }
    return fetch("search-index.json")
      .then(function (response) {
        if (!response.ok) {
          throw new Error("index");
        }
        return response.json();
      })
      .then(function (entries) {
        index = entries;
      })
      .catch(function () {
        failed = true;
      });
  }

  function terms(query) {
    return query.toLowerCase().split(/\s+/).filter(function (word) {
      return word.length > 0;
    });
  }

  function has(text, words) {
    var lower = text.toLowerCase();
    return words.every(function (word) {
      return lower.indexOf(word) >= 0;
    });
  }

  function score(entry, words) {
    var best = 0;
    var heading = null;
    var title = entry.title.toLowerCase();
    var joined = words.join(" ");
    if (title === joined) {
      best = 100;
    } else if (title.indexOf(joined) === 0) {
      best = 80;
    } else if (has(entry.title, words)) {
      best = 60;
    }
    entry.headings.forEach(function (item) {
      if (has(item.text, words)) {
        heading = heading || item;
        best = Math.max(best, 30);
      }
    });
    if (has(entry.description, words)) {
      best = Math.max(best, 15);
    }
    if (best === 0 && has(entry.text, words)) {
      best = 5;
    }
    return { score: best, heading: heading };
  }

  function search(query) {
    var words = terms(query);
    if (words.length === 0 || !index) {
      return [];
    }
    var found = [];
    index.forEach(function (entry, position) {
      var result = score(entry, words);
      if (result.score > 0) {
        found.push({ entry: entry, heading: result.heading, score: result.score, position: position });
      }
    });
    found.sort(function (a, b) {
      return b.score - a.score || a.position - b.position;
    });
    return found.slice(0, 8);
  }

  function note(message) {
    list.textContent = "";
    var item = document.createElement("li");
    item.className = "search-note";
    item.setAttribute("role", "presentation");
    item.textContent = message;
    list.appendChild(item);
    status.textContent = message;
    hits = [];
    mark();
  }

  function mark() {
    hits.forEach(function (link, position) {
      link.parentNode.setAttribute("aria-selected", position === selected ? "true" : "false");
    });
    if (hits[selected]) {
      input.setAttribute("aria-activedescendant", hits[selected].parentNode.id);
      hits[selected].scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function render() {
    if (failed) {
      note("Search is not available right now. Use the sidebar to browse the pages.");
      return;
    }
    if (!index) {
      note("Loading the search index...");
      return;
    }
    var found = search(input.value);
    if (found.length === 0) {
      note(terms(input.value).length === 0 ? "Type to search the documentation." : "Nothing matches that search.");
      return;
    }
    list.textContent = "";
    hits = [];
    selected = 0;
    found.forEach(function (result) {
      var item = document.createElement("li");
      item.setAttribute("role", "option");
      item.id = "search-hit-" + hits.length;
      var link = document.createElement("a");
      var title = document.createElement("strong");
      var place = document.createElement("span");
      link.className = "search-hit";
      link.tabIndex = -1;
      link.href = result.entry.slug + ".html" + (result.heading ? "#" + result.heading.anchor : "");
      title.textContent = result.entry.title;
      place.textContent = (result.entry.group ? result.entry.group + " / " : "") + (result.heading ? result.heading.text : result.entry.description);
      link.appendChild(title);
      link.appendChild(place);
      item.appendChild(link);
      list.appendChild(item);
      hits.push(link);
    });
    status.textContent = found.length + (found.length === 1 ? " result" : " results");
    mark();
  }

  function closeSearch(restoreFocus) {
    overlay.hidden = true;
    if (restoreFocus && opener) {
      opener.focus();
    }
  }

  function openSearch(from) {
    if (!overlay.hidden) {
      return;
    }
    opener = from || document.activeElement;
    overlay.hidden = false;
    input.value = "";
    note("Loading the search index...");
    input.focus();
    loadIndex().then(render);
  }

  function setupSearch() {
    overlay = document.createElement("div");
    overlay.className = "search-overlay";
    overlay.hidden = true;
    var box = document.createElement("div");
    box.className = "search-box";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", "Search the documentation");
    input = document.createElement("input");
    input.type = "search";
    input.className = "search-input";
    input.setAttribute("aria-label", "Search");
    input.setAttribute("placeholder", "Search the documentation");
    list = document.createElement("ul");
    list.className = "search-results";
    list.id = "search-results";
    list.setAttribute("role", "listbox");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "true");
    input.setAttribute("aria-controls", "search-results");
    status = document.createElement("p");
    status.className = "search-status";
    status.setAttribute("role", "status");
    box.appendChild(input);
    box.appendChild(status);
    box.appendChild(list);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    list.addEventListener("click", function (event) {
      if (event.target.closest && event.target.closest(".search-hit")) {
        closeSearch(false);
      }
    });

    input.addEventListener("input", render);
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        closeSearch(true);
      }
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" && hits.length > 0) {
        selected = (selected + 1) % hits.length;
        mark();
        event.preventDefault();
      } else if (event.key === "ArrowUp" && hits.length > 0) {
        selected = (selected + hits.length - 1) % hits.length;
        mark();
        event.preventDefault();
      } else if (event.key === "Enter" && hits[selected]) {
        closeSearch(false);
        window.location.href = hits[selected].href;
      } else if (event.key === "Tab") {
        event.preventDefault();
      }
    });
    document.querySelectorAll(".search-button").forEach(function (button) {
      button.addEventListener("click", function () {
        openSearch(button);
      });
    });
    document.addEventListener("keydown", function (event) {
      var typing = /^(input|textarea|select)$/i.test(event.target.tagName) || event.target.isContentEditable;
      if (event.key === "Escape" && !overlay.hidden) {
        closeSearch(true);
      } else if (((event.key || "").toLowerCase() === "k" && (event.ctrlKey || event.metaKey)) || (event.key === "/" && !typing)) {
        event.preventDefault();
        openSearch(null);
      }
    });
  }

  setupTheme();
  setupMenu();
  setupCopy();
  setupSearch();
})();
