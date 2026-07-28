"""Rechenkern für den Speicher-Vorteil-Rechner.

Bewusst frei von Streamlit: reine Funktionen, damit die Logik testbar und
wiederverwendbar bleibt (CLI, Tests, andere Frontends). Die UI (app.py)
importiert nur `compute`, `net_for`, `DEFAULTS` und `COLORS`.

Modellcharakter: Erstordnungs-Rechnung zur Einordnung, keine verbindliche
Auslegung. Jede Annahme ist Eingabe, nichts ist fest verdrahtet.
"""

from __future__ import annotations

from math import inf

# ── Farbwelt (semantisch): Solar=Bernstein, Spot=Petrol, Netz=Blau, Kosten=Rost
COLORS = {
    "eigen": "#E8A33D",
    "einspeise": "#F0C67A",
    "arbitrage": "#2FA4A4",
    "peak": "#2E5E8C",
    "n14a": "#6B7A8F",
    "degr": "#B4534B",
}

# ── Standardwerte je Modus ────────────────────────────────────────────────
DEFAULTS = {
    "haushalt": {
        "verbrauch": 4500, "bezug": 32.0, "einspeise": 8.0,
        "pv_kwp": 10, "pv_yield": 950, "ev_ohne": 30, "ev_mit": 65,
        "speicher_kwh": 10, "spread": 12.0, "zyklen": 220, "rt": 90,
        "invest": 22000, "invest_speicher": 8000, "degr_zyklen": 6000,
        "n14a_eur": 130,
        "delta_kw": 0, "leistungspreis": 0, "steuersatz": 0, "iab_quote": 0,
    },
    "gewerbe": {
        "verbrauch": 300000, "bezug": 25.0, "einspeise": 7.0,
        "pv_kwp": 100, "pv_yield": 950, "ev_ohne": 45, "ev_mit": 70,
        "speicher_kwh": 100, "spread": 10.0, "zyklen": 300, "rt": 90,
        "invest": 120000, "invest_speicher": 75000, "degr_zyklen": 6000,
        "n14a_eur": 0,
        "delta_kw": 40, "leistungspreis": 120, "steuersatz": 30, "iab_quote": 50,
    },
}


