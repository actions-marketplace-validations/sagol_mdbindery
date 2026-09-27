(function () {
  "use strict";

  // 1. Theme Management (Dark default, respects saved preference or OS preference)
  var root = document.documentElement;
  var themeToggle = document.getElementById("theme-toggle");
  var savedTheme = null;

  try {
    savedTheme = localStorage.getItem("mdbindery-theme");
  } catch (e) {
    savedTheme = null;
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    if (themeToggle) {
      themeToggle.textContent = theme === "light" ? "Dark theme" : "Light theme";
      themeToggle.setAttribute(
        "aria-label",
        theme === "light" ? "Switch to dark theme" : "Switch to light theme"
      );
    }
  }

  if (savedTheme === "light" || savedTheme === "dark") {
    applyTheme(savedTheme);
  } else if (
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: light)").matches
  ) {
    applyTheme("light");
  } else {
    applyTheme("dark");
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      var current =
        root.getAttribute("data-theme") === "light" ? "light" : "dark";
      var next = current === "light" ? "dark" : "light";
      applyTheme(next);
      try {
        localStorage.setItem("mdbindery-theme", next);
      } catch (e) {
        // Ignore storage errors in private browsing
      }
    });
  }

  // 2. Accessible Installation Tabs (Progressive Enhancement: all panels visible if JS off)
  var tabButtons = Array.prototype.slice.call(
    document.querySelectorAll('[role="tab"]')
  );
  var tabPanels = Array.prototype.slice.call(
    document.querySelectorAll('[role="tabpanel"]')
  );
  var panelTitles = Array.prototype.slice.call(
    document.querySelectorAll(".tab-panel-title")
  );

  panelTitles.forEach(function (el) {
    el.setAttribute("hidden", "hidden");
  });

  function activateTab(selectedBtn, focusTab) {
    var targetId = selectedBtn.getAttribute("aria-controls");
    tabButtons.forEach(function (btn) {
      var isSelected = btn === selectedBtn;
      btn.setAttribute("aria-selected", isSelected ? "true" : "false");
      btn.setAttribute("tabindex", isSelected ? "0" : "-1");
      if (isSelected && focusTab) {
        btn.focus();
      }
    });
    tabPanels.forEach(function (panel) {
      if (panel.id === targetId) {
        panel.removeAttribute("hidden");
      } else {
        panel.setAttribute("hidden", "hidden");
      }
    });
  }

  if (tabButtons.length > 0) {
    var initialTab =
      tabButtons.find(function (b) {
        return b.getAttribute("aria-selected") === "true";
      }) || tabButtons[0];
    activateTab(initialTab, false);
  }

  tabButtons.forEach(function (btn, index) {
    btn.addEventListener("click", function () {
      activateTab(btn, false);
    });
    btn.addEventListener("keydown", function (e) {
      var nextIndex = null;
      if (e.key === "ArrowRight") {
        nextIndex = (index + 1) % tabButtons.length;
      } else if (e.key === "ArrowLeft") {
        nextIndex = (index - 1 + tabButtons.length) % tabButtons.length;
      } else if (e.key === "Home") {
        nextIndex = 0;
      } else if (e.key === "End") {
        nextIndex = tabButtons.length - 1;
      }
      if (nextIndex !== null) {
        e.preventDefault();
        activateTab(tabButtons[nextIndex], true);
      }
    });
  });

  // 3. Copy-to-Clipboard Buttons with Timer Cancellation, Selection Fallback & Live Region
  var copyButtons = Array.prototype.slice.call(
    document.querySelectorAll(".copy-btn")
  );
  var copyLive = document.getElementById("copy-status-live");
  var copyTimers = new WeakMap();

  function selectCodeElement(codeEl) {
    try {
      var selection = window.getSelection ? window.getSelection() : null;
      if (selection && document.createRange) {
        var range = document.createRange();
        range.selectNodeContents(codeEl);
        selection.removeAllRanges();
        selection.addRange(range);
        return true;
      }
    } catch (e) {
      // Ignore selection errors
    }
    return false;
  }

  function setCopyFeedback(btn, label, liveMsg) {
    var defaultLabel =
      btn.getAttribute("data-default-label") || btn.textContent || "Copy";
    btn.setAttribute("data-default-label", defaultLabel);

    var prevTimer = copyTimers.get(btn);
    if (prevTimer) {
      clearTimeout(prevTimer);
    }

    btn.textContent = label;
    if (copyLive) {
      copyLive.textContent = liveMsg;
    }

    var timer = setTimeout(function () {
      btn.textContent = defaultLabel;
      copyTimers.delete(btn);
    }, 2000);
    copyTimers.set(btn, timer);
  }

  copyButtons.forEach(function (btn) {
    btn.setAttribute("data-default-label", btn.textContent || "Copy");
    btn.addEventListener("click", function () {
      var targetId = btn.getAttribute("data-copy-target");
      var codeEl = targetId ? document.getElementById(targetId) : null;
      if (!codeEl && btn.parentElement) {
        codeEl = btn.parentElement.querySelector("code");
      }
      if (!codeEl) {
        return;
      }
      var text = codeEl.textContent || "";

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () {
            setCopyFeedback(btn, "Copied", "Copied to clipboard.");
          },
          function () {
            var selected = selectCodeElement(codeEl);
            setCopyFeedback(
              btn,
              selected ? "Text selected" : "Copy failed",
              selected
                ? "Copy unavailable. Text selected; press Ctrl+C or Command+C, or use your device’s Copy action."
                : "Could not copy. Select the text and use your device’s Copy action."
            );
          }
        );
      } else {
        var selected = selectCodeElement(codeEl);
        setCopyFeedback(
          btn,
          selected ? "Text selected" : "Copy failed",
          selected
            ? "Copy unavailable. Text selected; press Ctrl+C or Command+C, or use your device’s Copy action."
            : "Could not copy. Select the text and use your device’s Copy action."
        );
      }
    });
  });

  // 4. Interactive Diagnostic Check Codes Filter (MB001 - MB904)
  var searchInput = document.getElementById("mb-search");
  var filterPills = Array.prototype.slice.call(
    document.querySelectorAll(".filter-pill")
  );
  var allPill = document.querySelector('.filter-pill[data-filter="all"]');
  var codeRows = Array.prototype.slice.call(
    document.querySelectorAll("#mb-codes-tbody tr")
  );
  var countStatus = document.getElementById("mb-count-status");
  var activeSeverity = "all";

  if (allPill && codeRows.length > 0) {
    allPill.textContent = "All (" + codeRows.length + ")";
  }

  function filterCheckCodes() {
    var query = searchInput ? searchInput.value.trim().toLowerCase() : "";
    var visibleCount = 0;

    codeRows.forEach(function (row) {
      var rowSeverity = (row.getAttribute("data-severity") || "").toLowerCase();
      var rowText = (row.textContent || "").toLowerCase();
      var matchesSeverity =
        activeSeverity === "all" || rowSeverity.indexOf(activeSeverity) !== -1;
      var matchesQuery = !query || rowText.indexOf(query) !== -1;

      if (matchesSeverity && matchesQuery) {
        row.removeAttribute("hidden");
        visibleCount += 1;
      } else {
        row.setAttribute("hidden", "hidden");
      }
    });

    if (countStatus) {
      countStatus.textContent =
        "Showing " + visibleCount + " of " + codeRows.length + " check codes";
    }
  }

  filterCheckCodes();

  if (searchInput) {
    searchInput.addEventListener("input", filterCheckCodes);
  }

  filterPills.forEach(function (pill) {
    pill.addEventListener("click", function () {
      activeSeverity = pill.getAttribute("data-filter") || "all";
      filterPills.forEach(function (p) {
        p.setAttribute("aria-pressed", p === pill ? "true" : "false");
      });
      filterCheckCodes();
    });
  });
})();
