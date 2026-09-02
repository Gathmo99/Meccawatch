# Meccawatch

Automatischer GitHub-Actions-Watcher für das **MECCHA ROGUE / Liberation Sequence ARG**.

## Was überwacht wird

- Hauptseite, `covenant.html`, `register.html`, `submit-art.html` und automatisch entdeckte interne HTML-Seiten
- kompletter HTML-Quelltext und SHA-256
- stabile HTTP-Response-Header (inklusive versteckter Signal-Header)
- `CARD xx/20`, `SIGNAL`, `PRIORITY`, `A.R.G.U.S.`, `SEVENTEENTH`
- neue relevante `/media/`-Assets
- Quelltext-Diffs, Snapshots und historische Versionen

Der Workflow läuft nominell alle fünf Minuten und kann unter **Actions → MECCHA ROGUE Watcher → Run workflow** manuell gestartet werden. GitHub weist darauf hin, dass geplante Workflows bei hoher Auslastung verzögert werden können; fünf Minuten sind daher ein Zeitplan, keine Echtzeitgarantie.

## Discord aktivieren

Im Repository unter **Settings → Secrets and variables → Actions → New repository secret** ein Secret namens `DISCORD_WEBHOOK` anlegen. Der Webhook selbst gehört niemals in eine Datei oder einen Commit.

Die erste Ausführung erstellt eine stille Baseline. Discord-Meldungen werden erst bei späteren relevanten Änderungen versendet.

## Lokaler Test

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python watcher.py
```

Optionale Umgebungsvariablen: `MECCHA_BASE_URL`, `MECCHA_MAX_PAGES`, `MECCHA_MAX_MEDIA_BYTES`.
