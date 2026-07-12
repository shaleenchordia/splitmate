import { useCallback, useEffect, useState } from 'react'
import { api, fmtMoney } from '../api.js'
import ExpenseForm from './ExpenseForm.jsx'
import { Avatar, Pencil, Plus, Trash } from './icons.jsx'
import SmartAdd from './SmartAdd.jsx'

export default function ExpensesTab({ group }) {
  const [expenses, setExpenses] = useState(null)
  const [settlements, setSettlements] = useState([])
  const [editing, setEditing] = useState(null) // null | 'new' | expense
  const [proposal, setProposal] = useState(null) // AI Smart-Add result
  const [editingSettlement, setEditingSettlement] = useState(null)
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

  const removeSettlement = async (s) => {
    if (!window.confirm(`Delete the settlement ${s.payer_name} → ${s.payee_name}?`)) return
    await api(`/groups/${group.id}/settlements/${s.id}/`, { method: 'DELETE' })
    load()
  }

  if (!expenses) return null
  const rows = [
    ...expenses.map((e) => ({ ...e, _type: 'expense' })),
    ...settlements.map((s) => ({ ...s, _type: 'settlement' })),
  ].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))

  return (
    <>
      <SmartAdd
        group={group}
        onProposal={(p) => {
          setProposal(p)
          setEditing('new')
        }}
      />
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="muted">
          {expenses.length} expenses · {settlements.length} settlements
        </span>
        <span className="spacer" style={{ flex: 1 }} />
        <button
          className="primary"
          onClick={() => {
            setProposal(null)
            setEditing('new')
          }}
        >
          <Plus size={15} /> Add expense
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {rows.length === 0 && (
          <div className="empty">
            <div className="glyph">🧾</div>
            No expenses yet — add one above, describe it to Smart add, or import a
            spreadsheet from the Import tab.
          </div>
        )}
        {rows.length > 0 && (
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
                    <td>
                      <span className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                        <Avatar name={r.payer_name} size={22} /> {r.payer_name}
                      </span>
                    </td>
                    <td>→ {r.payee_name}</td>
                    <td className="mono" style={{ textAlign: 'right' }}>
                      {fmtMoney(r.amount_base_minor)}
                    </td>
                    <td style={{ whiteSpace: 'nowrap', textAlign: 'right' }}>
                      <button className="icon-btn ghost" title="Edit settlement"
                        onClick={() => setEditingSettlement(r)}>
                        <Pencil size={14} />
                      </button>{' '}
                      <button className="icon-btn danger" title="Delete settlement"
                        onClick={() => removeSettlement(r)}>
                        <Trash size={14} />
                      </button>
                    </td>
                  </tr>
                ) : (
                  <ExpenseRow
                    key={`e${r.id}`}
                    expense={r}
                    group={group}
                    expanded={expanded === r.id}
                    onToggle={() => setExpanded(expanded === r.id ? null : r.id)}
                    onEdit={() => {
                      setProposal(null)
                      setEditing(r)
                    }}
                    onDelete={() => remove(r)}
                  />
                ),
              )}
            </tbody>
          </table>
        )}
      </div>
      {editing && (
        <ExpenseForm
          group={group}
          expense={editing === 'new' ? null : editing}
          proposal={editing === 'new' ? proposal : null}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            setProposal(null)
            load()
          }}
        />
      )}
      {editingSettlement && (
        <SettlementForm
          group={group}
          settlement={editingSettlement}
          onClose={() => setEditingSettlement(null)}
          onSaved={() => {
            setEditingSettlement(null)
            load()
          }}
        />
      )}
    </>
  )
}

// Edit a recorded settlement (who/when/how much) — full CRUD on payments.
function SettlementForm({ group, settlement, onClose, onSaved }) {
  const [form, setForm] = useState({
    payer: settlement.payer,
    payee: settlement.payee,
    amount: (settlement.amount_base_minor / 100).toString(),
    date: settlement.date,
    note: settlement.note || '',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api(`/groups/${group.id}/settlements/${settlement.id}/`, {
        method: 'PATCH',
        body: {
          payer: Number(form.payer),
          payee: Number(form.payee),
          amount_base_minor: Math.round(Number(form.amount) * 100),
          date: form.date,
          note: form.note,
        },
      })
      onSaved()
    } catch (err) {
      setError(err.body?.detail || err.body?.non_field_errors?.join('; ') || err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Edit settlement</h3>
        <form onSubmit={submit}>
          <div className="row">
            <div className="field" style={{ flex: 1 }}>
              <label>Payer</label>
              <select value={form.payer} onChange={(e) => setForm({ ...form, payer: e.target.value })}>
                {group.members.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Payee</label>
              <select value={form.payee} onChange={(e) => setForm({ ...form, payee: e.target.value })}>
                {group.members.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="row">
            <div className="field" style={{ flex: 1 }}>
              <label>Amount ({group.base_currency})</label>
              <input
                type="number" step="0.01" min="0.01"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
                required
              />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Date</label>
              <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} required />
            </div>
          </div>
          <div className="field">
            <label>Note</label>
            <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </div>
          {error && <div className="error-box">{error}</div>}
          <div className="row">
            <button className="primary" type="submit" disabled={busy}>Save changes</button>
            <button type="button" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
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
        <td>
          <span className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
            <Avatar name={expense.paid_by_name} size={22} /> {expense.paid_by_name}
          </span>
        </td>
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
        <td style={{ whiteSpace: 'nowrap', textAlign: 'right' }}>
          <button className="icon-btn ghost" title="Edit"
            onClick={(e) => { e.stopPropagation(); onEdit() }}>
            <Pencil size={14} />
          </button>{' '}
          <button className="icon-btn danger" title="Delete"
            onClick={(e) => { e.stopPropagation(); onDelete() }}>
            <Trash size={14} />
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} className="row-detail" style={{ background: 'var(--card-hover)' }}>
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
