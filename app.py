"""Speicher-Vorteil · unabhängig gerechnet — Streamlit-App.

Neutrales Instrument statt Verkaufstrichter: alle Annahmen sichtbar und
veränderbar, der Vorteil in seine Hebel zerlegt, Verschleiß gegengerechnet,
und die üblichen Weichzeichner (Round-Trip-Verluste, AgNes-Risiko, die im
Lastgang zu bestätigende Kappung) offen ausgewiesen.

Start lokal:   streamlit run app.py
"""

import io

import pandas as pd
import altair as alt
import streamlit as st

from calc import (DEFAULTS, COLORS, TECHNOLOGIES, compute, band,
                  spread_from_prices, price_stats)


@st.cache_data(show_spinner=False)
def load_prices(file_bytes: bytes):
    """Parst eine SMARD-Großhandelspreis-CSV (Viertelstunde) → DE/LU-Preisreihe (€/MWh)."""
    df = pd.read_csv(io.BytesIO(file_bytes), sep=";", decimal=",", thousands=".",
                     na_values=["-"], encoding="utf-8-sig")
    col = next(c for c in df.columns if c.startswith("Deutschland/Luxemburg"))
    prices = pd.to_numeric(df[col], errors="coerce").ffill().tolist()
    von = str(df.iloc[0, 0]) if len(df) else ""
    bis = str(df.iloc[-1, 1]) if len(df) else ""
    return prices, von, bis

# ── Seitenkonfiguration ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Speicher-Vorteil · unabhängig gerechnet",
    page_icon="⚡",
    layout="wide",
)

INK, MUTED, LINE, ACCENT = "#1B1E22", "#6A7078", "#E1E4E7", "#0E6E6E"
# ── Feinschliff: Streamlit-Chrome ausblenden + dezente Politur ─────────────
st.markdown(f"""
<style>
  #MainMenu {{visibility: hidden;}}
  footer {{visibility: hidden;}}
  [data-testid="stToolbar"] {{visibility: hidden; height: 0;}}
  [data-testid="stDecoration"] {{display: none;}}
  .stDeployButton, [data-testid="stAppDeployButton"] {{display: none;}}
  header[data-testid="stHeader"] {{background: transparent;}}

  .block-container {{padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1120px;}}
  [data-testid="stMetricValue"] {{font-size: 1.9rem; letter-spacing: -0.02em; color: {INK};}}
  [data-testid="stMetricLabel"] p {{color: {MUTED}; font-size: 0.82rem;}}
  section[data-testid="stSidebar"] {{border-right: 1px solid {LINE};}}
  .stButton > button {{border-radius: 8px; font-weight: 600;}}
  h2, h3 {{letter-spacing: -0.01em;}}

  /* Responsiv: schmale Screens - Spalten stapeln, Größen zähmen */
  @media (max-width: 640px) {{
    .block-container {{padding-left: 0.8rem; padding-right: 0.8rem; padding-top: 1.4rem;}}
    [data-testid="stMetricValue"] {{font-size: 1.4rem;}}
    [data-testid="stHorizontalBlock"] {{flex-wrap: wrap; gap: 0.4rem;}}
    [data-testid="stHorizontalBlock"] > div {{min-width: 100% !important;}}
    h1 {{font-size: 1.35rem !important;}}
  }}
</style>
""", unsafe_allow_html=True)
# Feld-Metadaten: label, einheit, step, nachkommastellen
FIELDS = {
    "verbrauch": ("Jahresverbrauch", "kWh/a", 100.0, 0),
    "bezug": ("Strombezugspreis", "ct/kWh", 0.5, 1),
    "pv_kwp": ("PV-Leistung", "kWp", 1.0, 0),
    "einspeise": ("Einspeisevergütung", "ct/kWh", 0.1, 1),
    "speicher_kwh": ("Speicher nutzbar", "kWh", 1.0, 0),
    "spread": ("nutzbarer Spread", "ct/kWh", 0.5, 1),
    "delta_kw": ("Lastspitzen-Kappung", "kW", 1.0, 0),
    "leistungspreis": ("Leistungspreis", "€/kW·a", 5.0, 0),
    "preis_kwh": ("Speicherpreis", "€/kWh", 10.0, 0),
    "invest_rest": ("Übrige Investition (PV, WR, Montage)", "€", 500.0, 0),
    "pv_yield": ("PV-Ertrag", "kWh/kWp", 10.0, 0),
    "ev_ohne": ("Eigenverbrauch o. Speicher", "%", 1.0, 0),
    "ev_mit": ("Eigenverbrauch m. Speicher", "%", 1.0, 0),
    "zyklen": ("Ladezyklen/Jahr", "Zyk.", 10.0, 0),
    "rt": ("Round-Trip-Wirkungsgrad", "%", 1.0, 0),
    "degr_zyklen": ("Zyklenlebensdauer", "Zyk.", 500.0, 0),
    "arb_dauer_h": ("Entladedauer Arbitrage", "h", 0.5, 1),
    "arb_capture": ("Ausschöpfung (Foresight)", "%", 5.0, 0),
    "n14a_eur": ("§14a-Reduzierung", "€/a", 10.0, 0),
    "iab_quote": ("IAB-Quote (§7g)", "%", 5.0, 0),
    "steuersatz": ("Steuersatz", "%", 1.0, 0),
}


