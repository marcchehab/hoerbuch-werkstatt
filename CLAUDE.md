# Hörbuch-Werkstatt

Deutsche Romane → Schwiizerdütsch-Hörbuch-Skripte. Chris spricht alle Rollen selber ein.

## Pipeline

1. `buecher/<slug>/original/` – Buch (EPUB) + `text/NNN-*.md` via `python3 tools/extract_epub.py <epub>`. Nie committen.
2. `buecher/<slug>/stil/beispiel.md` – Chris' eigene Übersetzung der ersten Seiten. **Massgebend für Dialekt, Register, Wortwahl.** Nie generisches Schwiizerdütsch schreiben; wo unsicher, im Beispiel nachschlagen.
3. `buecher/<slug>/stil/glossar.md` – wiederkehrende Begriffe (Namen, Orte, Technik) mit festgelegter Dialektform. Bei jeder neuen Entscheidung ergänzen.
4. `buecher/<slug>/skript/kapitel-NN.md` – Ausgabe im Skriptformat (unten).
5. `buecher/<slug>/figuren/NAME.md` – Steckbrief pro Figur. Beim ersten Auftritt anlegen, bei neuen Infos ergänzen (Änderungen markieren mit `> Kap. N: …`).
6. `python3 tools/serve.py` → http://localhost:8765 (Aufnahme-UI). Aufnahmen: `buecher/<slug>/audio/kapitel-NN/` (Takes als wav + `takes.json`). `tools/build.py` nur für den Nur-Lesen-Modus ohne Server.

Lange Kapitel: pro Kapitel einen Subagent (general-purpose) mit CLAUDE.md + stil/ + Quelle, parallel. Koordinator schreibt danach Steckbriefe + Glossar.

Kapitelweise arbeiten, damit Chris parallel aufnehmen kann. Nach jedem Kapitel: Glossar + betroffene Steckbriefe aktualisieren, dann build.

## Skriptformat

```
## Kapitel 3 – Dr Absprung

[SZENE: Brügg vo dr Meridian, Nacht]

ERZÄHLER: Dr Lärm vo de Triebwärk isch ...

KAI (flüsternd): Mir händ kei Ziit meh.

LENA (?): Wer seit das?

HALDE (ironisch, ?): …

[PAUSE]
```

- Erste Zeile: `## Kapitel N – Titel` (Titel übersetzt).
- `NAME: Text` – ein Absatz pro Zeile, Leerzeile zwischen allen Zeilen (Markdown-Absätze). NAME in Grossbuchstaben, wie in `figuren/`.
- `ERZÄHLER` für alles, was keine direkte Rede ist. Auch Erzählung ist Dialekt.
- `(Regieanweisung)` optional nach dem Namen: Tonfall, Lautstärke, Tempo. Kurz, Dialekt.
- `+ Text` – Fortsetzung des gleichen Absatzes (gleicher Sprecher), damit lange Absätze in aufnehmbare Stücke zerfallen. Faustregel: max. 2–3 Sätze pro Zeile; Originalabsätze bleiben als normale Zeilen erkennbar.
- `(?)` wenn der Sprecher im Original nicht eindeutig ist. Beste Vermutung als NAME, Chris entscheidet.
- `[SZENE: …]` bei Ortswechsel, `[PAUSE]` bei Abschnittswechsel.
- Gedanken einer Figur: `NAME (denkt): …`.
- Inquit-Formeln («sagte er leise») werden zur Regieanweisung, nicht mitgesprochen, ausser sie tragen Information.

## Steckbrief (`figuren/NAME.md`)

```
# NAME
- Aussprache: Pinyin mit Tönen · deutsche Annäherung
- Zeichen: 叶哲泰            (chinesische Schriftzeichen, für die Aussprache-Taste im UI)
- Farbe: #3a63a8            (Sprecherfarbe im UI, Chris ändert sie im UI oder hier)
- Foto: name.jpg            (optional; sonst wird figuren/NAME.jpg|png|webp automatisch genommen)
- Rolle:
- Alter:
- Aussehen:
- Temperament:
- Beziehungen:
- Bogen (spoilerfrei bis Kap. N):
- Erster Auftritt: Kap. N

## Stimme
- Tonlage:
- Tempo:
- Dialekt-Färbung:
- Sprachtics:
- Referenzzeile: «…»
```

Stimm-Vorschläge sind Vorschläge. Chris legt die Stimme fest; seine Notizen unter `## Chris` nie überschreiben.

## Regeln

- Kein Buchtext ausserhalb von `buecher/<slug>/` ablegen. `_beispiel` ist fiktiv und bleibt fiktiv.
- Keine Artifacts publizieren.
- Antworten auf Deutsch, kurz.
