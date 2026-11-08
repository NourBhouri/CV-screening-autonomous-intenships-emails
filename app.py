"""Candidatures spontanées automatiques — envoi pendant les heures de bureau (Europe/Paris)."""
import csv, io, os, re, smtplib, sqlite3, threading, time
from datetime import datetime
from email.message import EmailMessage
from hmac import compare_digest
from zoneinfo import ZoneInfo

import requests
from flask import Flask, Response, jsonify, render_template, request

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE)
os.makedirs(DATA_DIR, exist_ok=True)
DB, CV_DIR = os.path.join(DATA_DIR, "data.db"), os.path.join(DATA_DIR, "uploads")
PARIS = ZoneInfo("Europe/Paris")
OPEN = [(9, 0, 12, 0), (14, 0, 17, 30)]  # Lun-Ven
os.makedirs(CV_DIR, exist_ok=True)
app = Flask(__name__)
state = {"running": False, "last": 0.0, "msg": "Arrêté", "prep": False}


@app.before_request
def require_render_auth():
    if request.path == "/healthz" or os.environ.get("RENDER") != "true":
        return None
    username, password = os.environ.get("APP_USERNAME"), os.environ.get("APP_PASSWORD")
    if not username or not password:
        return "Application authentication is not configured", 503
    auth = request.authorization
    if auth and auth.username and auth.password and compare_digest(auth.username, username) and compare_digest(auth.password, password):
        return None
    return Response("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="Candidatures Auto"'})

DEFAULTS = {
    "name": "", "email": "", "smtp_host": "smtp.gmail.com", "smtp_port": "587", "smtp_pass": "",
    "keywords": "intelligence artificielle, machine learning, data science", "about": "", "anthropic_key": "",
    "running": "0", "daily_cap": "25", "delay_min": "6", "cv": "",
    "subject": "Candidature spontanée – stage en IA – {name}",
    "body": ("Bonjour,\n\nÉtudiant en Master Machine Learning for Business Intelligence, je recherche un stage "
             "en IA. {company} m'intéresse particulièrement et je serais ravi de contribuer à vos projets.\n\n"
             "Vous trouverez mon CV en pièce jointe. Je reste disponible pour un échange.\n\nCordialement,\n{name}"),
}
FOOTER = "\n\n—\nSi vous ne souhaitez plus recevoir de message de ma part, répondez simplement « stop »."


def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c


def init():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT)")
        c.execute("""CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, company TEXT, email TEXT DEFAULT '',
                     city TEXT DEFAULT '', status TEXT DEFAULT 'pending', sent_at TEXT, error TEXT)""")
        for col in ("job_title", "job_url", "job_desc", "subject", "body"):
            try: c.execute(f"ALTER TABLE contacts ADD COLUMN {col} TEXT DEFAULT ''")
            except sqlite3.OperationalError: pass


def cfg():
    with db() as c:
        d = dict(DEFAULTS); d.update({r["k"]: r["v"] for r in c.execute("SELECT * FROM settings")}); return d


def is_open(now):
    if now.weekday() > 4: return False
    t = now.hour * 60 + now.minute
    return any(a * 60 + b <= t < c * 60 + d for a, b, c, d in OPEN)



SECRETS = ("smtp_pass", "anthropic_key")


