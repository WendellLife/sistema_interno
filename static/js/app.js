/* Comportamentos do shell: CSRF no HTMX, toast, busca global (/), cronômetro. */
document.addEventListener("DOMContentLoaded", () => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  document.body.addEventListener("htmx:configRequest", (e) => { if (token) e.detail.headers["X-CSRFToken"] = token; });
  // Respostas 4xx com HTML (modais de erro, card com aviso) devem ser trocadas normalmente
  document.body.addEventListener("htmx:beforeSwap", (e) => {
    if ([400, 403, 404, 409].includes(e.detail.xhr.status)) { e.detail.shouldSwap = true; e.detail.isError = false; }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
      e.preventDefault(); window.dispatchEvent(new CustomEvent("abrir-busca"));
    }
  });
});

function toast(msg) {
  if (!msg) return;
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = msg; document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

/* Cronômetro: a verdade é do servidor (inicio + hora do servidor); o cliente só conta. */
function cronometro(estadoUrl) {
  return {
    ativo: false, inicio: null, offset: 0, tipo: null, chamado: null, texto: "0:00:00",
    async sync() {
      try {
        const r = await fetch(estadoUrl, { credentials: "same-origin" });
        const d = await r.json();
        this.ativo = d.ativo; this.tipo = d.tipo; this.chamado = d.chamado;
        this.inicio = d.inicio ? new Date(d.inicio).getTime() : null;
        this.offset = new Date(d.agora).getTime() - Date.now();
        this.tick();
      } catch (_) {}
    },
    tick() {
      if (!this.ativo || !this.inicio) { this.texto = "0:00:00"; return; }
      const s = Math.max(0, Math.floor((Date.now() + this.offset - this.inicio) / 1000));
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
      this.texto = `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
    },
    init() {
      this.sync();
      setInterval(() => this.tick(), 1000);
      setInterval(() => this.sync(), 60000);
      document.body.addEventListener("htmx:afterSwap", (e) => { if (e.detail.target.id === "card-apontamento") this.sync(); });
    },
  };
}
