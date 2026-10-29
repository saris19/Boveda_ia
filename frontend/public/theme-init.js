try {
  var theme = localStorage.getItem("boveda.theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch (e) {}
