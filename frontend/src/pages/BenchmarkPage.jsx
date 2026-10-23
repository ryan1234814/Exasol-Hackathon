import React from 'react'
import { Bar } from 'react-chartjs-2'
import { useGet, fmt } from './_shared'

// Benchmark = paired bars (Exasol vs SQLite) per scenario. Data is only timings
// the backend recorded, so this tab is honest about the single-node caveat.
export default function BenchmarkPage() {
  const { data, loading, error } = useGet('/benchmark?limit=5', [])

  const rows = data?.scenarios || []
  const scenarios = [...new Set(rows.map((r) => r.SCENARIO))]
  const pick = (sc, eng) => rows.find((r) => r.SCENARIO === sc && r.ENGINE === eng)?.ELAPSED_MS ?? null

  const chartData = scenarios.length ? {
    labels: scenarios,
    datasets: [
      { label: 'Exasol (ms)', data: scenarios.map((s) => pick(s, 'exasol')), backgroundColor: '#38bdf8' },
      { label: 'SQLite (ms)', data: scenarios.map((s) => pick(s, 'sqlite')), backgroundColor: '#8ba0b3' },
    ],
  } : { labels: [], datasets: [] }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { ticks: { color: '#e6edf3' }, grid: { display: false } },
      y: { type: 'logarithmic', ticks: { color: '#8ba0b3' }, grid: { color: '#26384a' }, title: { display: true, text: 'elapsed ms (log)', color: '#8ba0b3' } },
    },
    plugins: { legend: { labels: { color: '#e6edf3' } } },
  }

  return (
    <div className="panel">
      <h2>Engine benchmark {data ? `· ${data.runs} run(s)` : ''}</h2>
      {error && <div className="error">benchmark failed: {error}</div>}
      {loading && <div className="loading">loading…</div>}
      {data && (
        <>
          <div className="chart-wrap"><Bar data={chartData} options={options} /></div>
          <div className="scroll" style={{ marginTop: 12 }}>
            <table>
              <thead><tr><th>Scenario</th><th>Engine</th><th>Rows touched</th><th>Elapsed ms</th><th>Bytes sent</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.SCENARIO}</td>
                    <td>{r.ENGINE}</td>
                    <td className="mono">{fmt(r.ROWS_TOUCHED, 0)}</td>
                    <td className="mono">{fmt(r.ELAPSED_MS, 0)}</td>
                    <td className="mono">{fmt(r.BYTES_SENT, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.single_node_caveat && <div className="legend-note" style={{ marginTop: 10 }}>{data.single_node_caveat}</div>}
        </>
      )}
    </div>
  )
}
