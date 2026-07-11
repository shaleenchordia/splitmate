import { useEffect, useState } from 'react'
import { api } from '../api.js'

// The import report: every anomaly detected and the action taken.
// Available while staged (proposals) and permanently after commit.

export default function ImportReport({ group, batchId, onBack, showReviewLink, onReview }) {
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api(`/groups/${group.id}/imports/${batchId}/report/`)
      .then(setReport)
      .catch((e) => setError(e.message))
  }, [group.id, batchId])

  if (error) return <div className="error-box">{error}</div>
  if (!report) return null

  const download = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `import-report-${report.batch_id}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <button onClick={onBack}>← Imports</button>
        <h2 style={{ margin: 0 }}>Import report — {report.file_name}</h2>
        <span className={`badge ${report.status === 'committed' ? 'ok' : 'warning'}`}>
          {report.status}
        </span>
        <span style={{ flex: 1 }} />
        {showReviewLink && <button onClick={onReview}>Back to review</button>}
        <button onClick={download}>Download JSON</button>
      </div>

      <div className="card row" style={{ gap: 28 }}>
        <Stat label="Rows in file" value={report.total_rows} />
        <Stat label="Rows with findings" value={report.rows_with_anomalies} />
        <Stat label="Findings" value={report.total_anomalies} />
        {report.dispositions && (
          <>
            <Stat label="Imported as expenses" value={report.dispositions.expense || 0} />
            <Stat label="As settlements" value={report.dispositions.settlement || 0} />
            <Stat label="Excluded" value={report.dispositions.skipped || 0} />
          </>
        )}
        <Stat label="FX rates" value={Object.entries(report.fx_rates).map(([k, v]) => `${k} ${v}`).join(', ') || '—'} />
      </div>

      {report.rows
        .filter((r) => r.anomalies.length > 0)
        .map((row) => (
          <div className="card" key={row.row_number}>
            <div className="row">
              <span className="badge neutral">row {row.row_number}</span>
              <strong>{row.raw.description || '(no description)'}</strong>
              <span className="muted">
                {row.raw.date} · {row.raw.amount} {row.raw.currency}
              </span>
              <span style={{ flex: 1 }} />
              <DispositionBadge row={row} />
            </div>
            <table style={{ marginTop: 8 }}>
              <thead>
                <tr>
                  <th style={{ width: 220 }}>Finding</th>
                  <th>Detail</th>
                  <th style={{ width: 260 }}>Action taken</th>
                </tr>
              </thead>
              <tbody>
                {row.anomalies.map((a, i) => (
                  <tr key={i}>
                    <td>
                      <span className={`badge ${a.severity}`}>{a.severity}</span>{' '}
                      <strong>{a.code}</strong>
                    </td>
                    <td className="muted">{a.message}</td>
                    <td>
                      {JSON.stringify(a.action_taken)}
                      {a.overridden && <span className="badge warning"> overridden by reviewer</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="muted">{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
    </div>
  )
}

function DispositionBadge({ row }) {
  if (row.disposition === 'staged') return <span className="badge warning">staged</span>
  if (row.disposition === 'skip') return <span className="badge neutral">excluded</span>
  if (row.disposition === 'settlement')
    return <span className="badge ok">settlement #{row.created_settlement_id}</span>
  return <span className="badge ok">expense #{row.created_expense_id}</span>
}
