import { useState } from 'react'
import { api } from '../api.js'
import { Sparkle } from './icons.jsx'

// Create or edit an expense with any of the four split types. Amounts are
// entered in major units and converted to minor units at the API edge.
// `proposal` (optional) is an AI Smart-Add result used to prefill a new
// expense — the human reviews it here before anything is saved.

export default function ExpenseForm({ group, expense, proposal, onClose, onSaved }) {
  const members = group.members
  const ai = proposal?.expense
  const [form, setForm] = useState(() =>
    expense
      ? {
          description: expense.description,
          date: expense.date,
          paid_by: expense.paid_by,
          currency: expense.currency,
          amount: (Math.abs(expense.amount_minor) / 100).toString(),
          isRefund: expense.amount_minor < 0,
          fx_rate: Number(expense.fx_rate),
          split_type: expense.split_type,
          notes: expense.notes || '',
        }
      : {
          description: ai?.description || '',
          date: ai?.date || new Date().toISOString().slice(0, 10),
          paid_by: ai?.paid_by_id || members[0]?.id,
          currency: ai?.currency || group.base_currency,
          amount: ai?.amount ? String(ai.amount) : '',
          isRefund: false,
          fx_rate: 1,
          split_type: ai?.split_type || 'equal',
          notes: ai?.notes || '',
        },
  )
  const [selected, setSelected] = useState(() => {
    const map = {}
    if (expense) {
      for (const s of expense.splits) {
        map[s.member] = {
          on: true,
          percent: s.input_percent != null ? Number(s.input_percent) : '',
          units: s.input_share_units ?? '',
          amount: s.input_amount_minor != null ? s.input_amount_minor / 100 : '',
        }
      }
    } else if (ai?.participants?.length) {
      for (const p of ai.participants) {
        if (p.member_id)
          map[p.member_id] = {
            on: true,
            percent: p.percent ?? '',
            units: p.units ?? '',
            amount: p.amount ?? '',
          }
      }
    } else {
      for (const m of members) {
        if (!m.left_on) map[m.id] = { on: true, percent: '', units: '', amount: '' }
      }
    }
    for (const m of members) {
      if (!map[m.id]) map[m.id] = { on: false, percent: '', units: '', amount: '' }
    }
    return map
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const setPart = (id, k, v) =>
    setSelected((s) => ({ ...s, [id]: { ...s[id], [k]: v } }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const sign = form.isRefund ? -1 : 1
    const participants = members
      .filter((m) => selected[m.id].on)
      .map((m) => {
        const p = { member_id: m.id }
        const sel = selected[m.id]
        if (form.split_type === 'percentage') p.percent = Number(sel.percent || 0)
        if (form.split_type === 'share') p.units = Number(sel.units || 0)
        if (form.split_type === 'unequal')
          p.amount_minor = sign * Math.round(Number(sel.amount || 0) * 100)
        return p
      })
    try {
      const body = {
        description: form.description,
        date: form.date,
        paid_by: Number(form.paid_by),
        currency: form.currency,
        amount_minor: sign * Math.round(Number(form.amount) * 100),
        fx_rate: form.currency === group.base_currency ? 1 : Number(form.fx_rate),
        split_type: form.split_type,
        notes: form.notes,
        participants,
      }
      if (expense) {
        await api(`/groups/${group.id}/expenses/${expense.id}/`, { method: 'PUT', body })
      } else {
        await api(`/groups/${group.id}/expenses/`, { method: 'POST', body })
      }
      onSaved()
    } catch (err) {
      const b = err.body
      setError(
        Array.isArray(b) ? b.join('; ')
        : b?.non_field_errors?.join('; ') || b?.detail || err.message,
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{expense ? 'Edit expense' : proposal ? 'Confirm the parsed expense' : 'Add expense'}</h3>
        {proposal && (
          <p className="ai-suggestion" style={{ marginTop: 0 }}>
            <Sparkle size={13} />
            <span>
              Prefilled by {proposal.source === 'gemini' ? 'Gemini' : 'the offline parser'} —
              check every field before saving.
            </span>
          </p>
        )}
        {proposal?.warnings?.map((w, i) => (
          <div key={i} className="error-box" style={{ margin: '6px 0' }}>{w}</div>
        ))}
        <form onSubmit={submit}>
          <div className="field">
            <label>Description</label>
            <input
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="row">
            <div className="field" style={{ flex: 1 }}>
              <label>Date</label>
              <input type="date" value={form.date} onChange={(e) => set('date', e.target.value)} required />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Paid by</label>
              <select value={form.paid_by} onChange={(e) => set('paid_by', e.target.value)}>
                {members.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="row">
            <div className="field" style={{ flex: 1 }}>
              <label>Amount</label>
              <input
                type="number" step="0.01" min="0.01"
                value={form.amount}
                onChange={(e) => set('amount', e.target.value)}
                required
              />
            </div>
            <div className="field" style={{ width: 110 }}>
              <label>Currency</label>
              <select value={form.currency} onChange={(e) => set('currency', e.target.value)}>
                <option>INR</option>
                <option>USD</option>
                <option>EUR</option>
              </select>
            </div>
            {form.currency !== group.base_currency && (
              <div className="field" style={{ width: 140 }}>
                <label>Rate → {group.base_currency}</label>
                <input
                  type="number" step="0.0001" min="0.0001"
                  value={form.fx_rate}
                  onChange={(e) => set('fx_rate', e.target.value)}
                  required
                />
              </div>
            )}
          </div>
          <div className="field">
            <label>
              <input
                type="checkbox"
                checked={form.isRefund}
                onChange={(e) => set('isRefund', e.target.checked)}
                style={{ width: 'auto', marginRight: 6 }}
              />
              This is a refund (money flows back to participants)
            </label>
          </div>
          <div className="field">
            <label>Split type</label>
            <select value={form.split_type} onChange={(e) => set('split_type', e.target.value)}>
              <option value="equal">Equal — everyone selected pays the same</option>
              <option value="unequal">Unequal — exact amount per person</option>
              <option value="percentage">Percentage — % per person</option>
              <option value="share">Shares — proportional units (e.g. 2 : 1)</option>
            </select>
          </div>
          <div className="field">
            <label>Split between</label>
            <div className="split-grid">
              {members.map((m) => (
                <SplitRow
                  key={m.id}
                  member={m}
                  splitType={form.split_type}
                  sel={selected[m.id]}
                  setPart={setPart}
                />
              ))}
            </div>
          </div>
          <div className="field">
            <label>Notes</label>
            <input value={form.notes} onChange={(e) => set('notes', e.target.value)} />
          </div>
          {error && <div className="error-box">{error}</div>}
          <div className="row">
            <button className="primary" type="submit" disabled={busy}>
              {expense ? 'Save changes' : 'Add expense'}
            </button>
            <button type="button" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function SplitRow({ member, splitType, sel, setPart }) {
  return (
    <>
      <input
        type="checkbox"
        checked={sel.on}
        onChange={(e) => setPart(member.id, 'on', e.target.checked)}
        style={{ width: 'auto' }}
      />
      <span>
        {member.name}
        {member.left_on && <span className="muted"> (left {member.left_on})</span>}
        {member.is_guest && <span className="badge neutral">guest</span>}
      </span>
      {splitType === 'percentage' && (
        <input
          type="number" step="0.01" placeholder="%"
          disabled={!sel.on}
          value={sel.percent}
          onChange={(e) => setPart(member.id, 'percent', e.target.value)}
        />
      )}
      {splitType === 'share' && (
        <input
          type="number" step="1" min="0" placeholder="units"
          disabled={!sel.on}
          value={sel.units}
          onChange={(e) => setPart(member.id, 'units', e.target.value)}
        />
      )}
      {splitType === 'unequal' && (
        <input
          type="number" step="0.01" placeholder="amount"
          disabled={!sel.on}
          value={sel.amount}
          onChange={(e) => setPart(member.id, 'amount', e.target.value)}
        />
      )}
      {splitType === 'equal' && <span className="muted">equal</span>}
    </>
  )
}
