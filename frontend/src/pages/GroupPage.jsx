import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import BalancesTab from '../components/BalancesTab.jsx'
import ExpensesTab from '../components/ExpensesTab.jsx'
import { ArrowLeft, Check, Pencil, Trash, X } from '../components/icons.jsx'
import ImportsTab from '../components/ImportsTab.jsx'
import InsightsTab from '../components/InsightsTab.jsx'
import MembersTab from '../components/MembersTab.jsx'

const TABS = ['Expenses', 'Balances', 'Insights', 'Members', 'Import']

export default function GroupPage() {
  const { groupId } = useParams()
  const navigate = useNavigate()
  const [group, setGroup] = useState(null)
  const [tab, setTab] = useState('Expenses')
  const [renaming, setRenaming] = useState(false)
  const [newName, setNewName] = useState('')
  const [error, setError] = useState(null)

  const reload = useCallback(
    () => api(`/groups/${groupId}/`).then(setGroup).catch((e) => setError(e.message)),
    [groupId],
  )
  useEffect(() => {
    reload()
  }, [reload])

  const rename = async () => {
    if (!newName.trim() || newName === group.name) {
      setRenaming(false)
      return
    }
    try {
      await api(`/groups/${groupId}/`, { method: 'PATCH', body: { name: newName.trim() } })
      setRenaming(false)
      reload()
    } catch (e) {
      setError(e.body?.detail || e.message)
    }
  }

  const removeGroup = async () => {
    if (
      !window.confirm(
        `Delete "${group.name}" and ALL its expenses, settlements and imports? This cannot be undone.`,
      )
    )
      return
    try {
      await api(`/groups/${groupId}/`, { method: 'DELETE' })
      navigate('/')
    } catch (e) {
      setError(e.body?.detail || e.message)
    }
  }

  if (error)
    return (
      <div className="page">
        <div className="error-box">{error}</div>
      </div>
    )
  if (!group) return null

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 14 }}>
        <button className="ghost" onClick={() => navigate('/')}>
          <ArrowLeft size={15} /> Groups
        </button>
        {renaming ? (
          <span className="row" style={{ gap: 6 }}>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && rename()}
              autoFocus
              style={{ width: 240, fontWeight: 700, fontSize: 17 }}
            />
            <button className="icon-btn primary" onClick={rename} title="Save name">
              <Check size={14} />
            </button>
            <button className="icon-btn" onClick={() => setRenaming(false)} title="Cancel">
              <X size={14} />
            </button>
          </span>
        ) : (
          <>
            <h1 style={{ margin: 0 }}>{group.name}</h1>
            <button
              className="icon-btn ghost"
              title="Rename group"
              onClick={() => {
                setNewName(group.name)
                setRenaming(true)
              }}
            >
              <Pencil size={14} />
            </button>
          </>
        )}
        <span className="badge neutral">base currency {group.base_currency}</span>
        <span className="spacer" style={{ flex: 1 }} />
        <button className="danger" onClick={removeGroup} title="Delete this group">
          <Trash size={14} /> Delete group
        </button>
      </div>
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t} className={t === tab ? 'active' : ''} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
      {tab === 'Expenses' && <ExpensesTab group={group} />}
      {tab === 'Balances' && <BalancesTab group={group} />}
      {tab === 'Insights' && <InsightsTab group={group} />}
      {tab === 'Members' && <MembersTab group={group} onChange={reload} />}
      {tab === 'Import' && <ImportsTab group={group} onCommitted={reload} />}
    </div>
  )
}
