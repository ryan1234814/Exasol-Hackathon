import React from 'react'
import { Bar } from 'react-chartjs-2'
import { useGet, fmt, riskColor } from './_shared'
import SqlDrawer from '../components/SqlDrawer'

export default function Leaderboard() {
  const { data, loading, error } = useGet('/leaderboard?limit=10', [])

  const rows = data?.rows || []
  const chartData = rows.length ? {
    labels: rows.map((r) => `#${r.WARD_ID} ${r.WARD_NAME}`),
    datasets: [{
      label: 'RISK_SCORE',
      data: rows.map((r) => r.RISK_SCORE),
      backgroundColor: rows.map((r) => riskColor(r.RISK_SCORE)),
      borderWidth: 0,
    }],
  } : { labels: [], datasets: [] }

  const options = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { max: 100, ticks: { color: '#8ba0b3' }, grid: { color: '#26384a' } },
      y: { ticks: { color: '#e6edf3' }, grid: { display: false } },
    },
    plugins: { legend: { display: false } },
  }

  return (
    <div className="panel">
      <h2>Worst-ward leaderboard {data ? `· ${data.month}` : ''}</h2>
      {error && <div className="error">leaderboard failed: {error}</div>}
      {loading && <div className="loading">loading…</div>}
      {data && (
        <>
          <div className="chart-wrap"><Bar data={chartData} options={options} /></div>
          <div className="scroll" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>#</th><th>Ward</th><th>Risk</th><th>Worst param</th>
                  <th>Z</th><th>Breach</th><th>Slope</th><th>Complaints</th><th>High</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.WARD_ID}>
                    <td className="mono">{r.RANK_IN_MONTH}</td>
                    <td>#{r.WARD_ID} {r.WARD_NAME}</td>
                    <td className="mono" style={{ color: riskColor(r.RISK_SCORE), fontWeight: 700 }}>{fmt(r.RISK_SCORE)}</td>
                    <td>{r.WORST_PARAM}</td>
                    <td className="mono">{fmt(r.Z_COMPONENT, 2)}</td>
                    <td className="mono">{fmt(r.BREACH_COMPONENT, 2)}</td>
                    <td className="mono">{fmt(r.SLOPE_COMPONENT, 2)}</td>
                    <td className="mono">{r.N_COMPLAINTS}</td>
                    <td className="mono sev-high">{r.N_HIGH_SEV}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="legend-note">Risk components are the UDF's weighted inputs (0–1).</div>
          <div style={{ marginTop: 10 }}>
            <SqlDrawer step="materialize" label="How RISK_SCORE is materialized" />
          </div>
        </>
      )}
    </div>
  )
}
