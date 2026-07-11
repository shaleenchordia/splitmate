import { useCallback, useEffect, useState } from 'react'
import { api, fmtMoney } from '../api.js'
import ImportReport from './ImportReport.jsx'

// Review a staged batch: every anomaly must get a human decision before
// commit. Approve the proposal, or override it with one of the allowed
// alternatives.

export default function ImportReview({ group, batchId, onBack, onCommitted }) {
  const [batch, setBatch] = useState(null)
  const [showClean, setShowClean] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [showReport, setShowReport] = useState(false)

  const load = useCallback(
    () =>
      api(`/groups/${group.id}/imports/${batchId}/`)
        .then(setBatch)
        .catch((e) => setError(e.message)),
    [group.id, batchId],
  )
  useEffect(() => {
    load()
  }, [load])

  if (error) return <div className="error-box">{error}</div>
  if (!batch) return null

  const staged = batch.status === 'staged'

  const act = async (path, body) => {
    setBusy(true)
    setError(null)
    try {
      await api(`/groups/${group.id}/imports/${batchId}/${path}`, { method: 'POST', body })
      await load()
    } catch (err) {
      setError(
        err.body?.errors ? err.body.errors.join(' · ') : err.body?.detail || err.message,
      )
    } finally {
      setBusy(false)
    }
  }

  const commit = async () => {
    setBusy(true)
    setError(null)
    try {
      await api(`/groups/${group.id}/imports/${batchId}/commit/`, { method: 'POST' })
      await load()
      onCommitted()
      setShowReport(true)
    } catch (err) {
      setError(
        err.body?.errors ? err.body.errors.join(' · ') : err.body?.detail || err.message,
      )
    } finally {
      setBusy(false)
    }
  }

  if (showReport || batch.status === 'committed')
    return (
      <ImportReport
        group={group}
        batchId={batchId}
        onBack={onBack}
        showReviewLink={staged}
        onReview={() => setShowReport(false)}
      />
    )

  const rows = batch.rows.filter((r) => showClean || r.anomalies.length > 0)

  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <button onClick={onBack}>← Imports</button>
        <h2 style={{ margin: 0 }}>Review: {batch.file_name}</h2>
      </div>
      <div className="card row">
        <div style={{ flex: 1 }}>
          <strong>{batch.total_rows}</strong> rows · <strong>{batch.rows_with_anomalies}</strong>{' '}
          rows with findings ·{' '}
          <strong className={batch.review_open ? 'neg' : 'pos'}>
            {batch.review_open} decision{batch.review_open === 1 ? '' : 's'} still needed
          </strong>
          <div className="muted">
            USD rate for this batch: {batch.fx_rates.USD || '—'} · change it and re-run
            detection if it's wrong
          </div>
        </div>
        <button disabled={busy || !staged} onClick={() => act('approve-all/')}>
          Approve all remaining proposals
        </button>
        <button
          disabled={busy || !staged}
          onClick={() => {
            const rate = window.prompt('USD rate for this batch', batch.fx_rates.USD || '83.00')
            if (rate) act('redetect/', { fx_rates: { USD: rate } })
          }}
        >
          Re-run detection
        </button>
        <button className="primary" disabled={busy || !staged || batch.review_open > 0} onClick={commit}
          title={batch.review_open > 0 ? 'Resolve every review item first' : ''}
        >
          Commit to ledger
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="row" style={{ marginBottom: 8 }}>
        <label style={{ margin: 0 }}>
          <input
            type="checkbox"
            checked={showClean}
            onChange={(e) => setShowClean(e.target.checked)}
            style={{ width: 'auto', marginRight: 6 }}
          />
          Also show the {batch.total_rows - batch.rows_with_anomalies} clean rows
        </label>
      </div>

      {rows.map((row) => (
        <RowCard
          key={row.id}
          row={row}
          group={group}
          staged={staged}
          onResolve={(anomalyId, body) => act(`anomalies/${anomalyId}/resolve/`, body)}
        />
      ))}
    </>
  )
}

function RowCard({ row, group, staged, onResolve }) {
  const r = row.raw
  return (
    <div className="card">
      <div className="row">
        <span className="badge neutral">row {row.row_number}</span>
        <strong>{r.description || '(no description)'}</strong>
        <span className="muted">
          {r.date} · paid by {r.paid_by || '?'} · {r.amount} {r.currency || '?'} ·{' '}
          {r.split_type || 'no split type'} · {r.split_with}
        </span>
      </div>
      {r.notes && <div className="muted" style={{ marginTop: 4 }}>note: “{r.notes}”</div>}
      {row.anomalies.map((a) => (
        <AnomalyCard key={a.id} anomaly={a} group={group} staged={staged} onResolve={onResolve} />
      ))}
    </div>
  )
}

