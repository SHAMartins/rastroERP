// Menu lateral: abre o painel do modulo ao passar o mouse (desktop) ou ao clicar/tocar.
(function () {
  const modulos = document.querySelectorAll(".modulo[data-flyout]");
  const hover = window.matchMedia("(hover: hover) and (min-width: 992px)");
  let timer;

  function fecharTodos(exceto) {
    modulos.forEach((m) => {
      if (m !== exceto) {
        m.classList.remove("aberto");
        m.querySelector(".modulo-link").setAttribute("aria-expanded", "false");
      }
    });
  }

  function abrir(m) {
    fecharTodos(m);
    m.classList.add("aberto");
    m.querySelector(".modulo-link").setAttribute("aria-expanded", "true");
  }

  modulos.forEach((m) => {
    const botao = m.querySelector(".modulo-link");
    botao.addEventListener("click", () => {
      // Com mouse o hover ja abriu o painel: o clique so confirma. No toque, o clique alterna.
      if (hover.matches || !m.classList.contains("aberto")) abrir(m);
      else fecharTodos();
    });
    m.addEventListener("mouseenter", () => {
      if (!hover.matches) return;
      clearTimeout(timer);
      abrir(m);
    });
    m.addEventListener("mouseleave", () => {
      if (!hover.matches) return;
      timer = setTimeout(() => fecharTodos(), 180);
    });
  });

  document.addEventListener("click", (e) => {
    if (hover.matches && !e.target.closest(".modulo[data-flyout]")) fecharTodos();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      fecharTodos();
      document.body.classList.remove("menu-aberto");
    }
  });

  // Filtros que se aplicam ao escolher (substitui onchange inline, bloqueado pelo CSP)
  document.addEventListener("change", (e) => {
    if (e.target.matches("[data-autoenvio]") && e.target.form) e.target.form.submit();
  });

  // Gaveta do menu no celular
  const btnMenu = document.querySelector(".btn-menu");
  const sombra = document.querySelector(".sombra-menu");
  if (btnMenu) btnMenu.addEventListener("click", () => document.body.classList.toggle("menu-aberto"));
  if (sombra) sombra.addEventListener("click", () => document.body.classList.remove("menu-aberto"));
})();
