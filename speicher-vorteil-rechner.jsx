import React, { useState, useMemo } from "react";

// ── Farbwelt: semantisch motiviert ────────────────────────────────
// Solar = Bernstein, Spotmarkt = Petrol, Netz = Blau, Kosten = Rost
const C = {
  bg: "#F4F5F6",
  panel: "#FFFFFF",
  ink: "#1B1E22",
  muted: "#6A7078",
  line: "#E1E4E7",
  accent: "#0E6E6E",
  eigen: "#E8A33D",
  einspeise: "#F0C67A",
  arbitrage: "#2FA4A4",
  peak: "#2E5E8C",
  n14a: "#6B7A8F",
  degr: "#B4534B",
};

const fmtEur = (v) =>
  (v == null || !isFinite(v) ? "—" : Math.round(v).toLocaleString("de-DE") + " €");
const fmtEurA = (v) =>
  (v == null || !isFinite(v) ? "—" : Math.round(v).toLocaleString("de-DE") + " €/a");
const fmtNum = (v, d = 0) =>
  (v == null || !isFinite(v) ? "—" : v.toLocaleString("de-DE", { maximumFractionDigits: d }));

// ── Standardwerte je Modus ────────────────────────────────────────
const DEFAULTS = {
  haushalt: {
    verbrauch: 4500, bezug: 32, einspeise: 8.0,
    pv_kwp: 10, pv_yield: 950, ev_ohne: 30, ev_mit: 65,
    speicher_kwh: 10, spread: 12, zyklen: 220, rt: 90,
    invest: 22000, invest_speicher: 8000, degr_zyklen: 6000,
    n14a_eur: 130,
    delta_kw: 0, leistungspreis: 0, steuersatz: 0, iab_quote: 0,
  },
  gewerbe: {
    verbrauch: 300000, bezug: 25, einspeise: 7.0,
    pv_kwp: 100, pv_yield: 950, ev_ohne: 45, ev_mit: 70,
    speicher_kwh: 100, spread: 10, zyklen: 300, rt: 90,
    invest: 120000, invest_speicher: 75000, degr_zyklen: 6000,
    n14a_eur: 0,
    delta_kw: 40, leistungspreis: 120, steuersatz: 30, iab_quote: 50,
  },
};

