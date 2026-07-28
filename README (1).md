# Speicher-Vorteil · unabhängig gerechnet

Ein **neutrales** Werkzeug, das den wirtschaftlichen Vorteil von PV, Batteriespeicher
und dynamischem Stromtarif in seine **einzelnen Hebel zerlegt** — statt sie zu einer
geschönten Sammelzahl zu verrühren. Keine Hardware im Angebot, keine Kaufempfehlung,
keine Lead-Weitergabe: alle Annahmen liegen offen und sind veränderbar.

Genau das können die verbreiteten Rechner der Speicher-Anbieter strukturell nicht sein
— dort ist die kostenlose Analyse der Trichter für den Geräteverkauf.

## Was es rechnet

Der Vorteil wird in bis zu sechs Positionen aufgeschlüsselt und einzeln ausgewiesen:

| Hebel | gilt für | Grundlage |
|---|---|---|
| PV-Eigenverbrauch | PV | selbst genutzte kWh × Bezugspreis |
| Einspeiseerlös | PV | Überschuss-kWh × Einspeisevergütung |
| Arbitrage (dyn. Tarif) | Speicher + dyn. Tarif | Zyklen × nutzbare kWh × Spread, **nach** Round-Trip-Verlusten |
| Peak Shaving | Gewerbe (RLM) + Speicher | gekappte kW × Leistungspreis |
| §14a-Reduzierung | Haushalt + Speicher | pauschale Netzentgeltreduzierung |
| Verschleiß / Degradation | Speicher | Durchsatzkosten (LCOS-artig), als **Abzug** |

Zwei Modi (**Haushalt** und **Gewerbe RLM**) blenden die jeweils relevanten Hebel ein.
IAB (§7g) senkt die *effektive Investition* — nicht als getarnte Jahresersparnis.
Zusätzlich: Sensitivitäts-Bandbreite und Amortisation.

## Was es bewusst offenlegt

- **Round-Trip-Verluste** sind eingerechnet, Verschleiß wird gegengerechnet.
- Das **AgNes-Risiko** (mögliche Belastung reiner Arbitrage über dynamische Netzentgelte
  ab ~2030) ist ausgewiesen — der Arbitrage-Hebel ist über die Laufzeit nicht garantiert.
- Die Peak-Shaving-Kappung ist als **Annahme** markiert, die erst die Simulation des
  realen 15-Minuten-Lastgangs bestätigt.
- PV-Verschiebung und Arbitrage **konkurrieren** um dieselben Zyklen — die Summe ist
  eher eine Obergrenze.

## Projektstruktur

```
speicher-vorteil-rechner/
├── app.py              # Streamlit-UI
├── calc.py             # Rechenkern (frei von Streamlit, testbar)
├── requirements.txt
├── .streamlit/config.toml
├── README.md · LICENSE · .gitignore
```

Die Trennung von `calc.py` und `app.py` ist Absicht: der Rechenkern ist ohne UI
testbar (`python calc.py` gibt einen Selbsttest aus) und in anderen Frontends
oder einer CLI wiederverwendbar.

## Lokal starten

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Rechenkern-Selbsttest ohne UI:

```bash
python calc.py
```

## Auf Streamlit Community Cloud deployen

1. Repo auf GitHub pushen (öffentlich oder privat).
2. Auf [share.streamlit.io](https://share.streamlit.io) mit GitHub anmelden.
3. **New app** → Repo wählen, Branch `main`, Main file path `app.py`.
4. **Deploy.** `requirements.txt` wird automatisch installiert.

## Modellcharakter & Haftung

Erstordnungs-Rechnung zur Einordnung, **keine verbindliche Auslegung**, kein Angebot,
keine Steuer- oder Rechtsberatung. Das Ergebnis wird vollständig von den Annahmen
bestimmt — deshalb liegen sie offen.

## Roadmap

- **Echte Lastgang-Simulation** fürs Peak Shaving: CSV-Upload der 15-Minuten-Werte,
  nachweisbare kW-Kappung gegen Leistungs- *und* Energiegrenze über alle 35.040 Intervalle.
- **Multi-Use-Konkurrenz** zwischen PV-Verschiebung und Arbitrage sauber modellieren.
- EPEX-Spot-Historie statt pauschalem Spread.

## Lizenz

MIT — Namensfeld in `LICENSE` bitte ausfüllen.
