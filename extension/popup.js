// Comply Extension — Popup Logic

const DEFAULT_API_URL = "http://localhost:8000";
const MAX_CONTEXT_CHARS = 8000;

// ── État ──────────────────────────────────────────────────────────────────────
let apiUrl = DEFAULT_API_URL;
let sessionId = null;
let pageContext = null;  // { content, title, url }
let usePageContext = true;
let isLoading = false;

// ── Éléments DOM ──────────────────────────────────────────────────────────────
const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const btnSend = document.getElementById("btn-send");
const btnClear = document.getElementById("btn-clear");
const btnSettings = document.getElementById("btn-settings");
const settingsPanel = document.getElementById("settings-panel");
const apiUrlInput = document.getElementById("api-url-input");
const btnSaveSettings = document.getElementById("btn-save-settings");
const pageContextEl = document.getElementById("page-context");
const pageContextTitle = document.getElementById("page-context-title");
const btnToggleContext = document.getElementById("btn-toggle-context");

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  // Charger l'URL de l'API
  const stored = await chrome.storage.local.get(["apiUrl", "sessionId"]);
  apiUrl = stored.apiUrl || DEFAULT_API_URL;
  sessionId = stored.sessionId || null;
  apiUrlInput.value = apiUrl;

  // Charger le contenu de la page active
  await loadPageContext();
}

async function loadPageContext() {
  try {
    const response = await chrome.runtime.sendMessage({ action: "getPageContent" });
    if (response && response.content && response.content.trim().length > 100) {
      pageContext = response;
      pageContextTitle.textContent = response.title || response.url || "Page actuelle";
      pageContextEl.classList.remove("hidden");
    }
  } catch (e) {
    // Pas de content script disponible sur cette page (ex : about:blank, PDF natif)
  }
}

// ── Messages ──────────────────────────────────────────────────────────────────
function appendMessage(role, content) {
  const div = document.createElement("div");
  div.className = `message ${role}`;

  // Rendu markdown basique
  div.innerHTML = renderMarkdown(content);

  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function appendTyping() {
  const div = document.createElement("div");
  div.className = "typing";
  div.id = "typing-indicator";
  div.innerHTML = "<span></span><span></span><span></span>";
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function removeTyping() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

function renderMarkdown(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^#{1,3} (.+)$/gm, "<strong>$1</strong>")
    .replace(/^[-*] (.+)$/gm, "• $1")
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br/>")
    .replace(/^(.+)$/, "<p>$1</p>");
}

// ── Envoi ─────────────────────────────────────────────────────────────────────
async function sendMessage() {
  const question = inputEl.value.trim();
  if (!question || isLoading) return;

  isLoading = true;
  btnSend.disabled = true;
  inputEl.value = "";
  inputEl.style.height = "auto";

  appendMessage("user", question);

  // Construire la question avec contexte page si activé
  let fullQuestion = question;
  if (usePageContext && pageContext?.content) {
    const contextSnippet = pageContext.content.slice(0, MAX_CONTEXT_CHARS);
    fullQuestion = `${question}\n\n---\nContexte de la page "${pageContext.title}":\n${contextSnippet}`;
  }

  const typing = appendTyping();

  try {
    // Appel en streaming
    const response = await fetch(`${apiUrl}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: fullQuestion,
        session_id: sessionId,
      }),
    });

    if (!response.ok) {
      throw new Error(`Erreur API ${response.status}`);
    }

    removeTyping();

    const msgDiv = appendMessage("assistant", "");
    let fullText = "";
    let pEl = document.createElement("p");
    msgDiv.innerHTML = "";
    msgDiv.appendChild(pEl);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (data === "[DONE]") break;

        try {
          const chunk = JSON.parse(data);
          if (chunk.type === "session" && chunk.session_id) {
            sessionId = chunk.session_id;
            chrome.storage.local.set({ sessionId });
          } else if (chunk.type === "token" && chunk.text) {
            fullText += chunk.text;
            msgDiv.innerHTML = renderMarkdown(fullText);
            messagesEl.scrollTop = messagesEl.scrollHeight;
          }
        } catch (_) {}
      }
    }

  } catch (err) {
    removeTyping();
    const errDiv = appendMessage("error", `Erreur de connexion à l'API Comply.\nVérifiez que l'URL est correcte dans les paramètres.\n\nDétail : ${err.message}`);
  } finally {
    isLoading = false;
    btnSend.disabled = false;
    inputEl.focus();
  }
}

// ── Événements ────────────────────────────────────────────────────────────────
btnSend.addEventListener("click", sendMessage);

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Auto-resize textarea
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 80) + "px";
});

btnClear.addEventListener("click", () => {
  sessionId = null;
  chrome.storage.local.remove("sessionId");
  messagesEl.innerHTML = "";
  appendMessage(
    "assistant",
    "Conversation effacée. Comment puis-je vous aider ?"
  );
});

btnSettings.addEventListener("click", () => {
  settingsPanel.classList.toggle("hidden");
});

btnSaveSettings.addEventListener("click", () => {
  const url = apiUrlInput.value.trim().replace(/\/$/, "");
  if (url) {
    apiUrl = url;
    chrome.storage.local.set({ apiUrl: url });
  }
  settingsPanel.classList.add("hidden");

  // Confirmation visuelle
  btnSaveSettings.textContent = "Enregistré !";
  setTimeout(() => { btnSaveSettings.textContent = "Enregistrer"; }, 1500);
});

btnToggleContext.addEventListener("click", () => {
  usePageContext = !usePageContext;
  btnToggleContext.textContent = usePageContext ? "Utiliser" : "Désactivé";
  btnToggleContext.className = usePageContext ? "active" : "inactive";
  inputEl.placeholder = usePageContext
    ? "Question sur la page ou sur les JE..."
    : "Votre question...";
});

// ── Démarrage ─────────────────────────────────────────────────────────────────
init();
