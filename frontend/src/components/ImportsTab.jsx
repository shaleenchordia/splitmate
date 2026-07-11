import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import ImportReview from './ImportReview.jsx'

export default function ImportsTab({ group, onCommitted }) {
  const [batches, setBatches] = useState(null)
  const [open, setOpen] = useState(null) // batch id being reviewed
  const [file, setFile] = useState(null)
  const [usdRate, setUsdRate] = useState('83.00')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(
    () => api(`/groups/${group.id}/imports/`).then(setBatches).catch((e) => setError(e.message)),
    [group.id],
  )
  useEffect(() => {
    load()
  }, [load])

  const upload = async (e) => {
    e.preventDefault()
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('fx_rates', JSON.stringify({ USD: usdRate }))
      const batch = await api(`/groups/${group.id}/imports/`, { method: 'POST', formData: fd })
      setFile(null)
      await load()
      setOpen(batch.id)
    } catch (err) {
      setError(err.body?.detail || err.message)
    } finally {
      setBusy(false)
    }
  }

  if (open)
    return (
      <ImportReview
        group={group}
        batchId={open}
        onBack={() => {
          setOpen(null)
          load()
        }}
        onCommitted={onCommitted}
      />
    )

  return (
    <>
      <div className="card">
        <h3>Import a spreadsheet</h3>
        <p className="muted">
          Upload the group's expense export (CSV or XLSX). Nothing is written to the
          ledger until you review every problem the importer finds and approve the fixes.
        </p>
        <form className="row" onSubmit={upload}>
          <div style={{ flex: 2 }}>
            <input
              type="file"
              accept=".csv,.xlsx"
              onChange={(e) => setFile(e.target.files[0])}
            />
          </div>
          <div style={{ width: 180 }}>
            <label>USD → {group.base_currency} rate</label>
            <input
              type="number"
              step="0.0001"
              value={usdRate}
              onChange={(e) => setUsdRate(e.target.value)}
            />
          </div>
          <div style={{ alignSelf: 'flex-end' }}>
            <button className="primary" type="submit" disabled={!file || busy}>
              {busy ? 'Analyzing…' : 'Upload & analyze'}
            </button>
          </div>
        </form>
        {error && <div className="error-box">{error}</div>}
      </div>

      <div className="card">
        <h3>Import history</h3>
        {batches?.length === 0 && <p className="muted">No imports yet.</p>}
        {batches?.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Uploaded</th>
                <th>Status</th>
                <th>Rows</th>
                <th>Decisions</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.id}>
                  <td>{b.file_name}</td>
                  <td className="mono">{new Date(b.created_at).toLocaleString()}</td>
                  <td>
                    <span
                      className={`badge ${
                        b.status === 'committed' ? 'ok' : b.status === 'staged' ? 'warning' : 'neutral'
                      }`}
                    >
                      {b.status}
                    </span>
                  </td>
                  <td className="mono">{b.total_rows}</td>
                  <td className="mono">
                    {b.status === 'staged'
                      ? `${b.review_needed - b.review_open}/${b.review_needed} made`
                      : '—'}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button onClick={() => setOpen(b.id)}>
                      {b.status === 'staged' ? 'Review' : 'View report'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
