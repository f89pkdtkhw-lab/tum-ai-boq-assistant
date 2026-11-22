# Grok-Bot-Brücke

Statt Claude über eine API aufzurufen, legt das Backend jeden KI-Auftrag als Datei in eine Warteschlange. Ein Assistent (dieser Grok Bot) liest den Auftrag, recherchiert selbst und schreibt die Antwort zurück. Die App wartet und macht danach ganz normal weiter.

## Einschalten

1. In **Einstellungen** den Abschnitt **Entwickleroptionen** mit dem Freischaltcode öffnen (Umgebungsvariable `DEV_OPTIONS_CODE`; wenn sie fehlt, ist der Standardcode `2211`).
2. Als Anbieter **Grok Bot** wählen. Die Auswahl gilt sofort für diesen Backend-Prozess (wie ein in der Oberfläche eingegebener API-Schlüssel), bis das Backend neu startet.

Für eine Live-Demo im Pitch lieber **Mock** oder **Claude-API (Key)** nehmen: Die Brücke ist nicht echtzeitfähig, ein Auftrag dauert eher Minuten, und jemand muss die Warteschlange bedienen.

## Ordner

`GROKBOT_QUEUE_DIR`, Standard `~/boq-grokbot-queue`:

| Pfad | Inhalt |
| --- | --- |
| `inbox/<job_id>.json` | Offener Auftrag |
| `inbox/<job_id>.media/page-01.jpg` | Optional: Seitenbilder (PDF-Vision) |
| `outbox/<job_id>.json` | Antwort, sobald sie liegt |
| `inbox/done/<job_id>.json` | Auftrag, nachdem eine Antwort übernommen wurde |

Wartezeit: `GROKBOT_TIMEOUT` (Standard 900 s / 15 min), Prüfung alle `GROKBOT_POLL` (Standard 2 s). In der Analyse erscheint die Meldung **Wartet auf Grok Bot …**. Nach Ablauf der Zeit bricht der Aufruf mit einer klaren Fehlermeldung ab.

## Auftrag (Beispiel)

```json
{
  "job_id": "a1b2c3d4e5f60789a1b2c3d4e5f60789",
  "kind": "complete",
  "created_at": "2026-11-22T01:40:00Z",
  "system": "You review bills of quantities …",
  "prompt": "Question: …",
  "messages": [
    {"role": "system", "content": "You review bills of quantities …"},
    {"role": "user", "content": "Question: …"}
  ],
  "expected_output": {
    "format": "json",
    "schema_hint": "The prompt asks for a JSON object. Write outbox/<job_id>.json as {\"text\": \"{...the JSON object as a string...}\"} so parsers read Answer.text.",
    "json_mode": true
  },
  "model_params": {"max_tokens": 1024, "timeout": 900, "effort": null, "json_mode": true, "max_searches": null},
  "bilder": []
}
```

`kind` ist `complete` (normale Modellantwort) oder `research` (Deep Research / Normenrecherche). API-Schlüssel stehen nie in diesen Dateien.

## Antwort (Beispiel)

```json
{
  "text": "{\"findings\": []}"
}
```

Für `research` dürfen zusätzlich `citations`, `sources`, `searches` und `web_search` stehen:

```json
{
  "text": "Die Position verweist auf DIN 18300 …",
  "citations": [{"url": "https://example.org", "title": "Quelle", "cited_text": "…"}],
  "sources": [{"url": "https://example.org", "title": "Quelle"}],
  "searches": 3,
  "web_search": true
}
```

Reiner Text in der Antwortdatei wird als `{"text": "…"}` gelesen. Liegt ein JSON-Objekt ohne `text` vor, wird das ganze Objekt als Text weitergereicht (damit eine direkte Modell-JSON-Antwort auch funktioniert).

## Werkzeug

```sh
python tools/grokbot_queue.py list
python tools/grokbot_queue.py show <job_id>
python tools/grokbot_queue.py answer <job_id> antwort.json
```

`list` zeigt offene Aufträge, `show` den Prompt, `answer` schreibt die Datei nach `outbox/` und verschiebt den Auftrag nach `inbox/done/`.

## Grenzen

- Nicht in Echtzeit: typischerweise ein bis mehrere Minuten pro Aufruf, plus die Zeit, bis der Assistent aktiv wird.
- Verbrauch zählt gegen das Grok-Bot-Kontingent, nicht gegen ein Claude-API-Limit.
- Der gewählte Anbieter liegt im Speicher des Backends (ein Nutzer, ein Prozess). Nach einem Neustart gilt wieder `LLM_PROVIDER` aus der Umgebung bzw. der Mock.
- Eine unbeaufsichtigte Queue ohne Assistenten läuft in den Timeout.
