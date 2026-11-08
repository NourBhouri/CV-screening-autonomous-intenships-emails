# Candidatures Auto

Send personalized spontaneous internship applications (*candidatures spontanées*) to companies and startups in France, automatically, **only during their business hours**.

Upload your CV, find internship offers across several job platforms, let the app write a tailored email for each contact, and have it sent one by one on weekdays in Paris time.

> The interface is in French, since it targets the French job market.

## Features

- **CV upload**: your PDF is attached to every email.
- **Multi-platform offer search**: Indeed, LinkedIn, Glassdoor and Google Jobs in one click, using your keywords (via [python-jobspy](https://github.com/speedyapply/JobSpy), no API key needed). Emails found in job descriptions are picked up automatically.
- **CSV import**: add your own contacts (`company,email,city`).
- **One message per contact**: with an Anthropic API key, each email is written for that company (name, city, offer, your profile). Without a key, a template with `{company}`, `{name}`, `{job_title}` and `{keywords}` is used.
- **Drafts saved in advance**: prepare all messages at any time, review the next one with the preview button, send later.
- **Business-hours sending**: Monday to Friday, 09:00–12:00 and 14:00–17:30 (Europe/Paris), with a daily cap and a pause between emails.
- **Resumes after restart**: the running state is stored, so relaunching the app picks up the queue.
- **Opt-out line** automatically added to every email.

## Quick start

Requires Python 3.9+.

```bash
git clone https://github.com/<your-username>/candidatures-auto.git
cd candidatures-auto
pip install -r requirements.txt
python app.py
```

Open <http://localhost:5000>.

## Usage

1. **CV**: upload your PDF.
2. **Message**: set your subject and text, your target keywords, and a short "about you" with real facts (studies, projects, skills). Optionally add an Anthropic API key for fully personalized messages.
3. **Contacts**: click *Trouver des offres* (choose a location, default `France`) and/or import a CSV. Click *Préparer et enregistrer les messages* to write and save the drafts.
4. **Sending**: enter your name, sending address and SMTP credentials, set the daily cap and delay, then click *Démarrer*.

Keep the terminal open: emails are only sent while the app is running.

### Gmail setup

Enable 2-step verification on your Google account, then create an **app password** (Google Account → Security → App passwords). Use it in the SMTP password field, not your normal password. Default server: `smtp.gmail.com`, port `587` (STARTTLS).

### CSV format

```csv
company,email,city
Acme AI,jobs@acme.fr,Paris
Beta Labs,contact@beta.io,Lyon
```

## How sending works

A background worker checks every 15 seconds. It sends the next pending contact that has an email only if:

- it is a weekday inside the business-hour windows (Paris time),
- the daily cap has not been reached,
- the configured pause since the last email has elapsed.

If a contact has no saved draft yet, one is written and saved right before sending.

## Project structure

```
app.py              Flask backend, SQLite storage, message generation, sending worker
templates/index.html  Single-page interface
requirements.txt    Dependencies
```

`data.db` (settings, contacts, drafts) and `uploads/` (your CV) are created on first run.

## Security

- SMTP password and API key are stored **in clear text** in the local `data.db`. Run the app locally only, and never commit `data.db` or `uploads/` (they are in `.gitignore`).
- The server has no authentication: do not expose it on a public network.

## Responsible use

- Email only addresses relevant to the recipient's professional activity, personalize your messages, and keep volumes reasonable (the default cap is 25 per day). In the EU, B2B prospecting must respect GDPR/CNIL rules, including an easy way to opt out; honor any "stop" reply.
- Offer search relies on scraping public job pages, which may go against some sites' terms of service. LinkedIn in particular rate-limits quickly. Use it moderately and at your own risk.
- Generated messages are drafts: read a few before launching a campaign.

## Limitations

- Welcome to the Jungle, Apec and France Travail are not covered.
- Most job posts do not publish an email address; contacts without one are skipped until you provide it (CSV).
- Saved drafts are not regenerated when you change your profile or keywords.

## License

Add the license of your choice (e.g. MIT) in a `LICENSE` file.