# ── Deutsche Zahlenformatierung (locale-unabhängig) ───────────────────────
def de(v, d=0):
    if v is None or v != v or v in (float("inf"), float("-inf")):
        return "—"
    s = f"{v:,.{d}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def eur(v, d=0):
    return "—" if de(v, d) == "—" else de(v, d) + " €"


def eur_a(v):
    return "—" if de(v) == "—" else de(v) + " €/a"


def num_input(k):
    label, unit, step, dec = FIELDS[k]
    return st.number_input(
        f"{label} ({unit})",
        key=k, min_value=0.0, step=step,
        format=f"%.{dec}f",
    )


# ── Zustand / Modus ───────────────────────────────────────────────────────
st.sidebar.markdown("### Modus")
mode_label = st.sidebar.radio(
    "Betriebsart", ["Haushalt", "Gewerbe (RLM)"],
    label_visibility="collapsed",
)
mode = "gewerbe" if "Gewerbe" in mode_label else "haushalt"

# Bei Moduswechsel die Zahlen-Eingaben auf die Modus-Defaults zurücksetzen
if st.session_state.get("_mode") != mode:
    st.session_state["_mode"] = mode
    st.session_state["_tech"] = None  # Technik-Presets neu anwenden
    for k in DEFAULTS[mode]:
        st.session_state.pop(k, None)
for k, v in DEFAULTS[mode].items():
    st.session_state.setdefault(k, float(v))


is_g = mode == "gewerbe"

# ── Sidebar: Bausteine ────────────────────────────────────────────────────
st.sidebar.markdown("### Bausteine")
c1, c2 = st.sidebar.columns(2)
pv_on       = c1.checkbox("PV", value=True, key="pv")
speicher_on = c2.checkbox("Speicher", value=True, key="speicher")
c3, c4 = st.sidebar.columns(2)
dyn_on      = c3.checkbox("Dyn. Tarif", value=True, key="dyn")
n14a_on     = c4.checkbox("§14a", value=False, key="n14a") if not is_g else False

