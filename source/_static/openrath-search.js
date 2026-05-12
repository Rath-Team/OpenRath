(function () {
  function isSearchPage() {
    return Boolean(document.querySelector("#search-results"));
  }

  function submitSearch(form) {
    const input = form.querySelector('input[name="q"]');
    const query = input ? input.value.trim() : "";
    if (!query) {
      return;
    }
    const target = new URL(window.location.href);
    target.pathname = target.pathname.replace(/[^/]*$/, "search.html");
    target.hash = "";
    target.search = "q=" + encodeURIComponent(query);
    window.location.assign(target.toString());
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!isSearchPage()) {
      return;
    }

    const mainForm = document.querySelector("main form.bd-search");
    if (!mainForm) {
      return;
    }

    mainForm.setAttribute("action", "search.html");
    mainForm.addEventListener("submit", function (event) {
      event.preventDefault();
      submitSearch(mainForm);
    });

    const input = mainForm.querySelector('input[name="q"]');
    if (input) {
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          submitSearch(mainForm);
        }
      });
    }
  });
})();
