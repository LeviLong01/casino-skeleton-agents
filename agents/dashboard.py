"""Local observability dashboard for the agent layer.

A stdlib-only HTTP server: serves one page at / that polls a small JSON API
parsing agents/activity.log into typed events (commit, anomaly, error, tool
call, idle check, ...). No new dependency, and it only *reads* the log --
never touches git -- so it's safe to run alongside the orchestrator (or the
Test Writer Agent's hook, if that comes back) at any time, from any state.

This is deliberately the simplest thing that could work: a page that polls a
JSON endpoint. The API is already the right seam to grow from later --
swap the poll for a websocket push, or add a panel that reads MLflow traces
alongside the log, without changing where the log data comes from.

    python3 -m agents.dashboard
"""
import json
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from agents.common import ACTIVITY_LOG

PORT = 8765
LOG_LINE_RE = re.compile(r"^\[(?P<ts>[^\]]+)\] \[(?P<agent>[^\]]+)\] (?P<msg>.*)$", re.DOTALL)


def classify(message: str) -> str:
    lower = message.lower()
    if lower.startswith("anomaly "):
        return "anomaly"
    if "traceback" in lower or "verification failed" in lower or "tick failed" in lower or lower.startswith("error"):
        return "error"
    if "committed" in lower or "filed incident report" in lower:
        return "commit"
    if "scope guard" in lower:
        return "guard"
    if "tool call" in lower:
        return "tool"
    if (
        "no action" in lower
        or "within normal range" in lower
        or "no structural change" in lower
        or "no new outcomes" in lower
        or "deferring analysis" in lower
        or "anomaly persists" in lower
    ):
        return "idle"
    return "info"


def parse_log(limit=500):
    if not ACTIVITY_LOG.exists():
        return []
    lines = ACTIVITY_LOG.read_text().splitlines()[-limit:]
    events = []
    for line in lines:
        match = LOG_LINE_RE.match(line)
        if not match:
            continue
        message = match.group("msg")
        events.append(
            {
                "ts": match.group("ts"),
                "agent": match.group("agent"),
                "message": message,
                "type": classify(message),
            }
        )
    events.reverse()
    return events


def build_summary(events):
    by_agent = Counter(e["agent"] for e in events)
    by_type = Counter(e["type"] for e in events)
    return {"by_agent": by_agent, "by_type": by_type, "total": len(events)}


PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Casino Agent Layer</title>
<style>
  :root {
    --bg: #0b0e14; --panel: #12161f; --border: #232838; --text: #dfe4ee;
    --dim: #7a8296; --accent: #5eead4;
    --commit: #4ade80; --anomaly: #f87171; --error: #fb923c;
    --guard: #60a5fa; --tool: #c084fc; --idle: #4b5262; --info: #9ca3af;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 13px;
  }
  header {
    display: flex; align-items: center; gap: 14px;
    padding: 14px 20px; border-bottom: 1px solid var(--border);
    background: var(--panel); position: sticky; top: 0; z-index: 2;
  }
  h1 { font-size: 15px; font-weight: 600; margin: 0; letter-spacing: 0.2px; }
  .live { display: flex; align-items: center; gap: 6px; color: var(--commit); font-size: 12px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--commit); animation: pulse 1.6s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.25; } }
  select {
    background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 5px 8px; font-family: inherit; font-size: 12px;
  }
  .spacer { flex: 1; }
  .stats { display: flex; gap: 8px; padding: 12px 20px; flex-wrap: wrap; border-bottom: 1px solid var(--border); }
  .chip {
    background: var(--panel); border: 1px solid var(--border); border-radius: 999px;
    padding: 5px 12px; font-size: 12px; color: var(--dim); display: flex; gap: 6px; align-items: center;
  }
  .chip b { color: var(--text); font-weight: 600; }
  .chip.commit b { color: var(--commit); } .chip.anomaly b { color: var(--anomaly); } .chip.error b { color: var(--error); }
  main { max-width: 980px; margin: 0 auto; padding: 8px 20px 60px; }
  .row {
    display: grid; grid-template-columns: 90px 150px 1fr; gap: 12px;
    padding: 8px 10px; border-left: 3px solid var(--idle); border-radius: 4px;
    margin: 3px 0; align-items: baseline; animation: fadein 0.35s ease;
  }
  @keyframes fadein { from { opacity: 0; transform: translateY(-3px);} to { opacity: 1; transform: none; } }
  .row:hover { background: var(--panel); }
  .ts { color: var(--dim); font-size: 11px; }
  .agent { font-size: 12px; font-weight: 600; }
  .msg { white-space: pre-wrap; word-break: break-word; color: var(--text); }
  .row.commit { border-left-color: var(--commit); } .row.commit .agent { color: var(--commit); }
  .row.anomaly { border-left-color: var(--anomaly); } .row.anomaly .agent { color: var(--anomaly); }
  .row.error { border-left-color: var(--error); } .row.error .agent { color: var(--error); }
  .row.guard { border-left-color: var(--guard); } .row.guard .agent { color: var(--guard); }
  .row.tool { border-left-color: var(--tool); } .row.tool .agent { color: var(--tool); }
  .row.idle { border-left-color: var(--idle); } .row.idle .agent, .row.idle .msg { color: var(--dim); }
  .row.info { border-left-color: var(--info); }
  .empty { color: var(--dim); padding: 40px; text-align: center; }
