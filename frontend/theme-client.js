// SPDX-License-Identifier: AGPL-3.0-only
// Only the display preference is persisted; identity and dialogue stay elsewhere.
(function () {
  "use strict";
  const valid = value => ["auto", "light", "dark"].includes(value);
  const media = window.matchMedia("(prefers-color-scheme: light)");
  let preference = "auto";
  try {
    const stored = window.localStorage.getItem("sol-theme");
    if (valid(stored)) preference = stored;
  } catch (_) { /* Storage may be unavailable in embedded hosts. */ }
  function apply() {
    document.documentElement.dataset.themePref = preference;
    document.documentElement.dataset.theme = preference === "auto"
      ? (media.matches ? "light" : "dark") : preference;
    document.querySelectorAll("[data-theme-picker]").forEach(control => {
      control.value = preference;
    });
  }
  function set(value) {
    if (!valid(value)) return;
    preference = value;
    try { window.localStorage.setItem("sol-theme", value); } catch (_) {}
    apply();
  }
  apply();
  if (media.addEventListener) media.addEventListener("change", apply);
  else media.addListener(apply);
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.querySelectorAll("[data-theme-picker]").forEach(control => {
      control.addEventListener("change", () => set(control.value));
    });
  });
})();
