import { useCallback, useEffect, useState } from 'react'
import { api, fmtMoney } from '../api.js'
import ExpenseForm from './ExpenseForm.jsx'

export default function ExpensesTab({ group }) {
  const [expenses, setExpenses] = useState(null)
  const [settlements, setSettlements] = useState([])
  const [editing, setEditing] = useState(null) // null | 'new' | expense
  const [expanded, setExpanded] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    api(`/groups/${group.id}/expenses/`).then(setExpenses).catch((e) => setError(e.message))
    api(`/groups/${group.id}/settlements/`).then(setSettlements).catch(() => {})
  }, [group.id])
  useEffect(() => {
    load()
  }, [load])

  const remove = async (expense) => {
    if (!window.confirm(`Delete "${expense.description}"?`)) return
    await api(`/groups/${group.id}/expenses/${expense.id}/`, { method: 'DELETE' })
    load()
  }

  if (!expenses) return null
  const rows = [
    ...expenses.map((e) => ({ ...e, _type: 'expense' })),
    ...settlements.map((s) => ({ ...s, _type: 'settlement' })),
  ].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))

  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="muted">
          {expenses.length} expenses · {settlements.length} settlements
        </span>
        <span className="spacer" style={{ flex: 1 }} />
        <button className="primary" onClick={() => setEditing('new')}>
          Add expense
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Paid by</th>
              <th>Split</th>
              <th style={{ textAlign: 'right' }}>Amount</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) =>
              r._type === 'settlement' ? (
                <tr key={`s${r.id}`}>
                  <td className="mono">{r.date}</td>
                  <td>
                    <span className="badge ok">settlement</span> {r.payer_name} paid{' '}
                    {r.payee_name}
                    {r.note && <div className="muted">{r.note}</div>}
                  </td>
                  <td>{r.payer_name}</td>
                  <td>→ {r.payee_name}</td>
                  <td className="mono" style={{ textAlign: 'right' }}>
                    {fmtMoney(r.amount_base_minor)}
                  </td>
                  <td />
                </tr>
              ) : (
                <ExpenseRow
                  key={`e${r.id}`}
                  expense={r}
                  group={group}
                  expanded={expanded === r.id}
                  onToggle={() => setExpanded(expanded === r.id ? null : r.id)}
                  onEdit={() => setEditing(r)}
                  onDelete={() => remove(r)}
                />
              ),
            )}
          </tbody>
        </table>
      </div>
      {editing && (
        <ExpenseForm
          group={group}
          expense={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
          }}
        />
      )}
    </>
  )
}

function ExpenseRow({ expense, group, expanded, onToggle, onEdit, onDelete }) {
  const isRefund = expense.amount_minor < 0
  const isForeign = expense.currency !== group.base_currency
  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td className="mono">{expense.date}</td>
        <td>
          {expense.description}{' '}
          {isRefund && <span className="badge ok">refund</span>}{' '}
          {expense.source_row_number && (
            <span className="badge neutral" title="Imported from spreadsheet">
              CSV row {expense.source_row_number}
            </span>
          )}
          {expense.notes && <div className="muted">{expense.notes}</div>}
        </td>
        <td>{expense.paid_by_name}</td>
        <td>
          <span className="badge info">{expense.split_type}</span>{' '}
          <span className="muted">{expense.splits.length} people</span>
        </td>
        <td className="mono" style={{ textAlign: 'right' }}>
          {fmtMoney(expense.amount_base_minor)}
          {isForeign && (
            <div className="muted">
              {fmtMoney(expense.amount_minor, expense.currency)} @ {Number(expense.fx_rate)}
            </div>
          )}
        </td>
        <td style={{ whiteSpace: 'nowrap' }}>
          <button onClick={(e) => { e.stopPropagation(); onEdit() }}>Edit</button>{' '}
          <button className="danger" onClick={(e) => { e.stopPropagation(); onDelete() }}>
            Delete
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} style={{ background: '#fafbfc' }}>
            <strong>Split breakdown</strong>
            <table style={{ marginTop: 6 }}>
              <tbody>
                {expense.splits.map((s) => (
                  <tr key={s.member}>
                    <td>{s.member_name}</td>
                    <td className="muted">
                      {s.input_percent != null && `${Number(s.input_percent)}%`}
                      {s.input_share_units != null && `${s.input_share_units} share(s)`}
                      {s.input_amount_minor != null && 'exact amount'}
                      {s.input_percent == null &&
                        s.input_share_units == null &&
                        s.input_amount_minor == null &&
                        'equal'}
                    </td>
                    <td className="mono" style={{ textAlign: 'right' }}>
                      {fmtMoney(s.share_base_minor)}
                    </td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={2}>
                    <strong>Total</strong>
                  </td>
                  <td className="mono" style={{ textAlign: 'right' }}>
                    <strong>
                      {fmtMoney(
                        expense.splits.reduce((sum, s) => sum + s.share_base_minor, 0),
                      )}
                    </strong>
                  </td>
                </tr>
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  )
}
