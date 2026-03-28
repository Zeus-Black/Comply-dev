import pkg from "@slack/bolt";
const { App } = pkg;
import * as dotenv from "dotenv";
import axios from "axios";

dotenv.config();

const API_URL = process.env.API_URL || "http://localhost:8000";

// Sessions par user Slack (historique de conversation)
const userSessions = new Map<string, string>();

const app = new App({
  token: process.env.SLACK_BOT_TOKEN || "",
  signingSecret: process.env.SLACK_SIGNING_SECRET || "",
  socketMode: true,
  appToken: process.env.SLACK_APP_TOKEN || "",
});

// ── Helpers ──────────────────────────────────────────────────────────────────

async function callComply(
  userId: string,
  question: string
): Promise<{ answer: string; source: string; confidence: number; docsFound: number }> {
  const sessionId = userSessions.get(userId);

  const { data } = await axios.post(
    `${API_URL}/chat`,
    {
      question,
      session_id: sessionId || undefined,
    },
    { timeout: 60_000 }
  );

  if (data.session_id) {
    userSessions.set(userId, data.session_id);
  }

  return {
    answer: data.answer,
    source: data.source,
    confidence: data.confidence,
    docsFound: data.documents_found,
  };
}

function formatSlackBlocks(answer: string, source: string, confidence: number, docsFound: number) {
  const sourceEmoji = { rag: "🌿", web: "🌐", ticket: "🎫" }[source] || "🤖";
  const sourceName = { rag: "Base Kiwi", web: "Recherche web", ticket: "Support CNJE" }[source] || source;
  const confidencePct = Math.round(confidence * 100);

  return [
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: answer.slice(0, 2900), // Limite Slack
      },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: `${sourceEmoji} *${sourceName}*${docsFound > 0 ? ` · ${docsFound} source${docsFound > 1 ? "s" : ""}` : ""}${confidence > 0 ? ` · Confiance : ${confidencePct}%` : ""} · _Comply v2 · CNJE_`,
        },
      ],
    },
  ];
}

// ── Messages directs ──────────────────────────────────────────────────────────

app.message(async ({ message, say }) => {
  // @ts-ignore
  if (message.channel_type !== "im") return;
  // @ts-ignore
  const text: string = message.text || "";
  // @ts-ignore
  const userId: string = message.user || "unknown";

  if (!text.trim()) return;

  // Commandes spéciales
  if (text.toLowerCase() === "/reset" || text.toLowerCase() === "reset") {
    userSessions.delete(userId);
    await say("✅ Historique de conversation effacé.");
    return;
  }

  if (text.toLowerCase() === "/help" || text.toLowerCase() === "help") {
    await say({
      blocks: [
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: "*🌿 Comply — Assistant IA des Junior-Entreprises*\n\nJe peux vous aider avec :\n• ⚖️ Questions légales et réglementaires (Kiwi Légal)\n• 📚 Formations et ressources (Kiwi Formation)\n• 🤝 Services et partenaires (Kiwi Services)\n• 🌱 RSE et développement durable (Kiwi RSE)\n• 📁 Documents CNJE\n\n*Commandes :*\n• `reset` — Effacer l'historique\n• `help` — Afficher cette aide\n\nPostez simplement votre question !",
          },
        },
      ],
    });
    return;
  }

  // Indicateur de réflexion
  const thinking = await say("⏳ Comply réfléchit...");

  try {
    const { answer, source, confidence, docsFound } = await callComply(userId, text);

    await app.client.chat.update({
      channel: (thinking as any).channel,
      ts: (thinking as any).ts,
      text: answer,
      blocks: formatSlackBlocks(answer, source, confidence, docsFound),
    });
  } catch (err: any) {
    console.error("Erreur API Comply:", err.message);
    await app.client.chat.update({
      channel: (thinking as any).channel,
      ts: (thinking as any).ts,
      text: "❌ Erreur de connexion à Comply. Veuillez réessayer dans quelques instants.",
    });
  }
});

// ── Mentions en channel ───────────────────────────────────────────────────────

app.event("app_mention", async ({ event, say }) => {
  const question = event.text.replace(/<@[A-Z0-9]+>/g, "").trim();
  const userId = event.user;

  if (!question) {
    await say({
      text: "Bonjour ! Posez-moi une question sur les Junior-Entreprises.",
      thread_ts: event.ts,
    });
    return;
  }

  const thinking = await say({
    text: "⏳ Comply réfléchit...",
    thread_ts: event.ts,
  });

  try {
    const { answer, source, confidence, docsFound } = await callComply(userId, question);

    await app.client.chat.update({
      channel: event.channel,
      ts: (thinking as any).ts,
      text: answer,
      blocks: formatSlackBlocks(answer, source, confidence, docsFound),
    });
  } catch (err: any) {
    console.error("Erreur API Comply:", err.message);
    await app.client.chat.update({
      channel: event.channel,
      ts: (thinking as any).ts,
      text: "❌ Erreur de connexion à Comply. Veuillez réessayer.",
    });
  }
});

// ── Slash command /comply ─────────────────────────────────────────────────────

app.command("/comply", async ({ command, ack, respond }) => {
  await ack();

  const question = command.text.trim();
  if (!question) {
    await respond("Utilisez `/comply votre question` pour interroger Comply.");
    return;
  }

  await respond({ text: "⏳ Comply réfléchit..." });

  try {
    const { answer, source, confidence, docsFound } = await callComply(
      command.user_id,
      question
    );
    await respond({
      replace_original: true,
      text: answer,
      blocks: formatSlackBlocks(answer, source, confidence, docsFound),
    });
  } catch (err: any) {
    console.error("Erreur:", err.message);
    await respond({
      replace_original: true,
      text: "❌ Erreur de connexion à Comply.",
    });
  }
});

// ── Démarrage ─────────────────────────────────────────────────────────────────

(async () => {
  await app.start();
  console.log("🌿 Comply Slack Bot démarré !");
  console.log(`   API: ${API_URL}`);
})();
