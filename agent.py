import os, re, json, time, sqlite3, smtplib, hashlib, threading, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from agents import Agent, Runner, WebSearchTool

BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = BASE_DIR / "reports"
DB_FILE = BASE_DIR / "bazyan.db"
REPORT_DIR.mkdir(exist_ok=True)

EMAIL_ADDRESS = "nirouiapple@gmail.com"
EMAIL_PASSWORD = os.environ.get("BAZYAN_EMAIL_APP_PASSWORD")

WHATSAPP_TOKEN = os.environ.get("BAZYAN_WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("BAZYAN_WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_TO = os.environ.get("BAZYAN_WHATSAPP_TO", "")
WHATSAPP_GRAPH_VERSION = os.environ.get("BAZYAN_WHATSAPP_GRAPH_VERSION", "v23.0")

RUN_INTERVAL_HOURS = float(os.environ.get("BAZYAN_RUN_INTERVAL_HOURS", "24"))
ALERT_MIN_SCORE = int(os.environ.get("BAZYAN_ALERT_MIN_SCORE", "80"))
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = int(os.environ.get("PORT", "8787"))

instructions = r"""
You are BAZYAN AI, a professional business intelligence and market
research agent focused on REAL commercial opportunities in Iraq.

Research Iraq broadly: Erbil, Sulaymaniyah, Duhok, Baghdad, Basra,
Mosul/Nineveh, Kirkuk, Najaf, Karbala, Anbar, Babil, Diyala, Wasit,
Salah al-Din, Maysan, Dhi Qar, Qadisiyah, Muthanna.

Consider ALL legitimate sectors: agriculture, food, food processing,
restaurants, dairy, logistics, warehousing, cold chain, e-commerce,
retail, B2B services, construction, building materials, real estate,
healthcare, education, energy, solar, batteries, water, waste,
recycling, manufacturing, import substitution, automotive, tourism,
hospitality, technology, software, AI, professional services,
industrial services, trading, distribution and other sectors with
evidence of demand.

Use current reliable web sources. Prefer Iraqi government/KRG sources,
Central Bank, ministries, World Bank, IMF, UN/FAO/IFC, credible
companies and reputable news/trade data. Distinguish VERIFIED FACT
from ESTIMATE / ASSUMPTION. Never fabricate sources, competitors or
statistics.

Find at least 10 serious opportunities, preferably 12–15. For each:
name, best location, sector, problem, demand evidence, target
customers, solution, why now, real competitors, competition level,
competitive advantage, revenue model, startup cost range, revenue
potential, profit potential, break-even estimate, first customers,
risks, regulatory requirements, scalability, and score /100.

Scoring: demand 20, profit potential 15, startup affordability 15,
competition 10, speed to first customer 10, scalability 10, local
advantage 10, risk/regulatory ease 10.

Rank at least 10. Select BEST 3. Select ONE opportunity to validate
first. Give a low-cost validation test and the first 10 concrete
actions.

For monitoring, compare today's findings with previous reports:
NEW opportunities; stronger/weaker opportunities; new demand evidence;
new competitors; new regulations; new investment announcements;
important market changes; opportunities no longer attractive.

At the beginning write exactly:
ALERT_LEVEL: LOW or MEDIUM or HIGH
TOP_OPPORTUNITY: ...
TOP_LOCATION: ...
TOP_SCORE: ...

Use HIGH only when evidence is strong and a realistic low-risk next
step exists. Do not recommend large investment immediately.

End with SOURCES and explain what each important source supports.
Return one complete report.
"""

agent = Agent(
    name="Bazyan AI",
    instructions=instructions,
    tools=[WebSearchTool(search_context_size="high", external_web_access=True)],
)

def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        alert_level TEXT,
        top_opportunity TEXT,
        top_location TEXT,
        top_score INTEGER,
        report_path TEXT,
        report_hash TEXT UNIQUE,
        report TEXT NOT NULL,
        error TEXT
    );
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        channel TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        status TEXT NOT NULL,
        details TEXT,
        FOREIGN KEY(run_id) REFERENCES runs(id)
    );
    """)
    con.commit()
    con.close()

def marker(report, name, default=""):
    m = re.search(rf"(?im)^\s*{re.escape(name)}\s*:\s*(.+?)\s*$", report)
    return m.group(1).strip() if m else default

def score(report):
    m = re.search(r"\d{1,3}", marker(report, "TOP_SCORE", "0"))
    return int(m.group()) if m else 0

def previous_reports(limit=3):
    con = db()
    rows = con.execute(
        "SELECT started_at, report FROM runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    out = []
    for r in reversed(rows):
        text = r["report"]
        if len(text) > 14000:
            text = text[:14000]
        out.append(f"\n--- PREVIOUS REPORT {r['started_at']} ---\n{text}")
    return "\n".join(out)

def save_report(report):
    path = REPORT_DIR / f"bazyan_report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    path.write_text(report, encoding="utf-8")
    return path

def send_email(subject, body):
    if not EMAIL_PASSWORD:
        return False, "BAZYAN_EMAIL_APP_PASSWORD is not configured."
    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            s.sendmail(EMAIL_ADDRESS, EMAIL_ADDRESS, msg.as_string())
        return True, "EMAIL SENT SUCCESSFULLY."
    except Exception as e:
        return False, f"EMAIL ERROR: {e}"

def send_whatsapp(text):
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_TO):
        return False, "WhatsApp is not configured."
    url = f"https://graph.facebook.com/{WHATSAPP_GRAPH_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": WHATSAPP_TO,
        "type": "text",
        "text": {"body": text[:4000]}
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"WhatsApp HTTP {e.code}: {e.read().decode(errors='replace')}"
    except Exception as e:
        return False, f"WhatsApp ERROR: {e}"

def log_alert(run_id, channel, status, details):
    con = db()
    con.execute(
        "INSERT INTO alerts(run_id,channel,sent_at,status,details) VALUES(?,?,?,?,?)",
        (run_id, channel, datetime.now(timezone.utc).isoformat(), status, details)
    )
    con.commit()
    con.close()

def run_once():
    started = datetime.now(timezone.utc).isoformat()
    prior = previous_reports(3)
    task = f"""
