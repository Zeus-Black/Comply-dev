// Comply Extension — Content Script
// Extrait le texte de la page active (Notion, Google Drive, générique)

function extractPageContent() {
  const url = window.location.href;
  let text = "";

  try {
    if (url.includes("notion.so") || url.includes("notion.site")) {
      // Notion : chercher le conteneur principal de la page
      const selectors = [
        ".notion-page-content",
        ".notion-scroller",
        '[data-content-editable-root="true"]',
        ".notion-frame",
      ];
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) {
          text = el.innerText;
          break;
        }
      }
      // Fallback : tout le body sans la nav
      if (!text) {
        const clone = document.body.cloneNode(true);
        clone.querySelectorAll(".notion-sidebar, .notion-topbar, script, style").forEach((el) => el.remove());
        text = clone.innerText;
      }
    } else if (url.includes("docs.google.com")) {
      // Google Docs
      const selectors = [".kix-page", ".docs-texteventtarget-iframe", "#docs-editor"];
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) {
          text = el.innerText;
          break;
        }
      }
    } else if (url.includes("drive.google.com")) {
      // Google Drive (page de liste)
      const el = document.querySelector('[role="main"]') || document.querySelector(".a-d-Ta");
      text = el ? el.innerText : document.body.innerText;
    } else {
      // Page générique : nettoyer les éléments non-content
      const clone = document.body.cloneNode(true);
      clone
        .querySelectorAll("script, style, nav, footer, header, aside, [role='navigation'], [role='banner']")
        .forEach((el) => el.remove());
      text = clone.innerText;
    }
  } catch (e) {
    text = document.body.innerText;
  }

  // Nettoyage : supprimer les lignes trop courtes et les espaces multiples
  text = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 2)
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .slice(0, 15000);

  return text;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "getPageContent") {
    sendResponse({
      content: extractPageContent(),
      title: document.title,
      url: window.location.href,
    });
  }
  return true;
});
