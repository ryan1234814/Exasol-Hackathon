import React, { useEffect, useState } from 'react'

// Landing = the first screen the judge sees. Pure CSS, zero API calls, zero
// chart dependencies, so it renders even with the database and backend down.
// The CTA flips App's view state to 'app', which reveals the tabs + Dashboard.

const FEATURES = [
  {
    icon: '🔍',
    title: 'Anomaly Detection',
    desc: 'Z-score window analytics flag turbidity, chlorine, coliform & pH breaches before an illness spike confirms them.',
  },
  {
    icon: '💬',
    title: 'Complaint Triage',
    desc: 'WhatsApp citizen messages parsed, classified and severity-ranked by explainable regex rules — no black-box AI.',
  },
  {
    icon: '⚡',
    title: 'In-DB Analytics',
    desc: '300k+ samples scanned in milliseconds inside a local Exasol columnar engine. Nothing leaves the laptop.',
  },
  {
    icon: '⛓️',
    title: 'Traceable to SQL',
    desc: 'Every figure names the file behind it, opens that SQL in place, and copies the command that reproduces it. The Trust tab also shows how much of the raw data survived to be counted.',
  },
  {
    icon: '🔒',
    title: 'Free Forever',
    desc: 'Exasol Personal + an open-source stack. No API keys, no credits, no cloud — MIT-licensed throughout.',
  },
]

const STATS = [
  { value: '24', label: 'wards monitored' },
  { value: '300k+', label: 'water samples' },
  { value: '15k+', label: 'complaints triaged' },
  { value: '<1s', label: 'dashboard load' },
]

export default function Landing({ onEnter }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const t = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(t)
  }, [])

  return (
    <div className={`landing${visible ? ' landing--visible' : ''}`}>
      <header className="landing__hero">
        <p className="landing__badge">ExaThon India 2026 · Civic / Sustainability track</p>
        <h1 className="landing__title">
          Ward-Level Water Quality<br />&amp; Complaint Triage
        </h1>
        <p className="landing__subtitle">
          One page every morning. Every ward ranked. Every breach explained.<br />
          Catch deteriorating water quality <em>before</em> the illness spike confirms it.
        </p>
        <button className="landing__cta" onClick={onEnter}>Open Dashboard →</button>
        <p className="landing__hint">All analytics run locally — nothing leaves this machine.</p>
      </header>

      <section className="landing__stats">
        {STATS.map((s) => (
          <div className="landing__stat" key={s.label}>
            <span className="landing__stat-value">{s.value}</span>
            <span className="landing__stat-label">{s.label}</span>
          </div>
        ))}
      </section>

      <section className="landing__features">
        {FEATURES.map((f) => (
          <div className="landing__card" key={f.title}>
            <span className="landing__card-icon">{f.icon}</span>
            <h3>{f.title}</h3>
            <p>{f.desc}</p>
          </div>
        ))}
      </section>

      <section className="landing__description">
        <h2>What this does</h2>
        <div className="landing__description-body">
          <p>
            Municipal ward officers currently discover water-quality deterioration only after
            citizens fall ill. This dashboard inverts that timeline: it continuously analyses
            <strong> turbidity, residual chlorine, coliform and pH</strong> readings across all
            24 wards using SQL window functions — moving averages, z-scores, breach-run
            detection, 12-month deterioration slopes — then cross-references them with
            <strong> citizen complaints</strong> parsed from WhatsApp group exports.
          </p>
          <p>
            The result is a single risk-ranked view: which ward is getting worse <em>this
            month</em>, <em>why</em> (which parameter breached, by how many standard
            deviations, for how many consecutive days), and <em>what people are saying</em> —
            all running inside a local Exasol Personal database on this laptop.
          </p>
          <p>
            Every number on screen traces back to a SQL statement you can inspect and re-run,
            and the complaint classifier is a regex rule table, not a neural network — you can
            see exactly which rule fired on every message.
          </p>
          <p>
            You can also take it with you: export any table as CSV, download the 90-day
            breach forecast as an <strong>.ics calendar</strong> with a 7-day alarm, subscribe
            to the morning brief as an <strong>Atom feed</strong>, read that brief in
            <strong>हिन्दी</strong>, and install the whole dashboard so it still opens with the
            network off.
          </p>
        </div>
      </section>

      <footer className="landing__footer">
        <button className="landing__cta landing__cta--secondary" onClick={onEnter}>
          Enter Dashboard →
        </button>
        <p>Exasol Personal · FastAPI · React · Chart.js — all free, all local.</p>
      </footer>
    </div>
  )
}