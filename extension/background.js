// Comply Extension — Service Worker

const DEFAULT_API_URL = "http://localhost:8000";

// Initialisation des settings par défaut
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get("apiUrl", (data) => {
    if (!data.apiUrl) {
      chrome.storage.local.set({ apiUrl: DEFAULT_API_URL });
    }
  });
});

// Relay pour les messages depuis popup → content script
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "getPageContent") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs[0]?.id) {
        sendResponse({ error: "Aucun onglet actif" });
        return;
      }
      chrome.tabs.sendMessage(tabs[0].id, { action: "getPageContent" }, (response) => {
        if (chrome.runtime.lastError) {
          // Content script non injecté — injection manuelle
          chrome.scripting.executeScript(
            { target: { tabId: tabs[0].id }, files: ["content.js"] },
            () => {
              chrome.tabs.sendMessage(tabs[0].id, { action: "getPageContent" }, (resp) => {
                sendResponse(resp || { content: "", title: "", url: "" });
              });
            }
          );
        } else {
          sendResponse(response || { content: "", title: "", url: "" });
        }
      });
    });
    return true; // async
  }
});
