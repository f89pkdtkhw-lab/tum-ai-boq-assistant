# Standarddateien

Diese Dateien liegen im Repository und werden von der App automatisch bereitgestellt. Keine echten Projekte, Firmen oder Preise.

## `margin-demo.xlsx`

Dieselbe synthetische Demodatei wie unter [`docs/beispiele/margin-demo.xlsx`](../../docs/beispiele/margin-demo.xlsx) (Wettbewerbsvergleich Kindertagesstätte Nord).

Beim ersten Aufruf der Margin-Seite oder des Vault-Tabs *Wettbewerb / Marge* kopiert die API die Datei einmal in den lokalen Vault (`quelle=default`), sofern sie dort noch nicht liegt. Die Margin-Seite lädt sie dann von selbst als Vergleichsdatei. Wer die Datei aus dem Vault löscht, bekommt sie nicht automatisch zurück. Die gebündelte Datei bleibt unter `GET /api/vault/defaults/margin-demo` erreichbar.

In Tests ist das automatische Seeden ausgeschaltet (`LV_SCOUT_SEED_DEFAULTS=0`).
