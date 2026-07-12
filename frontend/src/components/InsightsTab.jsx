import { useCallback, useEffect, useState } from 'react'
import { api, fmtMoney } from '../api.js'
import { Avatar, Bot, Calendar, Chart, Coins, Trend } from './icons.jsx'

// Spending reports: stat cards per month, category breakdown, trend chart,
// and an AI-written digest (Gemini when configured, template otherwise).

const CAT_COLORS = [
  '#0ea5a0', '#6366f1', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6', '#f97316', '#64748b',
]

const monthLabel = (ym) => {
  const [y, m] = ym.split('-')
  return new Date(y, m - 1).toLocaleString('en', { month: 'short', year: 'numeric' })
}

export default function InsightsTab({ group }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(
    () => api(`/groups/${group.id}/ai/insights/`).then(setData).catch((e) => setError(e.message)),
    [group.id],
  )
  useEffect(() => {
    load()
  }, [load])

  if (error) return <div className="error-box">{error}</div>
  if (!data)
    return (
      <div className="card empty pulse">
        <div className="glyph">📊</div>
        Crunching the numbers…
      </div>
    )

  if (!data.expense_count)
    return (
      <div className="card empty">
        <div className="glyph">📊</div>
        No expenses yet — insights appear as soon as the group starts spending.
      </div>
    )

  const maxMonth = Math.max(...data.months.map((m) => m.total_minor), 1)
  const maxCat = Math.max(...data.categories.map((c) => c.total_minor), 1)
  const recentMonths = data.months.slice(-4)

  return (
    <>
      <div className="ai-panel">
        <h3>
          <Bot size={17} /> Group digest
          <span className="ai-source" style={{ fontWeight: 400 }}>
            {data.source === 'gemini' ? '· written by Gemini' : '· offline summary'}
          </span>
        </h3>
        <p className="digest" style={{ margin: 0 }}>{data.digest}</p>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-title"><Coins size={15} /> All time</div>
          <div className="stat-row">
            <Coins size={13} /> Total
            <span className="val big">{fmtMoney(data.total_minor, data.base_currency)}</span>
          </div>
          <div className="stat-row">
            <Calendar size={13} /> Expenses
            <span className="val">{data.expense_count}</span>
          </div>
          <div className="stat-row">
            <Trend size={13} /> Avg / expense
            <span className="val">
              {fmtMoney(Math.round(data.total_minor / data.expense_count), data.base_currency)}
            </span>
          </div>
        </div>
        {recentMonths.map((m) => (
          <div className="stat-card" key={m.month}>
            <div className="stat-title"><Calendar size={15} /> {monthLabel(m.month)}</div>
            <div className="stat-row">
              <Coins size={13} /> Total
              <span className="val big">{fmtMoney(m.total_minor, data.base_currency)}</span>
            </div>
            <div className="stat-row">
              <Calendar size={13} /> Expenses
              <span className="val">{m.count}</span>
            </div>
            <div className="stat-row">
              <Trend size={13} /> Avg / expense
              <span className="val">
                {fmtMoney(Math.round(m.total_minor / Math.max(m.count, 1)), data.base_currency)}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="row" style={{ alignItems: 'stretch' }}>
        <div className="card" style={{ flex: 1.2, minWidth: 320, marginBottom: 16 }}>
          <h3><Chart size={15} style={{ color: 'var(--brand)' }} /> Spending by category</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Auto-categorized from descriptions — no tagging needed.
          </p>
          {data.categories.map((c, i) => (
            <div className="cat-row" key={c.category}>
              <span className="dot" style={{ background: CAT_COLORS[i % CAT_COLORS.length] }} />
              <span className="name">{c.category}</span>
              <span className="track">
                <span
                  className="fill"
                  style={{
                    width: `${(c.total_minor / maxCat) * 100}%`,
                    background: CAT_COLORS[i % CAT_COLORS.length],
                  }}
                />
              </span>
              <span className="amt">
                {fmtMoney(c.total_minor, data.base_currency)}
                <span className="muted"> · {Math.round((c.total_minor / data.total_minor) * 100)}%</span>
              </span>
            </div>
          ))}
        </div>

        <div className="card" style={{ flex: 1, minWidth: 280, marginBottom: 16 }}>
          <h3><Trend size={15} style={{ color: 'var(--brand)' }} /> Monthly trend</h3>
          <p className="muted" style={{ marginTop: 0 }}>Total spending per month.</p>
          <div className="trend-chart">
            {data.months.slice(-8).map((m) => (
              <div className="trend-col" key={m.month} title={fmtMoney(m.total_minor, data.base_currency)}>
                <div
                  className="bar-v"
                  style={{ height: `${Math.max((m.total_minor / maxMonth) * 100, 3)}%` }}
                />
                <span className="lbl">{monthLabel(m.month).split(' ')[0]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Who fronts the money</h3>
        <table>
          <tbody>
            {data.top_payers.map((p) => (
              <tr key={p.name}>
                <td>
                  <span className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
                    <Avatar name={p.name} size={24} /> {p.name}
                  </span>
                </td>
                <td className="mono" style={{ textAlign: 'right' }}>
                  {fmtMoney(p.paid_minor, data.base_currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
