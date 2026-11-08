# Candidatures Auto

Send personalized spontaneous internship applications (_candidatures spontanées_) to companies and startups in France, automatically, **only during their business hours**.

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

## Deploy on Render

This app keeps its contacts, settings, and uploaded CV on disk. Use a paid Render web service with a persistent disk; the Blueprint below mounts one at `/var/data`. The deployment is protected by HTTP Basic authentication, so set a private username and password when Render prompts for `APP_USERNAME` and `APP_PASSWORD`.

1. Push this repository to GitHub, GitLab, or Bitbucket.
2. In Render, choose **New → Blueprint**, connect the repository, and apply `render.yaml`.
3. Enter values for `APP_USERNAME` and `APP_PASSWORD` when prompted. Keep them private.
4. Wait for the deploy to become live, then open its `onrender.com` URL and authenticate.

The repository originally used a file named `gitignore`, which Git does not recognize. `.gitignore` now excludes `data.db` and `uploads/`, and the currently tracked database and CV have been removed from the Git index while preserving local copies. Commit and push that removal before deploying. Earlier commits may still contain the files; rotate credentials stored in the database, and purge the files from Git history if the repository is public. The database stores SMTP and Anthropic credentials in clear text, so protect it as sensitive data.

The service uses one Gunicorn worker because the email sender runs in-process and SQLite is local to the persistent disk. Render disks require a paid service plan and prevent zero-downtime deploys. Do not scale this service to multiple instances.

## Usage

1. **CV**: upload your PDF.
2. **Message**: set your subject and text, your target keywords, and a short "about you" with real facts (studies, projects, skills). Optionally add an Anthropic API key for fully personalized messages.
3. **Contacts**: click _Trouver des offres_ (choose a location, default `France`) and/or import a CSV. Click _Préparer et enregistrer les messages_ to write and save the drafts.
4. **Sending**: enter your name, sending address and SMTP credentials, set the daily cap and delay, then click _Démarrer_.

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

- SMTP password and API key are stored **in clear text** in `data.db`; protect the file and never commit it or uploaded CVs.
- Render deployments require HTTP Basic authentication configured through `APP_USERNAME` and `APP_PASSWORD`. Local development remains unauthenticated by default.

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