Run a NEW comprehensive Iraqi business-opportunity monitoring report.
Search current web information. Find at least 10 serious opportunities,
rank them, choose the best 3, and choose one low-cost validation test.
Compare today's findings with the previous reports below. Avoid blindly
repeating old opportunities.

{prior}
"""
    print("\n" + "="*70)
    print("BAZYAN AI — AUTOMATIC RESEARCH")
    print("="*70)
    print("Dashboard: http://127.0.0.1:%d" % DASHBOARD_PORT)
    print("Searching current Iraqi opportunities...\n")
    try:
        result = Runner.run_sync(agent, task, max_turns=30)
        report = result.final_output
        path = save_report(report)
        digest = hashlib.sha256(report.encode()).hexdigest()
        alert = marker(report, "ALERT_LEVEL", "LOW").upper()
        top = marker(report, "TOP_OPPORTUNITY", "Unknown")
        location = marker(report, "TOP_LOCATION", "Unknown")
        top_score = score(report)

        con = db()
        cur = con.execute(
            """INSERT OR IGNORE INTO runs
            (started_at,finished_at,alert_level,top_opportunity,top_location,
             top_score,report_path,report_hash,report)
             VALUES (?,?,?,?,?,?,?,?,?)""",
            (started, datetime.now(timezone.utc).isoformat(), alert, top,
             location, top_score, str(path), digest, report)
        )
        con.commit()
        run_id = cur.lastrowid
        if not run_id:
            run_id = con.execute("SELECT id FROM runs WHERE report_hash=?", (digest,)).fetchone()["id"]
        con.close()

        print("\n" + "="*70)
        print("BAZYAN AI RESULT")
        print("="*70)
        print(report)
        print("\n" + "="*70)

        if alert == "HIGH" or top_score >= ALERT_MIN_SCORE:
            subject = f"BAZYAN AI — {alert} Opportunity Alert ({top_score}/100)"
            body = f"BAZYAN AI ALERT\n\nOpportunity: {top}\nLocation: {location}\nScore: {top_score}/100\nAlert: {alert}\n\nFull report:\n\n{report}"
            ok, detail = send_email(subject, body)
            log_alert(run_id, "email", "sent" if ok else "failed", detail)
            print(detail)

            wa = f"🚨 BAZYAN AI\nOpportunity: {top}\nLocation: {location}\nScore: {top_score}/100\nAlert: {alert}\n\nCheck your email for the full report."
            ok, detail = send_whatsapp(wa)
            log_alert(run_id, "whatsapp", "sent" if ok else "not_configured/failed", detail)
            print(detail)
        else:
            print("No high-priority alert this run.")
    except Exception as e:
        print("BAZYAN ERROR:", e)

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/report/"):
            try:
                rid = int(self.path.split("/")[-1])
            except ValueError:
                self.send_error(404); return
            con = db()
            row = con.execute("SELECT report FROM runs WHERE id=?", (rid,)).fetchone()
            con.close()
            if not row:
                self.send_error(404); return
            data = row["report"].encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        con = db()
        runs = con.execute(
            "SELECT id,started_at,alert_level,top_opportunity,top_location,top_score FROM runs ORDER BY id DESC LIMIT 30"
        ).fetchall()
        alerts = con.execute(
            "SELECT run_id,channel,sent_at,status,details FROM alerts ORDER BY id DESC LIMIT 30"
        ).fetchall()
        con.close()
        rows = "".join(
            f"<tr><td>{r['id']}</td><td>{r['started_at']}</td><td>{r['alert_level']}</td>"
            f"<td>{r['top_opportunity']}</td><td>{r['top_location']}</td><td>{r['top_score']}</td>"
            f"<td><a href='/report/{r['id']}'>Open</a></td></tr>" for r in runs
        )
        alerts_text = json.dumps([dict(a) for a in alerts], ensure_ascii=False, indent=2)
        html = f"""<!doctype html><html><head><meta charset=utf-8>
<title>BAZYAN AI Dashboard</title>
<style>body{{font-family:Arial;margin:30px;background:#f5f5f5}}.card{{background:#fff;padding:20px;margin:20px 0;border-radius:10px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}pre{{white-space:pre-wrap}}</style>
</head><body><div class=card><h1>BAZYAN AI Dashboard</h1><p>Automatic Iraq opportunity monitor</p></div>
<div class=card><h2>Recent Runs</h2><table><tr><th>ID</th><th>Time</th><th>Alert</th><th>Opportunity</th><th>Location</th><th>Score</th><th>Report</th></tr>
{rows or '<tr><td colspan=7>No runs yet.</td></tr>'}</table></div>
<div class=card><h2>Recent Alerts</h2><pre>{alerts_text}</pre></div></body></html>"""
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args): pass

def dashboard_server():
    ThreadingHTTPServer((DASHBOARD_HOST, DASHBOARD_PORT), DashboardHandler).serve_forever()

def main():
    init_db()
    threading.Thread(target=dashboard_server, daemon=True).start()
    while True:
        run_once()
        print(f"\nNext automatic run in {RUN_INTERVAL_HOURS:g} hours.")
        time.sleep(max(1, int(RUN_INTERVAL_HOURS * 3600)))

if __name__ == "__main__":
    main()