def compose(s, company, job=None):
    """Objet + corps. Avec une offre et une clé Anthropic : message rédigé sur mesure, sinon modèle."""
    job = job or {}
    if s["anthropic_key"]:
        try:
            offre = (f"Offre : {job['job_title']}. Extrait : {(job.get('job_desc') or '')[:700]}\n" if job.get("job_title")
                     else "Pas d'offre précise : candidature spontanée adaptée à l'activité de cette entreprise.\n")
            prompt = ("Rédige en français un email de candidature (stage) de 110 à 140 mots, sobre et sincère.\n"
                      f"Candidat : {s['name']}. Profil (n'utilise QUE ces faits) : {s['about'] or 'étudiant en Master IA'}.\n"
                      f"Mots-clés visés : {s['keywords']}.\nEntreprise : {company}.\nVille : {job.get('city') or 'non précisée'}.\n"
                      + offre +
                      "Personnalise le message pour cette entreprise précise (nom, activité probable, ville, offre) et fais le lien "
                      "avec le profil, mentionne le CV en pièce jointe, aucune formule creuse, n'invente rien. "
                      "Format : première ligne « OBJET: ... », puis le corps.")
            r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                              headers={"x-api-key": s["anthropic_key"], "anthropic-version": "2023-06-01"},
                              json={"model": "claude-sonnet-4-6", "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]})
            t = r.json()["content"][0]["text"].strip()
            subj, _, body = t.partition("\n")
            return subj.replace("OBJET:", "").strip(), body.strip()
        except Exception:
            pass
    subj, body = s["subject"], s["body"]
    if job.get("job_title") and "{job_title}" not in body:
        body = body.replace("Bonjour,\n\n", "Bonjour,\n\nJe me permets de vous contacter au sujet de votre offre « {job_title} ».\n\n", 1)
    rep = {"{company}": company, "{name}": s["name"], "{job_title}": job.get("job_title") or "votre secteur",
           "{keywords}": s["keywords"]}
    for k, v in rep.items(): subj, body = subj.replace(k, v), body.replace(k, v)
    return subj, body


def clean(v):
    return "" if v is None or (isinstance(v, float) and v != v) else str(v)


def send(s, to, subj, body):
    m = EmailMessage()
    m["From"], m["To"] = f"{s['name']} <{s['email']}>", to
    m["Subject"] = subj
    m.set_content(body + FOOTER)
    if s["cv"] and os.path.exists(os.path.join(CV_DIR, s["cv"])):
        with open(os.path.join(CV_DIR, s["cv"]), "rb") as f:
            m.add_attachment(f.read(), maintype="application", subtype="pdf", filename=s["cv"])
    with smtplib.SMTP(s["smtp_host"], int(s["smtp_port"]), timeout=30) as sm:
        sm.starttls(); sm.login(s["email"], s["smtp_pass"]); sm.send_message(m)


def worker():
    while True:
        time.sleep(15)
        if not state["running"]: continue
        now, s = datetime.now(PARIS), cfg()
        if not is_open(now): state["msg"] = "En attente des heures de bureau (lun-ven 9h-12h / 14h-17h30)"; continue
        with db() as c:
            today = c.execute("SELECT COUNT(*) FROM contacts WHERE status='sent' AND sent_at LIKE ?",
                              (now.strftime("%Y-%m-%d") + "%",)).fetchone()[0]
            if today >= int(s["daily_cap"]): state["msg"] = "Quota du jour atteint"; continue
            if time.time() - state["last"] < int(s["delay_min"]) * 60: state["msg"] = "Pause entre deux envois"; continue
            row = c.execute("SELECT * FROM contacts WHERE status='pending' AND email!='' ORDER BY id LIMIT 1").fetchone()
            if not row: state["msg"] = "Aucun contact en attente avec un email"; continue
            try:
                subj, body = row["subject"], row["body"]
                if not body:  # pas encore préparé : on rédige puis on enregistre
                    subj, body = compose(s, row["company"], dict(row))
                    c.execute("UPDATE contacts SET subject=?, body=? WHERE id=?", (subj, body, row["id"]))
                send(s, row["email"], subj, body)
                c.execute("UPDATE contacts SET status='sent', sent_at=?, error=NULL WHERE id=?", (now.strftime("%Y-%m-%d %H:%M"), row["id"]))
                state["msg"] = f"Envoyé à {row['company']}"
            except Exception as e:
                c.execute("UPDATE contacts SET status='failed', error=? WHERE id=?", (str(e)[:200], row["id"]))
                state["msg"] = f"Échec : {e}"
            state["last"] = time.time()


@app.get("/")
def index(): return render_template("index.html")


@app.get("/healthz")
def healthz(): return jsonify(ok=True)


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        with db() as c:
            for k, v in request.json.items():
                if k in DEFAULTS and k != "cv": c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, str(v)))
    s = cfg()
    for k in SECRETS: s[k] = "••••••" if s[k] else ""
    return jsonify(s)


@app.post("/api/cv")
def cv():
    f = request.files.get("cv")
    if not f or not f.filename.lower().endswith(".pdf"): return jsonify(error="Choisis un fichier PDF"), 400
    name = re.sub(r"[^\w.\-]", "_", f.filename); f.save(os.path.join(CV_DIR, name))
    with db() as c: c.execute("INSERT OR REPLACE INTO settings VALUES('cv',?)", (name,))
    return jsonify(cv=name)


@app.get("/api/search")
def search():
    p = {"q": request.args.get("q", ""), "per_page": 25, "etat_administratif": "A"}
    if request.args.get("dept"): p["departement"] = request.args["dept"]
    r = requests.get("https://recherche-entreprises.api.gouv.fr/search", params=p, timeout=15).json()
    return jsonify([{"company": x["nom_complet"], "city": (x.get("siege") or {}).get("libelle_commune", "")} for x in r.get("results", [])])


@app.route("/api/contacts", methods=["GET", "POST"])
def contacts():
    with db() as c:
        if request.method == "POST":
            for x in request.json:
                c.execute("INSERT INTO contacts(company,email,city) VALUES(?,?,?)", (x["company"], x.get("email", ""), x.get("city", "")))
        return jsonify([dict(r) for r in c.execute("SELECT * FROM contacts ORDER BY id DESC")])