</style>
</head>
<body>
<header>
  <h1>Casino Agent Layer &mdash; Live Activity</h1>
  <div class="live"><span class="dot"></span>live</div>
  <div class="spacer"></div>
  <select id="filter">
    <option value="">all agents</option>
  </select>
</header>
<div class="stats" id="stats"></div>
<main id="events"><div class="empty">waiting for events&hellip;</div></main>
<script>
let currentFilter = "";
const filterEl = document.getElementById("filter");
filterEl.addEventListener("change", () => { currentFilter = filterEl.value; render(lastData); });

let lastData = null;
let knownAgents = new Set();

function typeLabel(t) {
  return {anomaly: "ANOMALY", error: "ERROR", commit: "commit", guard: "guard", tool: "tool", idle: "idle", info: "info"}[t] || t;
}

function render(data) {
  if (!data) return;
  lastData = data;
  for (const a of Object.keys(data.summary.by_agent)) {
    if (!knownAgents.has(a)) {
      knownAgents.add(a);
      const opt = document.createElement("option");
      opt.value = a; opt.textContent = a;
      filterEl.appendChild(opt);
    }
  }

  const stats = document.getElementById("stats");
  const chips = [];
  for (const [agent, count] of Object.entries(data.summary.by_agent)) {
    chips.push(`<div class="chip">${agent} <b>${count}</b></div>`);
  }
  chips.push(`<div class="chip commit">commits <b>${data.summary.by_type.commit || 0}</b></div>`);
  chips.push(`<div class="chip anomaly">anomalies <b>${data.summary.by_type.anomaly || 0}</b></div>`);
  chips.push(`<div class="chip error">errors <b>${data.summary.by_type.error || 0}</b></div>`);
  stats.innerHTML = chips.join("");

  const events = currentFilter ? data.events.filter(e => e.agent === currentFilter) : data.events;
  const container = document.getElementById("events");
  if (!events.length) {
    container.innerHTML = '<div class="empty">no events yet&hellip;</div>';
    return;
  }
  container.innerHTML = events.slice(0, 300).map(e => `
    <div class="row ${e.type}">
      <div class="ts">${e.ts.replace('T',' ').replace('Z','')}</div>
      <div class="agent">${e.agent}</div>
      <div class="msg">${(e.type === 'anomaly' ? '🔴 ' : '') + escapeHtml(e.message)}</div>
    </div>`).join("");
}

function escapeHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function poll() {
  try {
    const res = await fetch("/api/activity?limit=500");
    render(await res.json());
  } catch (e) { /* server between ticks, ignore */ }
  setTimeout(poll, 1500);
}
poll();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # keep stdout quiet; this is a dashboard, not a request log

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/activity":
            limit = int(parse_qs(parsed.query).get("limit", ["500"])[0])
            events = parse_log(limit=limit)
            payload = json.dumps({"events": events, "summary": build_summary(events)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Casino agent activity dashboard: http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