def compute(mode: str, t: dict, inp: dict) -> dict:
    """Berechnet die Hebel-Zerlegung und Kennzahlen.

    mode: "haushalt" | "gewerbe"
    t:    Bausteine, z.B. {"pv": True, "speicher": True, "dyn": True, "n14a": False}
    inp:  Zahlenwerte (siehe DEFAULTS)
    """
    is_g = mode == "gewerbe"
    pv_prod = inp["pv_kwp"] * inp["pv_yield"] if t.get("pv") else 0.0
    ev_quote = inp["ev_mit"] if t.get("speicher") else inp["ev_ohne"]
    self_kwh = min(pv_prod * ev_quote / 100.0, inp["verbrauch"]) if t.get("pv") else 0.0
    surplus_kwh = max(pv_prod - self_kwh, 0.0)

    levers: list[dict] = []

    # Hebel 1 — PV-Eigenverbrauch (vermiedener Netzbezug)
    if t.get("pv"):
        levers.append({
            "key": "eigen", "label": "PV-Eigenverbrauch", "color": COLORS["eigen"],
            "kind": "benefit", "value": self_kwh * inp["bezug"] / 100.0,
            "note": f"{self_kwh:,.0f} kWh selbst genutzt · Quote {ev_quote:.0f}%",
        })
        # Hebel 2 — Einspeiseerlös (Überschuss)
        levers.append({
            "key": "einspeise", "label": "Einspeiseerlös", "color": COLORS["einspeise"],
            "kind": "benefit", "value": surplus_kwh * inp["einspeise"] / 100.0,
            "note": f"{surplus_kwh:,.0f} kWh eingespeist",
        })

    # Hebel 3 — Arbitrage (dyn. Tarif, braucht Speicher)
    arb_kwh = 0.0
    if t.get("speicher") and t.get("dyn"):
        arb_kwh = inp["zyklen"] * inp["speicher_kwh"] * (inp["rt"] / 100.0)
        levers.append({
            "key": "arbitrage", "label": "Arbitrage (dyn. Tarif)", "color": COLORS["arbitrage"],
            "kind": "benefit", "value": arb_kwh * inp["spread"] / 100.0,
            "note": f"{inp['zyklen']:,.0f} Zyklen · Spread {inp['spread']:.1f} ct · η {inp['rt']:.0f}%",
        })

    # Hebel 4 — Leistungspreis / Peak Shaving (nur Gewerbe RLM, braucht Speicher)
    if is_g and t.get("speicher") and inp["delta_kw"] > 0:
        levers.append({
            "key": "peak", "label": "Peak Shaving (Leistungspreis)", "color": COLORS["peak"],
            "kind": "benefit", "value": inp["delta_kw"] * inp["leistungspreis"],
            "note": f"{inp['delta_kw']:,.0f} kW × {inp['leistungspreis']:,.0f} €/kW · im Lastgang zu bestätigen",
        })

    # Hebel 5 — §14a (nur Haushalt, braucht steuerbaren Verbraucher/Speicher)
    if (not is_g) and t.get("speicher") and t.get("n14a") and inp["n14a_eur"] > 0:
        levers.append({
            "key": "n14a", "label": "§14a-Netzentgeltreduzierung", "color": COLORS["n14a"],
            "kind": "benefit", "value": float(inp["n14a_eur"]),
            "note": "pauschale Reduzierung (Modul 1)",
        })

    # Kostenzeile — Verschleiß / Degradation auf Arbitrage-Durchsatz
    lcos_ct = 0.0
    if t.get("speicher") and inp["degr_zyklen"] > 0 and inp["speicher_kwh"] > 0:
        lcos_ct = inp["invest_speicher"] / (inp["degr_zyklen"] * inp["speicher_kwh"]) * 100.0
        degr_cost = arb_kwh * lcos_ct / 100.0
        if degr_cost > 0:
            levers.append({
                "key": "degr", "label": "Verschleiß / Degradation", "color": COLORS["degr"],
                "kind": "cost", "value": -degr_cost,
                "note": f"{lcos_ct:.1f} ct/kWh Durchsatzkosten auf Arbitrage",
            })

    benefits = sum(l["value"] for l in levers if l["kind"] == "benefit")
    costs = sum(l["value"] for l in levers if l["kind"] == "cost")  # negativ
    net_annual = benefits + costs

    # Investition & Steuer (IAB nur Gewerbe, einmalig — kein Jahres-Hebel)
    steuervorteil = 0.0
    if is_g and inp["iab_quote"] > 0 and inp["steuersatz"] > 0:
        iab_betrag = inp["invest"] * (min(inp["iab_quote"], 50) / 100.0)
        steuervorteil = iab_betrag * (inp["steuersatz"] / 100.0)
    eff_invest = max(inp["invest"] - steuervorteil, 0.0)
    payback = eff_invest / net_annual if net_annual > 0 else inf

    return {
        "levers": levers, "benefits": benefits, "costs": costs,
        "net_annual": net_annual, "eff_invest": eff_invest,
        "steuervorteil": steuervorteil, "payback": payback,
        "arb_kwh": arb_kwh, "lcos_ct": lcos_ct,
    }


def net_for(mode, t, inp, spread_mul, bezug_mul, ev_shift) -> float:
    """Netto-Vorteil unter skalierten Annahmen — für die Sensitivitäts-Bandbreite."""
    mod = dict(inp)
    mod["spread"] = inp["spread"] * spread_mul
    mod["bezug"] = inp["bezug"] * bezug_mul
    mod["ev_ohne"] = max(0, inp["ev_ohne"] + ev_shift)
    mod["ev_mit"] = max(0, inp["ev_mit"] + ev_shift)
    return compute(mode, t, mod)["net_annual"]


def band(mode, t, inp, eff_invest) -> dict:
    """Pessimistische/optimistische Bandbreite für Vorteil und Amortisation."""
    lo = net_for(mode, t, inp, 0.7, 0.9, -8)
    hi = net_for(mode, t, inp, 1.3, 1.1, 8)
    p_lo = eff_invest / hi if hi > 0 else inf   # beste Amortisation
    p_hi = eff_invest / lo if lo > 0 else inf   # schlechteste
    return {"lo": lo, "hi": hi, "p_lo": p_lo, "p_hi": p_hi}


if __name__ == "__main__":
    # Mini-Selbsttest
    for m in ("haushalt", "gewerbe"):
        tog = {"pv": True, "speicher": True, "dyn": True, "n14a": False}
        res = compute(m, tog, DEFAULTS[m])
        print(f"[{m}] Netto {res['net_annual']:.0f} €/a · "
              f"Amortisation {res['payback']:.1f} J · Hebel {len(res['levers'])}")
