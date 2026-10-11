// Leitura de codigo de barras / QR Code. Dois jeitos, ambos opcionais (sempre da para digitar):
//  1) Leitor USB/Bluetooth: funciona como um teclado que "digita" o codigo e aperta Enter.
//     Nos campos [data-leitor], esse Enter nao envia o formulario antes da hora.
//  2) Camera do celular/notebook: botao [data-scanner-alvo="#id-do-campo"] (biblioteca html5-qrcode).
// Modos do campo (data-leitor): "substituir" (um codigo), "anexar" (um por linha), "anexar-virgula".
(function () {
  function juntar(campo, texto, modo) {
    const atual = campo.value.trim();
    if (modo === "substituir" || !atual) return texto;
    return modo === "anexar-virgula" ? atual.replace(/,\s*$/, "") + ", " + texto : atual + "\n" + texto;
  }

  function avisarMudanca(campo) {
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // 1) Leitor tipo teclado: Enter num <input data-leitor> nao envia o form
  document.addEventListener("keydown", (e) => {
    const campo = e.target;
    if (e.key !== "Enter" || !(campo instanceof HTMLInputElement) || !campo.dataset.leitor) return;
    e.preventDefault();
    if (campo.dataset.leitor === "anexar-virgula") {
      if (campo.value.trim() && !campo.value.trim().endsWith(",")) campo.value = campo.value.trim() + ", ";
      return;
    }
    const campos = [...campo.form.elements].filter((c) => !c.disabled && c.type !== "hidden" && c.tagName !== "BUTTON");
    const proximo = campos[campos.indexOf(campo) + 1];
    if (proximo) proximo.focus();
  });

  // 2) Camera
  const modalEl = document.getElementById("modal-scanner");
  if (!modalEl || !window.bootstrap) return;
  const modal = new bootstrap.Modal(modalEl);
  const statusEl = document.getElementById("scanner-status");
  let leitor = null, alvo = null, lidos = new Set();

  const status = (texto) => { statusEl.textContent = texto; };

  document.addEventListener("click", (e) => {
    const botao = e.target.closest("[data-scanner-alvo]");
    if (!botao) return;
    e.preventDefault();
    alvo = document.querySelector(botao.dataset.scannerAlvo);
    if (!alvo) return;
    lidos = new Set();
    modal.show();
  });

  modalEl.addEventListener("shown.bs.modal", () => {
    if (!window.Html5Qrcode) {
      status("O scanner por camera nao carregou (sem internet?). Use o leitor USB ou digite o codigo.");
      return;
    }
    status("Aponte a camera para o codigo de barras ou QR Code.");
    leitor = new Html5Qrcode("scanner-video");
    leitor.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 280, height: 150 } }, lido, () => {})
      .catch((erro) => {
        leitor = null;                           // nada para parar depois
        status(`Nao foi possivel abrir a camera (${erro}). Libere a permissao da camera. ` +
               "Ela so funciona em localhost ou em endereco HTTPS.");
      });
  });

  modalEl.addEventListener("hidden.bs.modal", () => {
    if (!leitor) return;
    const l = leitor;
    leitor = null;
    try {                                        // stop() lanca erro direto se a camera nem chegou a abrir
      l.stop().catch(() => {}).finally(() => l.clear());
    } catch (e) {
      l.clear();
    }
  });

  function lido(texto) {
    texto = texto.trim();
    if (!texto || lidos.has(texto)) return;          // a camera le o mesmo codigo varias vezes por segundo
    lidos.add(texto);
    if (navigator.vibrate) navigator.vibrate(80);
    const modo = alvo.dataset.leitor || "substituir";
    alvo.value = juntar(alvo, texto, modo);
    avisarMudanca(alvo);
    if (modo === "substituir") {
      modal.hide();
      return;
    }
    status(`${lidos.size} lido(s). Ultimo: ${texto}. Continue lendo ou clique em Concluir.`);
  }
})();