// ── Rechenkern ────────────────────────────────────────────────────
function compute(mode, t, inp) {
  const isG = mode === "gewerbe";
  const pvProd = t.pv ? inp.pv_kwp * inp.pv_yield : 0;
  const evQuote = t.speicher ? inp.ev_mit : inp.ev_ohne;
  const selfKWh = t.pv ? Math.min((pvProd * evQuote) / 100, inp.verbrauch) : 0;
  const surplusKWh = Math.max(pvProd - selfKWh, 0);

  const levers = [];

  // Hebel 1 — PV-Eigenverbrauch (vermiedener Netzbezug)
  if (t.pv) {
    levers.push({
      key: "eigen", label: "PV-Eigenverbrauch", color: C.eigen, kind: "benefit",
      value: (selfKWh * inp.bezug) / 100,
      note: `${fmtNum(selfKWh)} kWh selbst genutzt · Quote ${evQuote}%`,
    });
    // Hebel 2 — Einspeiseerlös (Überschuss)
    levers.push({
      key: "einspeise", label: "Einspeiseerlös", color: C.einspeise, kind: "benefit",
      value: (surplusKWh * inp.einspeise) / 100,
      note: `${fmtNum(surplusKWh)} kWh eingespeist`,
    });
  }

  // Hebel 3 — Arbitrage (dyn. Tarif, braucht Speicher)
  let arbKWh = 0;
  if (t.speicher && t.dyn) {
    arbKWh = inp.zyklen * inp.speicher_kwh * (inp.rt / 100);
    levers.push({
      key: "arbitrage", label: "Arbitrage (dyn. Tarif)", color: C.arbitrage, kind: "benefit",
      value: (arbKWh * inp.spread) / 100,
      note: `${fmtNum(inp.zyklen)} Zyklen · Spread ${fmtNum(inp.spread, 1)} ct · η ${inp.rt}%`,
    });
  }

  // Hebel 4 — Leistungspreis / Peak Shaving (nur Gewerbe RLM, braucht Speicher)
  if (isG && t.speicher && inp.delta_kw > 0) {
    levers.push({
      key: "peak", label: "Peak Shaving (Leistungspreis)", color: C.peak, kind: "benefit",
      value: inp.delta_kw * inp.leistungspreis,
      note: `${fmtNum(inp.delta_kw)} kW × ${fmtNum(inp.leistungspreis)} €/kW · im Lastgang zu bestätigen`,
    });
  }

  // Hebel 5 — §14a (nur Haushalt, braucht steuerbaren Verbraucher/Speicher)
  if (!isG && t.speicher && t.n14a && inp.n14a_eur > 0) {
    levers.push({
      key: "n14a", label: "§14a-Netzentgeltreduzierung", color: C.n14a, kind: "benefit",
      value: inp.n14a_eur, note: "pauschale Reduzierung (Modul 1)",
    });
  }

  // Kostenzeile — Verschleiß / Degradation auf Arbitrage-Durchsatz
  let lcos_ct = 0, degrCost = 0;
  if (t.speicher && inp.degr_zyklen > 0 && inp.speicher_kwh > 0) {
    lcos_ct = (inp.invest_speicher / (inp.degr_zyklen * inp.speicher_kwh)) * 100;
    degrCost = (arbKWh * lcos_ct) / 100;
    if (degrCost > 0) {
      levers.push({
        key: "degr", label: "Verschleiß / Degradation", color: C.degr, kind: "cost",
        value: -degrCost,
        note: `${fmtNum(lcos_ct, 1)} ct/kWh Durchsatzkosten auf Arbitrage`,
      });
    }
  }

  const benefits = levers.filter((l) => l.kind === "benefit").reduce((s, l) => s + l.value, 0);
  const costs = levers.filter((l) => l.kind === "cost").reduce((s, l) => s + l.value, 0); // negativ
  const netAnnual = benefits + costs;

  // Investition & Steuer (IAB nur Gewerbe, einmalig — kein Jahres-Hebel)
  let steuervorteil = 0;
  if (isG && inp.iab_quote > 0 && inp.steuersatz > 0) {
    const iabBetrag = inp.invest * (Math.min(inp.iab_quote, 50) / 100);
    steuervorteil = iabBetrag * (inp.steuersatz / 100);
  }
  const effInvest = Math.max(inp.invest - steuervorteil, 0);
  const payback = netAnnual > 0 ? effInvest / netAnnual : Infinity;

  return { levers, benefits, costs, netAnnual, effInvest, steuervorteil, payback, arbKWh, lcos_ct };
}

function netFor(mode, t, inp, spreadMul, bezugMul, evShift) {
  const mod = { ...inp, spread: inp.spread * spreadMul, bezug: inp.bezug * bezugMul,
    ev_ohne: Math.max(0, inp.ev_ohne + evShift), ev_mit: Math.max(0, inp.ev_mit + evShift) };
  return compute(mode, t, mod).netAnnual;
}

// ── kleine UI-Bausteine ───────────────────────────────────────────
function NumField({ label, unit, value, onChange, step = 1 }) {
  return (
    <label className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-sm" style={{ color: C.muted }}>{label}</span>
      <span className="flex items-center gap-1.5">
        <input
          type="number" value={value} step={step}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          className="w-24 text-right font-mono text-sm rounded px-2 py-1 outline-none focus:ring-2"
          style={{ border: `1px solid ${C.line}`, color: C.ink, background: "#FBFBFC" }}
        />
        <span className="text-xs w-12" style={{ color: C.muted }}>{unit}</span>
      </span>
    </label>
  );
}

function Toggle({ on, onClick, label, dot }) {
  return (
    <button onClick={onClick}
      className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors"
      style={{
        border: `1px solid ${on ? C.accent : C.line}`,
        background: on ? "rgba(14,110,110,0.06)" : "#FBFBFC",
        color: on ? C.accent : C.muted,
      }}>
      <span className="w-2.5 h-2.5 rounded-full"
        style={{ background: on ? (dot || C.accent) : C.line }} />
      {label}
    </button>
  );
}

