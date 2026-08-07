#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");

let data = {};

try {
  const raw = fs.readFileSync(0, "utf8");
  if (raw.trim()) data = JSON.parse(raw);
} catch {
  process.stdout.write("{}");
  process.exit(0);
}

let prompt = data.prompt || data.user_prompt || "";

if (!prompt) {
  const messages = data.llm_request?.messages || [];
  const users = messages.filter((message) => message?.role === "user");
  const content = users.at(-1)?.content;

  if (typeof content === "string") {
    prompt = content;
  } else if (Array.isArray(content)) {
    prompt = content
      .filter((part) => part && typeof part === "object")
      .map((part) => part.text || "")
      .join("");
  }
}

if (prompt) {
  const root = data.cwd || data.project_dir || process.cwd();
  const session = String(data.session_id || "unknown").slice(0, 8);
  const now = new Date();
  const date = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  const time = [
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0"),
  ].join(":");
  const logDir = path.join(root, "proc", "archive", "prompts");
  const logFile = path.join(logDir, `${date}.md`);

  fs.mkdirSync(logDir, { recursive: true });
  fs.appendFileSync(logFile, `\n## ${time} | session: ${session}\n${prompt}\n`, "utf8");
}

process.stdout.write("{}");
