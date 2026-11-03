(function () {
  const root = document.documentElement;
  const preference = root.dataset.themePreference || localStorage.getItem("splitmate-theme") || "system";

  function apply(pref) {
    const dark = pref === "dark" || (pref !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.setAttribute("data-bs-theme", dark ? "dark" : "light");
  }

  apply(preference);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
    apply(root.dataset.themePreference || "system");
  });

  const shell = document.querySelector(".app-shell");
  const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  if (shell && sidebarToggle) {
    const setSidebar = function (collapsed) {
      shell.classList.toggle("sidebar-collapsed", collapsed);
      sidebarToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      sidebarToggle.setAttribute("aria-label", collapsed ? "Show menu" : "Hide menu");
    };
    setSidebar(localStorage.getItem("splitmate-sidebar") === "hidden");
    sidebarToggle.addEventListener("click", function () {
      const collapsed = !shell.classList.contains("sidebar-collapsed");
      setSidebar(collapsed);
      localStorage.setItem("splitmate-sidebar", collapsed ? "hidden" : "shown");
    });
  }

  document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      const input = button.parentElement.querySelector("input");
      if (!input) return;
      const hidden = input.type === "password";
      input.type = hidden ? "text" : "password";
      const nowHidden = input.type === "password";
      button.setAttribute("aria-pressed", nowHidden ? "false" : "true");
      button.setAttribute("aria-label", nowHidden ? "Show password" : "Hide password");
      const icon = button.querySelector("i");
      if (icon) icon.className = nowHidden ? "bi bi-eye-slash" : "bi bi-eye";
    });
  });

  document.querySelectorAll("[data-password-match]").forEach(function (box) {
    const first = document.getElementById(box.dataset.with);
    const second = document.getElementById(box.dataset.for);
    const text = box.querySelector(".password-match-text");
    if (!first || !second || !text) return;
    const sync = function () {
      const left = first.value;
      const right = second.value;
      if (!left && !right) {
        box.hidden = true;
        return;
      }
      box.hidden = false;
      const same = left.length > 0 && left === right;
      const longEnough = left.length >= 6;
      const ok = same && longEnough;
      box.classList.toggle("is-match", ok);
      box.classList.toggle("is-mismatch", !ok);
      if (ok) text.textContent = "Passwords match.";
      else if (!same) text.textContent = "Passwords do not match.";
      else text.textContent = "Use at least 6 characters.";
    };
    first.addEventListener("input", sync);
    second.addEventListener("input", sync);
  });

  document.querySelectorAll(".agreement a").forEach(function (link) {
    link.addEventListener("click", function (event) {
      event.stopPropagation();
    });
  });

  document.querySelectorAll("[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  document.querySelectorAll("form[data-once]").forEach(function (form) {
    form.addEventListener("submit", function () {
      if (form.dataset.submitted === "1") return;
      form.dataset.submitted = "1";
      const button = form.querySelector("[data-save]");
      if (button) button.disabled = true;
    });
  });

  const expenseForm = document.querySelector("[data-expense-form]");
  if (expenseForm) {
    const sync = function () {
      const selected = expenseForm.querySelector("input[name=split_method]:checked");
      expenseForm.dataset.method = selected ? selected.value : "equal";
    };
    expenseForm.querySelectorAll("input[name=split_method]").forEach(function (input) {
      input.addEventListener("change", sync);
    });
    sync();
  }

  document.querySelectorAll("[data-chart]").forEach(function (canvas) {
    const node = document.getElementById(canvas.dataset.chart);
    if (!node || !window.Chart) return;
    const data = JSON.parse(node.textContent);
    if (canvas.dataset.kind === "line" && data.labels.length) {
      new Chart(canvas, {
        type: "line",
        data: { labels: data.labels, datasets: [{ label: "Your share", data: data.values, borderColor: "#1f6f5b", tension: 0.25 }] },
        options: { plugins: { legend: { display: false } } },
      });
    }
    if (canvas.dataset.kind === "doughnut" && data.categories.length) {
      new Chart(canvas, {
        type: "doughnut",
        data: { labels: data.categories, datasets: [{ data: data.category_values }] },
      });
    }
  });
})();