function describeAction(action) {
  if (!action) return ''
  const p = action
  switch (p.action) {
    case 'keep': return 'Keep as-is'
    case 'skip_row': return 'Exclude this row from the ledger'
    case 'set_date': return `Set date to ${p.date}`
    case 'set_payer': return `Set payer to ${p.name}`
    case 'set_currency': return `Treat as ${p.currency}`
    case 'set_amount_minor': return `Round to ${fmtMoney(p.amount_minor)}`
    case 'convert_currency': return `Convert at rate ${p.rate}`
    case 'convert_to_settlement':
    case 'record_as_settlement':
      return `Record as settlement: ${p.payer || '?'} → ${p.payee || '?'}`
    case 'set_split_type': return `Change split type to '${p.split_type}'`
    case 'normalize_percents': return 'Scale percentages proportionally to 100%'
    case 'remove_participant': return `Remove ${p.name} from the split & re-split`
    case 'add_member': return `Add ${p.name} as a ${p.is_guest ? 'guest ' : ''}member`
    case 'map_name': return `Read '${p.source}' as '${p.target}'`
    default: return JSON.stringify(p)
  }
}

function AnomalyCard({ anomaly, group, staged, onResolve }) {
  const [overriding, setOverriding] = useState(false)
  const resolved = anomaly.resolved_action != null
  const overridden =
    resolved && JSON.stringify(anomaly.resolved_action) !== JSON.stringify(anomaly.proposed_action)

  return (
    <div className={`anomaly ${anomaly.severity} ${resolved ? 'resolved' : ''}`}>
      <div className="row">
        <span className={`badge ${anomaly.severity}`}>
          {anomaly.severity === 'review' ? 'needs decision' : anomaly.severity}
        </span>
        <strong>{anomaly.code}</strong>
        {resolved && (
          <span className="badge ok">{overridden ? 'overridden' : 'approved'}</span>
        )}
      </div>
      <p style={{ margin: '6px 0' }}>{anomaly.message}</p>
      <div className="row">
        <span className="muted">
          {resolved ? 'Decision: ' : 'Proposal: '}
          <strong>{describeAction(anomaly.resolved_action || anomaly.proposed_action)}</strong>
        </span>
        {staged && (
          <>
            <span style={{ flex: 1 }} />
            {!resolved && (
              <button className="primary" onClick={() => onResolve(anomaly.id, { action: 'approve' })}>
                Approve proposal
              </button>
            )}
            <button onClick={() => setOverriding(!overriding)}>
              {overriding ? 'Cancel' : resolved ? 'Change decision' : 'Override…'}
            </button>
          </>
        )}
      </div>
      {overriding && staged && (
        <OverridePicker
          anomaly={anomaly}
          group={group}
          onPick={(body) => {
            setOverriding(false)
            onResolve(anomaly.id, body)
          }}
        />
      )}
    </div>
  )
}

function OverridePicker({ anomaly, group, onPick }) {
  const [date, setDate] = useState('')
  const [payer, setPayer] = useState(group.members[0]?.name || '')

  return (
    <div className="row" style={{ marginTop: 8, gap: 8 }}>
      <button onClick={() => onPick({ action: 'approve' })}>Approve proposal</button>
      <button onClick={() => onPick({ action: 'keep' })}>Keep row unchanged</button>
      <button onClick={() => onPick({ action: 'skip_row' })}>Exclude row</button>
      {['SETTLEMENT_AS_EXPENSE', 'PERSONAL_TRANSFER'].includes(anomaly.code) && (
        <button onClick={() => onPick({ action: 'record_as_settlement' })}>
          Record as settlement
        </button>
      )}
      {['DATE_FAR_PAST', 'DATE_OUT_OF_SEQUENCE', 'AMBIGUOUS_DATE', 'BAD_DATE'].includes(
        anomaly.code,
      ) && (
        <span className="row" style={{ gap: 6 }}>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} style={{ width: 160 }} />
          <button disabled={!date} onClick={() => onPick({ action: 'set_date', date })}>
            Use this date
          </button>
        </span>
      )}
      {anomaly.code === 'MISSING_PAYER' && (
        <span className="row" style={{ gap: 6 }}>
          <select value={payer} onChange={(e) => setPayer(e.target.value)} style={{ width: 160 }}>
            {group.members.map((m) => (
              <option key={m.id} value={m.name}>{m.name}</option>
            ))}
          </select>
          <button onClick={() => onPick({ action: 'set_payer', name: payer })}>
            This person paid
          </button>
        </span>
      )}
      {['UNKNOWN_PERSON', 'MEMBER_AFTER_DEPARTURE', 'MEMBER_BEFORE_JOINING'].includes(
        anomaly.code,
      ) &&
        anomaly.proposed_action.name && (
          <button
            onClick={() =>
              onPick({ action: 'remove_participant', name: anomaly.proposed_action.name })
            }
          >
            Remove {anomaly.proposed_action.name} from split
          </button>
        )}
    </div>
  )
}
