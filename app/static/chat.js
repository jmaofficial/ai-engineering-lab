import { renderMarkdown } from "/static/markdown.js";

const form = document.querySelector("#chat-form");
const input = document.querySelector("#message");
const send = document.querySelector("#send");
const newChat = document.querySelector("#new-chat");
const messages = document.querySelector("#messages");
const welcome = document.querySelector("#welcome");
const status = document.querySelector("#status");
const error = document.querySelector("#error");
const storageKey = "ai-lab-chat-v1";
let conversationId = null;
let history = [];
let busy = false;

try {
  const saved = JSON.parse(localStorage.getItem(storageKey));
  if (saved && Number.isInteger(saved.conversationId) && saved.conversationId > 0 &&
      Array.isArray(saved.messages) && saved.messages.length <= 200 &&
      saved.messages.every(m => ["user", "assistant"].includes(m.role) && typeof m.content === "string")) {
    conversationId = saved.conversationId;
    history = saved.messages;
  }
} catch { /* Chat still works when browser storage is unavailable. */ }

function save() {
  try { localStorage.setItem(storageKey, JSON.stringify({ conversationId, messages: history.slice(-200) })); }
  catch { /* A full or restricted browser store should not prevent chatting. */ }
}

function render() {
  messages.replaceChildren();
  for (const message of history) {
    const article = document.createElement("article");
    article.className = `message ${message.role}`;
    article.setAttribute("aria-label", message.role === "user" ? "You" : "Agent");
    if (message.role === "assistant") {
      const label = document.createElement("div");
      label.className = "message-label";
      label.textContent = "✳ Lab";
      article.append(label);
    }
    const body = document.createElement("div");
    body.className = "message-body";
    if (message.role === "assistant") body.append(renderMarkdown(message.content));
    else body.textContent = message.content;
    article.append(body);
    messages.append(article);
  }
  welcome.hidden = history.length > 0;
  messages.hidden = history.length === 0;
}

function resize() { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 210)}px`; }
function updateControls() {
  send.disabled = busy || !input.value.trim();
  input.disabled = busy;
  newChat.disabled = busy;
  form.setAttribute("aria-busy", String(busy));
}
function scrollToEnd() { window.scrollTo({ top: document.body.scrollHeight, behavior: "instant" }); }

input.addEventListener("input", () => { resize(); updateControls(); });
input.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); if (!send.disabled) form.requestSubmit(); }
});

document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => {
  input.value = button.dataset.prompt;
  resize(); updateControls(); input.focus();
}));

newChat.addEventListener("click", () => {
  if (busy) return;
  conversationId = null; history = []; input.value = "";
  error.hidden = true; status.textContent = "";
  save(); render(); resize(); updateControls(); input.focus();
  window.scrollTo(0, 0);
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || busy) return;
  busy = true; input.value = "";
  error.hidden = true;
  status.textContent = "Thinking… Some analyses can take a few minutes.";
  status.classList.add("busy");
  history.push({ role: "user", content: message });
  render(); resize(); updateControls(); scrollToEnd();
  try {
    const response = await fetch("/agent", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversationId }),
      signal: AbortSignal.timeout(900000),
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) throw new Error(typeof result?.detail === "string" ? result.detail : `Request failed (${response.status}). Please try again.`);
    if (typeof result?.response !== "string" || !Number.isInteger(result.conversation_id) || result.conversation_id < 1) throw new Error("The server returned an unexpected response. Please try again.");
    conversationId = result.conversation_id;
    history.push({ role: "assistant", content: result.response });
    save();
  } catch (failure) {
    history.pop();
    input.value = message;
    error.textContent = failure.name === "TimeoutError" ? "The request timed out. The server may still be processing it; wait before trying again." : failure.message;
    error.hidden = false;
  } finally {
    busy = false; status.textContent = ""; status.classList.remove("busy");
    render(); resize(); updateControls(); input.focus(); scrollToEnd();
  }
});

render(); updateControls();
