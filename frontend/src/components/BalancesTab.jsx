import { useCallback, useEffect, useState } from 'react'
import { api, fmtMoney } from '../api.js'

export default function BalancesTab({ group }) {
  const [data, setData] = useState(null)
  const [ledger, setLedger] = useState(null) // {member, entries, net_minor}
  const [error, setError] = useState(null)
  const [settling, setSettling] = useState(null) // suggestion being recorded

  const load = useCallback(
    () => api(`/groups/${group.id}/balances/`).then(setData).catch((e) => setError(e.message)),
    [group.id],
  )
  useEffect(() => {
    load()
  }, [load])

  const openLedger = async (memberId) => {
    setLedger(await api(`/groups/${group.id}/members/${memberId}/ledger/`))
  }

  const recordSettlement = async (s) => {
    setSettling(s)
    try {
      await api(`/groups/${group.id}/settlements/`, {
        method: 'POST',
        body: {
          payer: s.payer_id,
          payee: s.payee_id,
          amount_base_minor: s.amount_minor,
          date: new Date().toISOString().slice(0, 10),
          note: 'Settle up',
        },
      })
      await load()
    } finally {
      setSettling(null)
    }
  }

  if (error) return <div className="error-box">{error}</div>
  if (!data) return null

  return (
    <>
      <div className="card">
        <h3>Net balances</h3>
        <p className="muted">
          Positive = the group owes them. Click a person to see every expense behind
          their number.
        </p>
        <table>
          <tbody>
            {data.balances.map((b) => (
              <tr key={b.member_id} className="clickable" onClick={() => openLedger(b.member_id)}>
                <td>
                  {b.name}
                  {b.is_guest && <span className="badge neutral"> guest</span>}
                  {b.left_on && <span className="muted"> (left {b.left_on})</span>}
                </td>
                <td className="mono" style={{ textAlign: 'right' }}>
                  <span className={b.net_minor > 0 ? 'pos' : b.net_minor < 0 ? 'neg' : ''}>
                    {b.net_minor > 0 ? 'is owed ' : b.net_minor < 0 ? 'owes ' : 'settled '}
                    {b.net_minor !== 0 && fmtMoney(Math.abs(b.net_minor))}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Settle up — who pays whom</h3>
        <p className="muted">
          The minimum set of transfers that clears every balance. Record one when the
          money actually moves.
        </p>
        {data.settle_up.length === 0 && <p>Everyone is settled. 🎉</p>}
        <table>
          <tbody>
            {data.settle_up.map((s, i) => (
              <tr key={i}>
                <td>
                  <strong>{s.payer}</strong> pays <strong>{s.payee}</strong>
                </td>
                <td className="mono">{fmtMoney(s.amount_minor)}</td>
                <td style={{ textAlign: 'right' }}>
                  <button disabled={settling === s} onClick={() => recordSettlement(s)}>
                    Record payment
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {ledger && (
        <div className="modal-backdrop" onClick={() => setLedger(null)}>
          <div className="modal" style={{ width: 760 }} onClick={(e) => e.stopPropagation()}>
            <h3>{ledger.member.name} — every number, explained</h3>
            <p className="muted">
              Each row shows what {ledger.member.name} paid and their owed share. The
              running sum of the effect column IS their balance — nothing else touches it.
            </p>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Item</th>
                  <th style={{ textAlign: 'right' }}>Paid</th>
                  <th style={{ textAlign: 'right' }}>Owed share</th>
                  <th style={{ textAlign: 'right' }}>Effect</th>
                </tr>
              </thead>
              <tbody>
                {ledger.entries.map((e, i) => (
                  <tr key={i}>
                    <td className="mono">{e.date}</td>
                    <td>
                      {e.description}
                      {e.type === 'settlement' && <span className="badge ok"> settlement</span>}
                      {e.currency && e.currency !== group.base_currency && (
                        <div className="muted">
                          {fmtMoney(e.amount_minor, e.currency)} @ {Number(e.fx_rate)}
                        </div>
                      )}
                    </td>
                    <td className="mono" style={{ textAlign: 'right' }}>
                      {e.paid_minor ? fmtMoney(e.paid_minor) : '—'}
                    </td>
                    <td className="mono" style={{ textAlign: 'right' }}>
                      {e.owed_minor ? fmtMoney(e.owed_minor) : '—'}
                    </td>
                    <td className="mono" style={{ textAlign: 'right' }}>
                      <span className={e.effect_minor > 0 ? 'pos' : e.effect_minor < 0 ? 'neg' : ''}>
                        {fmtMoney(e.effect_minor)}
                      </span>
                    </td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={4}><strong>Net balance</strong></td>
                  <td className="mono" style={{ textAlign: 'right' }}>
                    <strong className={ledger.net_minor > 0 ? 'pos' : ledger.net_minor < 0 ? 'neg' : ''}>
                      {fmtMoney(ledger.net_minor)}
                    </strong>
                  </td>
                </tr>
              </tbody>
            </table>
            <div className="row" style={{ marginTop: 12 }}>
              <button onClick={() => setLedger(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
