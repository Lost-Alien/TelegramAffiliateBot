"""
TechSelect Bot — Cookie Deploy Dashboard
=========================================
Local web dashboard to update X (Twitter) cookies and deploy to EC2.

Usage:
    python dashboard/deploy_dashboard.py

Opens at: http://localhost:7777
"""
import http.server
import json
import os
import re
import subprocess
import threading
import urllib.parse
import webbrowser
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
DASHBOARD_PORT = 7777
ENV_FILE = Path(__file__).parent.parent / "TelegramDealAutoPoster" / ".env"
EC2_HOST = "ubuntu@13.239.243.61"
EC2_REMOTE_ENV = "/opt/telegrambot/app/TelegramDealAutoPoster/.env"
EC2_REMOTE_XPOSTER = "/opt/telegrambot/app/TelegramDealAutoPoster/x_poster.py"
EC2_CONTAINER = "telegram_deal_poster"
GITHUB_REPO = "https://github.com/Lost-Alien/TelegramAffiliateBot.git"

SSH_KEYS = [
    str(Path(__file__).parent.parent / "TelegramBot-key.pem"),  # Primary EC2 key
    str(Path.home() / ".ssh" / "id_ed25519"),
    str(Path.home() / ".ssh" / "wabotkey-new"),
    str(Path.home() / ".ssh" / "id_rsa"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def find_ssh_key():
    for key in SSH_KEYS:
        if Path(key).exists():
            return key
    return None


def update_env_var(env_path: Path, key: str, value: str) -> bool:
    """Update or insert a KEY=value line in the .env file."""
    if not env_path.exists():
        return False
    content = env_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    new_line = f'{key}={value}'
    if pattern.search(content):
        content = pattern.sub(new_line, content)
    else:
        content = content.rstrip("\n") + f"\n{new_line}\n"
    env_path.write_text(content, encoding="utf-8")
    return True


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Run a shell command, return (success, output)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def deploy_cookies(auth_token: str, ct0: str) -> list[dict]:
    """Full deploy pipeline. Returns list of step results."""
    steps = []

    # Step 1: Update local .env
    ok1 = update_env_var(ENV_FILE, "TWITTER_AUTH_TOKEN", auth_token)
    ok2 = update_env_var(ENV_FILE, "TWITTER_CT0", ct0)
    steps.append({
        "name": "Update local .env",
        "ok": ok1 and ok2,
        "detail": f"{ENV_FILE}"
    })

    ssh_key = find_ssh_key()

    # Step 2: SCP .env to EC2
    if ssh_key:
        scp_cmd = [
            "scp", "-i", ssh_key,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            str(ENV_FILE),
            f"{EC2_HOST}:{EC2_REMOTE_ENV}",
        ]
        ok, out = run_cmd(scp_cmd, timeout=20)
        steps.append({"name": "SCP .env → EC2", "ok": ok, "detail": out or "Done"})

        # Step 2b: SCP x_poster.py to EC2 (XActions engine)
        xposter_local = str(ENV_FILE.parent / "x_poster.py")
        scp_xp = [
            "scp", "-i", ssh_key,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            xposter_local,
            f"{EC2_HOST}:{EC2_REMOTE_XPOSTER}",
        ]
        ok_xp, out_xp = run_cmd(scp_xp, timeout=20)
        steps.append({"name": "SCP x_poster.py → EC2", "ok": ok_xp, "detail": out_xp or "Done"})

        # Step 3: Docker restart on EC2
        restart_cmd = [
            "ssh", "-i", ssh_key,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            EC2_HOST,
            f"docker restart {EC2_CONTAINER}",
        ]
        ok3, out3 = run_cmd(restart_cmd, timeout=30)
        steps.append({"name": f"Restart Docker ({EC2_CONTAINER})", "ok": ok3, "detail": out3 or "Done"})
    else:
        steps.append({"name": "SCP .env → EC2", "ok": False,
                       "detail": "No SSH key found. Add your key to ~/.ssh/"})
        steps.append({"name": "Restart Docker", "ok": False,
                       "detail": "Skipped — SSH not available"})

    # Step 4: Commit & push x_poster.py to GitHub
    git_dir = ENV_FILE.parent.parent
    ok_add, _ = run_cmd(["git", "-C", str(git_dir), "add", "-A"])
    ok_commit, commit_out = run_cmd([
        "git", "-C", str(git_dir),
        "commit",
        "--author=abs6187 <23f2000876@ds.study.iitm.ac.in>",
        "-m", "chore: update X cookie credentials via deploy dashboard",
        "--allow-empty",
    ])
    ok_push, push_out = run_cmd(["git", "-C", str(git_dir), "push", "origin", "main"], timeout=30)
    steps.append({
        "name": "Git push → GitHub",
        "ok": ok_push,
        "detail": push_out or commit_out or "Done"
    })

    return steps


# ── HTML Template ─────────────────────────────────────────────────────────────

def render_html(result_json: str = "null") -> str:
    ssh_key = find_ssh_key() or "❌ Not found (add key to ~/.ssh/)"
    env_exists = "✅" if ENV_FILE.exists() else "❌ Missing"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TechSelect Bot — Deploy Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0d1117;
    --surface: #161b22;
    --surface2: #21262d;
    --border: #30363d;
    --accent: #238636;
    --accent-hover: #2ea043;
    --danger: #da3633;
    --warn: #e3b341;
    --text: #e6edf3;
    --muted: #8b949e;
    --blue: #388bfd;
    --purple: #a371f7;
    --cyan: #39d353;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    min-height: 100vh;
    padding: 2rem 1rem;
  }}
  .container {{ max-width: 780px; margin: 0 auto; }}

  /* Header */
  .header {{
    display: flex; align-items: center; gap: 1rem;
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
  }}
  .logo {{
    width: 48px; height: 48px;
    background: linear-gradient(135deg, #1d9bf0, #a855f7);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem;
  }}
  .header h1 {{ font-size: 1.5rem; font-weight: 700; }}
  .header p {{ font-size: 0.85rem; color: var(--muted); margin-top: 2px; }}
  .badge {{
    margin-left: auto;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.75rem;
    color: var(--cyan);
  }}

  /* Status bar */
  .status-grid {{
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 0.75rem; margin-bottom: 2rem;
  }}
  .status-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem;
  }}
  .status-card .label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
  .status-card .value {{ font-size: 0.9rem; font-weight: 500; font-family: 'JetBrains Mono', monospace; }}

  /* Form card */
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }}
  .card h2 {{
    font-size: 1rem; font-weight: 600; margin-bottom: 0.25rem;
    display: flex; align-items: center; gap: 0.5rem;
  }}
  .card .desc {{ font-size: 0.82rem; color: var(--muted); margin-bottom: 1.5rem; }}

  .field {{ margin-bottom: 1.25rem; }}
  .field label {{
    display: block; font-size: 0.8rem; font-weight: 500;
    margin-bottom: 0.5rem; color: var(--text);
  }}
  .field label span {{ color: var(--muted); font-weight: 400; margin-left: 6px; }}
  .field textarea, .field input {{
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    padding: 0.75rem 1rem;
    resize: vertical;
    transition: border-color 0.2s;
    outline: none;
  }}
  .field textarea:focus, .field input:focus {{
    border-color: var(--blue);
    box-shadow: 0 0 0 3px rgba(56,139,253,0.1);
  }}
  .field textarea {{ min-height: 60px; }}

  .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}

  .help {{
    font-size: 0.75rem; color: var(--muted);
    margin-top: 0.4rem;
    display: flex; align-items: center; gap: 4px;
  }}

  /* Button */
  .btn-deploy {{
    width: 100%;
    background: linear-gradient(135deg, var(--accent), #1a7f37);
    border: none;
    border-radius: 8px;
    color: #fff;
    cursor: pointer;
    font-size: 1rem;
    font-weight: 600;
    padding: 0.85rem;
    transition: all 0.2s;
    display: flex; align-items: center; justify-content: center; gap: 0.5rem;
  }}
  .btn-deploy:hover {{ background: linear-gradient(135deg, var(--accent-hover), #2ea043); transform: translateY(-1px); box-shadow: 0 4px 16px rgba(35,134,54,0.4); }}
  .btn-deploy:active {{ transform: translateY(0); }}
  .btn-deploy:disabled {{ opacity: 0.5; cursor: not-allowed; transform: none; }}

  /* Steps guide */
  .steps {{ list-style: none; }}
  .steps li {{
    display: flex; align-items: flex-start; gap: 0.75rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.85rem;
  }}
  .steps li:last-child {{ border-bottom: none; }}
  .step-num {{
    min-width: 24px; height: 24px;
    background: var(--surface2);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.7rem; font-weight: 600; color: var(--blue);
    border: 1px solid var(--blue);
  }}
  .step-text {{ line-height: 1.5; }}
  .step-text code {{
    background: var(--surface2);
    padding: 1px 6px; border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem; color: var(--purple);
  }}

  /* Results */
  #results {{ display: none; }}
  .result-item {{
    display: flex; align-items: flex-start; gap: 0.75rem;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-bottom: 0.5rem;
    background: var(--surface2);
    border: 1px solid var(--border);
    animation: fadeIn 0.3s ease;
  }}
  .result-item.ok {{ border-color: rgba(35,134,54,0.4); background: rgba(35,134,54,0.08); }}
  .result-item.fail {{ border-color: rgba(218,54,51,0.4); background: rgba(218,54,51,0.08); }}
  .result-icon {{ font-size: 1.1rem; margin-top: 1px; }}
  .result-name {{ font-size: 0.85rem; font-weight: 600; }}
  .result-detail {{ font-size: 0.75rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; margin-top: 2px; word-break: break-all; }}

  .spinner {{
    width: 18px; height: 18px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    display: inline-block;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}

  footer {{ text-align: center; color: var(--muted); font-size: 0.75rem; margin-top: 2rem; }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <div class="logo">🤖</div>
    <div>
      <h1>TechSelect Deploy Dashboard</h1>
      <p>Cookie update &amp; EC2 deployment control panel</p>
    </div>
    <div class="badge">● Live</div>
  </div>

  <div class="status-grid">
    <div class="status-card">
      <div class="label">Local .env</div>
      <div class="value">{env_exists} {ENV_FILE.name}</div>
    </div>
    <div class="status-card">
      <div class="label">SSH Key</div>
      <div class="value" style="font-size:0.78rem">{ssh_key}</div>
    </div>
    <div class="status-card">
      <div class="label">EC2 Host</div>
      <div class="value">{EC2_HOST}</div>
    </div>
    <div class="status-card">
      <div class="label">Docker Container</div>
      <div class="value">{EC2_CONTAINER}</div>
    </div>
  </div>

  <!-- How to get cookies -->
  <div class="card">
    <h2>📋 How to get your X.com cookies</h2>
    <p class="desc">Takes 30 seconds. Do this when logged in to <strong>@techselect_blog</strong> on x.com</p>
    <ol class="steps">
      <li>
        <div class="step-num">1</div>
        <div class="step-text">Go to <strong>x.com</strong> in Chrome/Edge and make sure you're logged in as <code>@techselect_blog</code></div>
      </li>
      <li>
        <div class="step-num">2</div>
        <div class="step-text">Press <code>F12</code> (DevTools) → click <strong>Application</strong> tab → expand <strong>Cookies</strong> → click <code>https://x.com</code></div>
      </li>
      <li>
        <div class="step-num">3</div>
        <div class="step-text">Find <code>auth_token</code> — copy the long value (~40 chars) and paste below</div>
      </li>
      <li>
        <div class="step-num">4</div>
        <div class="step-text">Find <code>ct0</code> — copy the long value (~160 chars) and paste below</div>
      </li>
      <li>
        <div class="step-num">5</div>
        <div class="step-text">Click <strong>🚀 Deploy Cookies to EC2</strong> — done!</div>
      </li>
    </ol>
  </div>

  <!-- Cookie form -->
  <div class="card">
    <h2>🍪 Paste X.com Cookies</h2>
    <p class="desc">These are your browser session cookies from x.com. They expire roughly every 30 days.</p>
    <form id="cookieForm">
      <div class="field">
        <label>auth_token <span>from Application → Cookies → x.com</span></label>
        <input type="text" id="auth_token" name="auth_token" placeholder="Paste auth_token value here (~40 chars)" autocomplete="off" spellcheck="false" required />
        <div class="help">💡 Looks like: <code>abc123def456...</code></div>
      </div>
      <div class="field">
        <label>ct0 (CSRF token) <span>same Cookies panel</span></label>
        <textarea id="ct0" name="ct0" placeholder="Paste ct0 value here (~160 chars)" autocomplete="off" spellcheck="false" required></textarea>
        <div class="help">💡 Looks like: <code>89cc1e083fc1ff86dc503b...</code></div>
      </div>
      <button type="submit" class="btn-deploy" id="deployBtn">
        🚀 Deploy Cookies to EC2
      </button>
    </form>
  </div>

  <!-- Results -->
  <div id="results">
    <div class="card">
      <h2>⚙️ Deployment Progress</h2>
      <p class="desc" id="resultSummary">Running...</p>
      <div id="stepsList"></div>
    </div>
  </div>

  <footer>TechSelect Bot Deploy Dashboard · Running on localhost:{DASHBOARD_PORT}</footer>

</div>

<script>
const form = document.getElementById('cookieForm');
const btn = document.getElementById('deployBtn');
const resultsDiv = document.getElementById('results');
const stepsList = document.getElementById('stepsList');
const resultSummary = document.getElementById('resultSummary');

form.addEventListener('submit', async (e) => {{
  e.preventDefault();
  const auth_token = document.getElementById('auth_token').value.trim();
  const ct0 = document.getElementById('ct0').value.trim();

  if (!auth_token || !ct0) {{
    alert('Both auth_token and ct0 are required!');
    return;
  }}

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Deploying...';
  resultsDiv.style.display = 'block';
  stepsList.innerHTML = '<div style="color:#8b949e;font-size:0.85rem;padding:0.5rem">⏳ Running deployment pipeline...</div>';
  resultSummary.textContent = 'Deploying to EC2...';
  window.scrollTo({{ top: document.body.scrollHeight, behavior: 'smooth' }});

  try {{
    const res = await fetch('/deploy', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ auth_token, ct0 }})
    }});
    const data = await res.json();

    stepsList.innerHTML = '';
    let allOk = true;
    for (const step of data.steps) {{
      if (!step.ok) allOk = false;
      const div = document.createElement('div');
      div.className = 'result-item ' + (step.ok ? 'ok' : 'fail');
      div.innerHTML = `
        <div class="result-icon">${{step.ok ? '✅' : '❌'}}</div>
        <div>
          <div class="result-name">${{step.name}}</div>
          <div class="result-detail">${{step.detail}}</div>
        </div>
      `;
      stepsList.appendChild(div);
    }}

    resultSummary.textContent = allOk
      ? '🎉 All steps completed! Bot is live with new cookies.'
      : '⚠️ Some steps failed — check details above.';
    resultSummary.style.color = allOk ? '#39d353' : '#e3b341';

    btn.disabled = false;
    btn.innerHTML = allOk ? '✅ Deployed! Deploy Again' : '🔄 Retry Deploy';

  }} catch (err) {{
    stepsList.innerHTML = `<div class="result-item fail"><div class="result-icon">❌</div><div><div class="result-name">Request failed</div><div class="result-detail">${{err.message}}</div></div></div>`;
    resultSummary.textContent = 'Deployment failed — see error above.';
    btn.disabled = false;
    btn.innerHTML = '🔄 Retry';
  }}
}});
</script>
</body>
</html>"""


# ── HTTP Server ───────────────────────────────────────────────────────────────

class DashboardHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Silence default request log

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = render_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(html))
            self.end_headers()
            self.wfile.write(html)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/deploy":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body)
                auth_token = data.get("auth_token", "").strip()
                ct0 = data.get("ct0", "").strip()

                if not auth_token or not ct0:
                    self._json({"error": "auth_token and ct0 required"}, 400)
                    return

                print(f"[Dashboard] Deploying cookies (auth_token={auth_token[:8]}...)")
                steps = deploy_cookies(auth_token, ct0)
                self._json({"steps": steps})

            except Exception as e:
                self._json({"error": str(e)}, 500)
        else:
            self.send_response(404)
            self.end_headers()

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════════╗
║      TechSelect Bot — Cookie Deploy Dashboard        ║
╠══════════════════════════════════════════════════════╣
║  URL  : http://localhost:{DASHBOARD_PORT}                     ║
║  .env : {str(ENV_FILE)[:45]:<45}  ║
║  EC2  : {EC2_HOST:<45}  ║
╚══════════════════════════════════════════════════════╝

Opening browser...
""")

    server = http.server.HTTPServer(("127.0.0.1", DASHBOARD_PORT), DashboardHandler)
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{DASHBOARD_PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