t = {"pv": pv_on, "speicher": speicher_on, "dyn": dyn_on, "n14a": n14a_on}
st.sidebar.write(t)
# ── Sidebar: Speichertechnik ──────────────────────────────────────────────
# Setzt zellchemie-abhängige Startwerte (Wirkungsgrad, Zyklenlebensdauer),
# bevor die zugehörigen Zahlenfelder instanziiert werden. Bleibt editierbar.
st.sidebar.markdown("### Speichertechnik")
tech = st.sidebar.selectbox(
    "Zellchemie", list(TECHNOLOGIES),
    format_func=lambda k: TECHNOLOGIES[k]["label"],
    key="tech", disabled=not t["speicher"],
)
if st.session_state.get("_tech") != tech:
    st.session_state["_tech"] = tech
    st.session_state["rt"] = float(TECHNOLOGIES[tech]["rt"])
    st.session_state["degr_zyklen"] = float(TECHNOLOGIES[tech]["degr_zyklen"])
st.sidebar.caption(TECHNOLOGIES[tech]["note"])

# ── Sidebar: Preisdaten (optional) ────────────────────────────────────────
# Leitet den Arbitrage-Spread aus echten SMARD-Spotpreisen ab (statt Pauschale).
# Muss vor dem Spread-Feld laufen, um dessen Wert setzen zu können.
st.sidebar.markdown("### Preisdaten (optional)")
price_info = None
if t["speicher"] and t["dyn"]:
    up = st.sidebar.file_uploader("SMARD-Spotpreise (CSV, Viertelstunde)", type=["csv"])
    use_csv = st.sidebar.checkbox("Spread aus Preisdaten ableiten",
                                  value=True, disabled=up is None)
    if up is not None:
        try:
            prices, von, bis = load_prices(up.getvalue())
            sp = spread_from_prices(
                prices, dur_h=st.session_state["arb_dauer_h"],
                capture=st.session_state["arb_capture"] / 100.0)
            pstat = price_stats(prices)
            if sp:
                price_info = {**sp, **pstat, "von": von, "bis": bis}
                if use_csv:
                    st.session_state["spread"] = round(sp["spread_ct"], 1)
                st.sidebar.caption(
                    f"{sp['days']} Tage · Ø {pstat['mean']:.0f} €/MWh · "
                    f"{pstat['negativ']}× negativ · Spread {sp['spread_ct']:.1f} ct/kWh")
        except Exception:
            st.sidebar.error("CSV nicht lesbar — SMARD-Format (Viertelstunde) erwartet.")
else:
    st.sidebar.caption("Speicher + dyn. Tarif aktivieren, um Spotpreise zu nutzen.")

# ── Sidebar: Eckdaten ─────────────────────────────────────────────────────
st.sidebar.markdown("### Eckdaten")
num_input("verbrauch")
num_input("bezug")
if t["pv"]:
    num_input("pv_kwp")
    num_input("einspeise")
if t["speicher"]:
    num_input("speicher_kwh")
if t["speicher"] and t["dyn"]:
    num_input("spread")
if is_g and t["speicher"]:
    num_input("delta_kw")
    num_input("leistungspreis")
if t["speicher"]:
    num_input("preis_kwh")
num_input("invest_rest")

with st.sidebar.expander("Annahmen anzeigen"):
    if t["pv"]:
        num_input("pv_yield")
        num_input("ev_ohne")
        num_input("ev_mit")
    if t["speicher"] and t["dyn"]:
        num_input("zyklen")
        num_input("rt")
        num_input("arb_dauer_h")
        num_input("arb_capture")
    if t["speicher"]:
        num_input("degr_zyklen")
    if (not is_g) and t["speicher"] and t["n14a"]:
        num_input("n14a_eur")
    if is_g:
        num_input("iab_quote")
        num_input("steuersatz")

inp = {k: st.session_state[k] for k in DEFAULTS[mode]}
r = compute(mode, t, inp)
b = band(mode, t, inp, r["eff_invest"])