// ── Hauptkomponente ───────────────────────────────────────────────
export default function App() {
  const [mode, setMode] = useState("haushalt");
  const [t, setT] = useState({ pv: true, speicher: true, dyn: true, n14a: false });
  const [inp, setInp] = useState(DEFAULTS.haushalt);
  const [showAss, setShowAss] = useState(false);

  const switchMode = (m) => { setMode(m); setInp(DEFAULTS[m]); };
  const set = (k) => (v) => setInp((s) => ({ ...s, [k]: v }));
  const isG = mode === "gewerbe";

  const r = useMemo(() => compute(mode, t, inp), [mode, t, inp]);

  // Bandbreite (Sensitivität): pessimistisch/optimistisch
  const band = useMemo(() => {
    const lo = netFor(mode, t, inp, 0.7, 0.9, -8);
    const hi = netFor(mode, t, inp, 1.3, 1.1, 8);
    const pLo = hi > 0 ? r.effInvest / hi : Infinity; // beste Amortisation
    const pHi = lo > 0 ? r.effInvest / lo : Infinity;  // schlechteste
    return { lo, hi, pLo, pHi };
  }, [mode, t, inp, r.effInvest]);

  const maxAbs = Math.max(...r.levers.map((l) => Math.abs(l.value)), 1);
  const benefitTotal = r.benefits;

  return (
    <div style={{ background: C.bg, color: C.ink, minHeight: "100%" }}
      className="font-sans">
      <div className="max-w-6xl mx-auto px-5 py-8">

        {/* Kopf */}
        <header className="mb-7 pb-5" style={{ borderBottom: `1px solid ${C.line}` }}>
          <div className="flex items-baseline justify-between flex-wrap gap-2">
            <h1 className="text-2xl font-bold tracking-tight">
              Speicher-Vorteil · unabhängig gerechnet
            </h1>
            <span className="font-mono text-xs px-2 py-1 rounded"
              style={{ color: C.accent, border: `1px solid ${C.accent}`, letterSpacing: "0.03em" }}>
              keine Kaufempfehlung · Annahmen offen
            </span>
          </div>
          <p className="text-sm mt-2 max-w-2xl" style={{ color: C.muted }}>
            Zerlegt den wirtschaftlichen Vorteil von PV, Speicher und dynamischem Tarif
            in seine einzelnen Hebel. Jede Annahme ist sichtbar und veränderbar. Verschleiß
            wird gegengerechnet, statt ihn wegzulassen.
          </p>
        </header>

        <div className="grid gap-6" style={{ gridTemplateColumns: "minmax(0,340px) 1fr" }}>

          {/* ── Steuerung ──────────────────────────────── */}
          <aside className="space-y-5">
            {/* Modus */}
            <div className="rounded-xl p-1 inline-flex w-full"
              style={{ background: "#EBEDEF", border: `1px solid ${C.line}` }}>
              {["haushalt", "gewerbe"].map((m) => (
                <button key={m} onClick={() => switchMode(m)}
                  className="flex-1 rounded-lg py-2 text-sm font-semibold capitalize transition-colors"
                  style={{
                    background: mode === m ? C.panel : "transparent",
                    color: mode === m ? C.ink : C.muted,
                    boxShadow: mode === m ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                  }}>
                  {m === "gewerbe" ? "Gewerbe (RLM)" : "Haushalt"}
                </button>
              ))}
            </div>

            {/* Komponenten */}
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide mb-2"
                style={{ color: C.muted }}>Bausteine wählen</div>
              <div className="flex flex-wrap gap-2">
                <Toggle on={t.pv} dot={C.eigen} label="PV"
                  onClick={() => setT((s) => ({ ...s, pv: !s.pv }))} />
                <Toggle on={t.speicher} dot={C.arbitrage} label="Speicher"
                  onClick={() => setT((s) => ({ ...s, speicher: !s.speicher }))} />
                <Toggle on={t.dyn} dot={C.arbitrage} label="Dyn. Tarif"
                  onClick={() => setT((s) => ({ ...s, dyn: !s.dyn }))} />
                {!isG && (
                  <Toggle on={t.n14a} dot={C.n14a} label="§14a"
                    onClick={() => setT((s) => ({ ...s, n14a: !s.n14a }))} />
                )}
              </div>
            </div>

            {/* Eingaben */}
            <div className="rounded-xl p-4" style={{ background: C.panel, border: `1px solid ${C.line}` }}>
              <div className="text-xs font-semibold uppercase tracking-wide mb-1"
                style={{ color: C.muted }}>Eckdaten</div>
              <NumField label="Jahresverbrauch" unit="kWh/a" value={inp.verbrauch} onChange={set("verbrauch")} step={100} />
              <NumField label="Strombezugspreis" unit="ct/kWh" value={inp.bezug} onChange={set("bezug")} step={0.5} />
              {t.pv && (<>
                <NumField label="PV-Leistung" unit="kWp" value={inp.pv_kwp} onChange={set("pv_kwp")} />
                <NumField label="Einspeisevergütung" unit="ct/kWh" value={inp.einspeise} onChange={set("einspeise")} step={0.1} />
              </>)}
              {t.speicher && (
                <NumField label="Speicher nutzbar" unit="kWh" value={inp.speicher_kwh} onChange={set("speicher_kwh")} />
              )}
              {t.speicher && t.dyn && (
                <NumField label="nutzbarer Spread" unit="ct/kWh" value={inp.spread} onChange={set("spread")} step={0.5} />
              )}
              {isG && t.speicher && (<>
                <NumField label="Lastspitzen-Kappung" unit="kW" value={inp.delta_kw} onChange={set("delta_kw")} />
                <NumField label="Leistungspreis" unit="€/kW·a" value={inp.leistungspreis} onChange={set("leistungspreis")} step={5} />
              </>)}
              <NumField label="Investition gesamt" unit="€" value={inp.invest} onChange={set("invest")} step={500} />
            </div>

            {/* Annahmen (aufklappbar) */}
            <div className="rounded-xl" style={{ background: C.panel, border: `1px solid ${C.line}` }}>
              <button onClick={() => setShowAss((s) => !s)}
                className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold">
                <span>Annahmen {showAss ? "ausblenden" : "anzeigen"}</span>
                <span style={{ color: C.muted }}>{showAss ? "−" : "+"}</span>
              </button>
              {showAss && (
                <div className="px-4 pb-4 pt-1" style={{ borderTop: `1px solid ${C.line}` }}>
                  {t.pv && (<>
                    <NumField label="PV-Ertrag" unit="kWh/kWp" value={inp.pv_yield} onChange={set("pv_yield")} step={10} />
                    <NumField label="Eigenverbrauch o. Speicher" unit="%" value={inp.ev_ohne} onChange={set("ev_ohne")} />
                    <NumField label="Eigenverbrauch m. Speicher" unit="%" value={inp.ev_mit} onChange={set("ev_mit")} />
                  </>)}
                  {t.speicher && t.dyn && (<>
                    <NumField label="Ladezyklen/Jahr" unit="Zyk." value={inp.zyklen} onChange={set("zyklen")} step={10} />
                    <NumField label="Round-Trip-Wirkungsgrad" unit="%" value={inp.rt} onChange={set("rt")} />
                  </>)}
                  {t.speicher && (<>
                    <NumField label="Speicher-Anteil Investition" unit="€" value={inp.invest_speicher} onChange={set("invest_speicher")} step={500} />
                    <NumField label="Zyklenlebensdauer" unit="Zyk." value={inp.degr_zyklen} onChange={set("degr_zyklen")} step={500} />
                  </>)}
                  {!isG && t.speicher && t.n14a && (
                    <NumField label="§14a-Reduzierung" unit="€/a" value={inp.n14a_eur} onChange={set("n14a_eur")} step={10} />
                  )}
                  {isG && (<>
                    <NumField label="IAB-Quote (§7g)" unit="%" value={inp.iab_quote} onChange={set("iab_quote")} step={5} />
                    <NumField label="Steuersatz" unit="%" value={inp.steuersatz} onChange={set("steuersatz")} />
                  </>)}
                </div>
              )}
            </div>
          </aside>

          {/* ── Ergebnis ──────────────────────────────── */}
          <main className="space-y-5">
            {/* Kennzahlen */}
            <div className="grid grid-cols-3 gap-4">
              <div className="rounded-xl p-4" style={{ background: C.panel, border: `1px solid ${C.line}` }}>
                <div className="text-xs uppercase tracking-wide" style={{ color: C.muted }}>Netto-Vorteil</div>
                <div className="font-mono text-2xl font-bold mt-1">{fmtEurA(r.netAnnual)}</div>
                <div className="text-xs mt-1" style={{ color: C.muted }}>
                  Bandbreite {fmtNum(band.lo)}–{fmtNum(band.hi)} €/a
                </div>
              </div>
              <div className="rounded-xl p-4" style={{ background: C.panel, border: `1px solid ${C.line}` }}>
                <div className="text-xs uppercase tracking-wide" style={{ color: C.muted }}>Amortisation</div>
                <div className="font-mono text-2xl font-bold mt-1">
                  {isFinite(r.payback) ? fmtNum(r.payback, 1) + " J" : "—"}
                </div>
                <div className="text-xs mt-1" style={{ color: C.muted }}>
                  {isFinite(band.pLo) && isFinite(band.pHi)
                    ? `${fmtNum(band.pLo, 1)}–${fmtNum(band.pHi, 1)} J` : "je nach Annahme"}
                </div>
              </div>
              <div className="rounded-xl p-4" style={{ background: C.panel, border: `1px solid ${C.line}` }}>
                <div className="text-xs uppercase tracking-wide" style={{ color: C.muted }}>Eff. Investition</div>
                <div className="font-mono text-2xl font-bold mt-1">{fmtEur(r.effInvest)}</div>
                <div className="text-xs mt-1" style={{ color: C.muted }}>
                  {r.steuervorteil > 0 ? `nach IAB −${fmtEur(r.steuervorteil)}` : "ohne Steuervorteil"}
                </div>
              </div>
            </div>

            {/* Zerlegung */}
            <div className="rounded-xl p-5" style={{ background: C.panel, border: `1px solid ${C.line}` }}>
              <div className="flex items-baseline justify-between mb-4">
                <h2 className="font-semibold">Der Vorteil, in seine Hebel zerlegt</h2>
                <span className="font-mono text-sm" style={{ color: C.muted }}>
                  Nutzen {fmtEurA(benefitTotal)}
                </span>
              </div>

              {r.levers.length === 0 && (
                <p className="text-sm py-6 text-center" style={{ color: C.muted }}>
                  Kein Baustein aktiv. Wähle links PV, Speicher oder dyn. Tarif.
                </p>
              )}

              <div className="space-y-3">
                {r.levers.map((l) => (
                  <div key={l.key}>
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="flex items-center gap-2">
                        <span className="w-3 h-3 rounded-sm" style={{ background: l.color }} />
                        <span className="font-medium">{l.label}</span>
                      </span>
                      <span className="font-mono font-semibold"
                        style={{ color: l.kind === "cost" ? C.degr : C.ink }}>
                        {l.value >= 0 ? "+" : "−"}{fmtEur(Math.abs(l.value))}
                      </span>
                    </div>
                    <div className="h-2.5 rounded-full overflow-hidden" style={{ background: "#EEF0F1" }}>
                      <div className="h-full rounded-full"
                        style={{ width: `${(Math.abs(l.value) / maxAbs) * 100}%`, background: l.color }} />
                    </div>
                    <div className="text-xs mt-1" style={{ color: C.muted }}>{l.note}</div>
                  </div>
                ))}
              </div>

              {r.levers.length > 0 && (
                <div className="flex items-center justify-between mt-4 pt-3 font-mono"
                  style={{ borderTop: `1px solid ${C.line}` }}>
                  <span className="text-sm font-semibold">Netto-Vorteil / Jahr</span>
                  <span className="text-lg font-bold">{fmtEurA(r.netAnnual)}</span>
                </div>
              )}
            </div>

            {/* Ehrlichkeits-Hinweise */}
            <div className="rounded-xl p-5 text-sm space-y-2.5"
              style={{ background: "#FBFAF7", border: `1px solid ${C.line}` }}>
              <div className="font-semibold" style={{ color: C.ink }}>Was diese Rechnung offenlegt</div>
              {r.arbKWh > 0 && (
                <p style={{ color: C.muted }}>
                  <span style={{ color: C.arbitrage }}>■</span> Arbitrage ist <em>nach</em> Round-Trip-Verlusten
                  gerechnet und um Verschleiß gekürzt. Die <strong>AgNes-Reform</strong> der Bundesnetzagentur
                  könnte reine Arbitrage ab ~2030 über dynamische Netzentgelte belasten — der Hebel ist über
                  die Laufzeit nicht garantiert.
                </p>
              )}
              {isG && t.speicher && inp.delta_kw > 0 && (
                <p style={{ color: C.muted }}>
                  <span style={{ color: C.peak }}>■</span> Die Lastspitzen-Kappung ist eine <strong>Annahme</strong>.
                  Ob der Speicher die Zielleistung über die längste Jahresspitze wirklich hält, entscheidet sich
                  erst in der Simulation des realen 15-Minuten-Lastgangs — eine einzige Überschreitung setzt den
                  Jahreshöchstwert neu.
                </p>
              )}
              {t.pv && t.speicher && t.dyn && (
                <p style={{ color: C.muted }}>
                  <span style={{ color: C.eigen }}>■</span> PV-Verschiebung und Arbitrage teilen sich denselben
                  Speicher. Beide Hebel sind hier unabhängig geschätzt — real konkurrieren sie um Zyklen, die
                  Summe ist daher eher eine Obergrenze.
                </p>
              )}
              <p style={{ color: C.muted }}>
                <span style={{ color: C.degr }}>■</span> Erstordnungs-Modell zur Einordnung, keine
                verbindliche Auslegung. Prüfe die Annahmen links — sie bestimmen das Ergebnis.
              </p>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