@app.post("/api/import")
def import_csv():  # colonnes : company,email,city
    txt = request.files["file"].read().decode("utf-8-sig")
    rows = [{"company": r.get("company") or r.get("entreprise") or "", "email": r.get("email", ""), "city": r.get("city", "")}
            for r in csv.DictReader(io.StringIO(txt))]
    with db() as c:
        for x in rows:
            if x["company"]: c.execute("INSERT INTO contacts(company,email,city) VALUES(?,?,?)", (x["company"], x["email"], x["city"]))
    return jsonify(n=len(rows))


@app.route("/api/contacts/<int:i>", methods=["PATCH", "DELETE"])
def contact(i):
    with db() as c:
        if request.method == "DELETE": c.execute("DELETE FROM contacts WHERE id=?", (i,))
        else: c.execute("UPDATE contacts SET email=?, status='pending', error=NULL WHERE id=?", (request.json["email"].strip(), i))
    return jsonify(ok=True)



@app.post("/api/jobs")
def jobs():
    """Agrège Indeed, LinkedIn, Glassdoor et Google Jobs via python-jobspy (sans clé API)."""
    try: from jobspy import scrape_jobs
    except ImportError: return jsonify(error="Installe python-jobspy : pip install python-jobspy"), 400
    s, n, loc = cfg(), 0, (request.json.get("location") or "France").strip()
    try:
        with db() as c:
            for kw in [k.strip() for k in s["keywords"].split(",") if k.strip()]:
                df = scrape_jobs(site_name=["indeed", "linkedin", "glassdoor", "google"], search_term=f"stage {kw}",
                                 google_search_term=f"stage {kw} offres {loc}", location=loc, results_wanted=15,
                                 hours_old=24 * 14, country_indeed="France")
                for r in df.to_dict("records"):
                    co, title = clean(r.get("company")), clean(r.get("title"))
                    if not co or not title or c.execute("SELECT 1 FROM contacts WHERE company=? AND job_title=?", (co, title)).fetchone(): continue
                    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", clean(r.get("emails")))
                    c.execute("INSERT INTO contacts(company,email,city,job_title,job_url,job_desc) VALUES(?,?,?,?,?,?)",
                              (co, m.group(0) if m else "", clean(r.get("location")), title, clean(r.get("job_url")), clean(r.get("description"))[:1500])); n += 1
    except Exception as e: return jsonify(error=str(e)), 400
    return jsonify(n=n)


def prep_all():
    try:
        s = cfg()
        with db() as c:
            rows = c.execute("SELECT * FROM contacts WHERE status='pending' AND email!='' AND COALESCE(body,'')=''").fetchall()
        for r in rows:
            subj, body = compose(s, r["company"], dict(r))
            with db() as c: c.execute("UPDATE contacts SET subject=?, body=? WHERE id=?", (subj, body, r["id"]))
    finally: state["prep"] = False


@app.post("/api/prepare")
def prepare():
    if not state["prep"]:
        state["prep"] = True; threading.Thread(target=prep_all, daemon=True).start()
    return jsonify(ok=True)


@app.get("/api/preview/next")
def preview_next():
    with db() as c:
        r = c.execute("SELECT * FROM contacts WHERE status='pending' ORDER BY email='' , id LIMIT 1").fetchone()
    if not r: return jsonify(error="Aucun contact"), 404
    subj, body = (r["subject"], r["body"]) if r["body"] else compose(cfg(), r["company"], dict(r))
    return jsonify(subject=subj, body=body, company=r["company"])


@app.get("/api/preview/<int:i>")
def preview(i):
    with db() as c: r = c.execute("SELECT * FROM contacts WHERE id=?", (i,)).fetchone()
    subj, body = compose(cfg(), r["company"], dict(r))
    return jsonify(subject=subj, body=body)


@app.post("/api/test")
def test():
    s = cfg()
    try: subj, body = compose(s, "Entreprise Test"); send(s, s["email"], subj, body); return jsonify(ok=True)
    except Exception as e: return jsonify(error=str(e)), 400


@app.route("/api/engine", methods=["GET", "POST"])
def engine():
    if request.method == "POST":
        state["running"] = request.json["run"]; state["msg"] = "En marche" if state["running"] else "Arrêté"
        with db() as c: c.execute("INSERT OR REPLACE INTO settings VALUES('running',?)", ("1" if state["running"] else "0",))
    now = datetime.now(PARIS)
    with db() as c:
        sent = c.execute("SELECT COUNT(*) FROM contacts WHERE status='sent' AND sent_at LIKE ?", (now.strftime("%Y-%m-%d") + "%",)).fetchone()[0]
    return jsonify(running=state["running"], prep=state["prep"], msg=state["msg"], open=is_open(now), paris=now.strftime("%a %H:%M"), today=sent)


init()
state["running"] = cfg()["running"] == "1"
state["msg"] = "En marche" if state["running"] else "Arrêté"
threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    app.run(port=5000)