# ── Kopf ──────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:8px">
      <h1 style="margin:0;font-size:1.7rem;letter-spacing:-0.01em">Speicher-Vorteil · unabhängig gerechnet</h1>
      <span style="font-family:ui-monospace,monospace;font-size:0.72rem;color:{ACCENT};
        border:1px solid {ACCENT};border-radius:6px;padding:3px 8px;letter-spacing:0.03em">
        keine Kaufempfehlung · Annahmen offen</span>
    </div>
    <p style="color:{MUTED};max-width:46rem;margin:.4rem 0 0">
      Zerlegt den wirtschaftlichen Vorteil von PV, Speicher und dynamischem Tarif in seine
      einzelnen Hebel. Jede Annahme ist links sichtbar und veränderbar. Verschleiß wird
      gegengerechnet, statt ihn wegzulassen.</p>
    """,
    unsafe_allow_html=True,
)
st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ── Kennzahlen ────────────────────────────────────────────────────────────
m1, m2, m3 = st.columns(3)
m1.metric("Netto-Vorteil", eur_a(r["net_annual"]),
          f"Bandbreite {de(b['lo'])}–{de(b['hi'])} €/a", delta_color="off")
pay = de(r["payback"], 1) + " J" if r["payback"] != float("inf") else "—"
pay_band = (f"{de(b['p_lo'], 1)}–{de(b['p_hi'], 1)} J"
            if b["p_lo"] != float("inf") and b["p_hi"] != float("inf") else "je nach Annahme")
m2.metric("Amortisation", pay, pay_band, delta_color="off")
tax_note = (f"nach IAB −{eur(r['steuervorteil'])}" if r["steuervorteil"] > 0
            else "ohne Steuervorteil")
m3.metric("Eff. Investition", eur(r["eff_invest"]), tax_note, delta_color="off")
if t["speicher"]:
    m3.caption(f"Gesamt {eur(r['invest'])} · Speicher {eur(r['invest_speicher'])} "
               f"({de(st.session_state['preis_kwh'])} €/kWh)")
else:
    m3.caption(f"Gesamt {eur(r['invest'])}")

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ── Zerlegung ─────────────────────────────────────────────────────────────
st.subheader("Der Vorteil, in seine Hebel zerlegt")

if not r["levers"]:
    st.info("Kein Baustein aktiv. Wähle links PV, Speicher oder dyn. Tarif.")
else:
    df = pd.DataFrame([{"Hebel": l["label"], "Wert": round(l["value"]),
                        "farbe": l["color"]} for l in r["levers"]])
    order = df["Hebel"].tolist()
    chart = (
        alt.Chart(df).mark_bar(cornerRadius=3).encode(
            x=alt.X("Wert:Q", title="€ / Jahr"),
            y=alt.Y("Hebel:N", sort=order, title=None,
                    axis=alt.Axis(labelLimit=240, labelOverlap=False, labelFontSize=12)),
            color=alt.Color("Hebel:N",
                            scale=alt.Scale(domain=order, range=df["farbe"].tolist()),
                            legend=None),
            tooltip=[alt.Tooltip("Hebel:N"), alt.Tooltip("Wert:Q", format=",.0f", title="€/a")],
        ).properties(height=max(140, 58 * len(order)))
    )
    st.altair_chart(chart, use_container_width=True)

    # Detailzeilen mit Notiz
    rows = []
    for l in r["levers"]:
        sign = "+" if l["value"] >= 0 else "−"
        col = COLORS["degr"] if l["kind"] == "cost" else INK
        rows.append(
            f"<div style='display:flex;align-items:flex-start;gap:8px;padding:4px 0'>"
            f"<span style='width:11px;height:11px;border-radius:3px;background:{l['color']};"
            f"margin-top:3px;flex:none'></span>"
            f"<div style='flex:1'><div style='display:flex;justify-content:space-between'>"
            f"<span style='font-weight:600'>{l['label']}</span>"
            f"<span style='font-family:ui-monospace,monospace;color:{col};font-weight:600'>"
            f"{sign}{eur(abs(l['value']))}</span></div>"
            f"<div style='color:{MUTED};font-size:.8rem'>{l['note']}</div></div></div>"
        )
    rows.append(
        f"<div style='display:flex;justify-content:space-between;border-top:1px solid {LINE};"
        f"margin-top:8px;padding-top:8px;font-family:ui-monospace,monospace'>"
        f"<span style='font-weight:700'>Netto-Vorteil / Jahr</span>"
        f"<span style='font-weight:700;font-size:1.05rem'>{eur_a(r['net_annual'])}</span></div>"
    )
    st.markdown("".join(rows), unsafe_allow_html=True)

# ── Ehrlichkeits-Hinweise ─────────────────────────────────────────────────
st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
notes = []
if r["arb_kwh"] > 0:
    notes.append(
        f"<span style='color:{COLORS['arbitrage']}'>■</span> Arbitrage ist *nach* "
        "Round-Trip-Verlusten gerechnet und um Verschleiß gekürzt. Die **AgNes-Reform** der "
        "Bundesnetzagentur könnte reine Arbitrage ab ~2030 über dynamische Netzentgelte belasten — "
        "der Hebel ist über die Laufzeit nicht garantiert.")
if price_info:
    notes.append(
        f"<span style='color:{COLORS['arbitrage']}'>■</span> Der Spread von "
        f"**{price_info['spread_ct']:.1f} ct/kWh** stammt aus deinen SMARD-Spotpreisen "
        f"({price_info['days']} Tage, {price_info['negativ']} Viertelstunden negativ, "
        f"Ø {price_info['mean']:.0f} €/MWh) — Modell: ein Zyklus/Tag, "
        f"{price_info['dur_h']:.0f}-h-Fenster, {price_info['capture'] * 100:.0f}% Ausschöpfung "
        "gegen die Perfect-Foresight-Illusion. Historische Spreads sind keine Garantie für künftige.")
if is_g and t["speicher"] and inp["delta_kw"] > 0:
    notes.append(
        f"<span style='color:{COLORS['peak']}'>■</span> Die Lastspitzen-Kappung ist eine "
        "**Annahme**. Ob der Speicher die Zielleistung über die längste Jahresspitze wirklich hält, "
        "entscheidet die Simulation des realen 15-Minuten-Lastgangs — eine einzige Überschreitung "
        "setzt den Jahreshöchstwert neu.")
if t["pv"] and t["speicher"] and t["dyn"]:
    notes.append(
        f"<span style='color:{COLORS['eigen']}'>■</span> PV-Verschiebung und Arbitrage teilen sich "
        "denselben Speicher. Beide Hebel sind hier unabhängig geschätzt — real konkurrieren sie um "
        "Zyklen, die Summe ist daher eher eine Obergrenze.")
if t["speicher"] and tech == "natrium":
    notes.append(
        f"<span style='color:{COLORS['arbitrage']}'>■</span> **Natrium-Ionen (Na⁺)** läuft 2026 erst "
        "hoch: Zyklen- und Wirkungsgrad-Werte sind Herstellerangaben (CATL Naxtra, Revolta), "
        "unabhängig noch nicht bestätigt (IRENA: weniger ausgereift als Li-Ion). Der Kostenvorteil "
        "ist projiziert, nicht garantiert — setze deinen realen Angebotspreis ein. Heim-Na⁺-Systeme "
        "haben oft geringere Lade-/Entladeleistung, relevant fürs Peak Shaving.")
notes.append(
    f"<span style='color:{COLORS['degr']}'>■</span> Erstordnungs-Modell zur Einordnung, keine "
    "verbindliche Auslegung. Prüfe die Annahmen links — sie bestimmen das Ergebnis.")

with st.container():
    st.markdown("**Was diese Rechnung offenlegt**")
    for n in notes:
        st.markdown(n, unsafe_allow_html=True)

st.caption("Modellrechnung ohne Gewähr · kein Angebot · keine Steuer- oder Rechtsberatung.")
