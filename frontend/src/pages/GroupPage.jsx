import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import BalancesTab from '../components/BalancesTab.jsx'
import ExpensesTab from '../components/ExpensesTab.jsx'
import ImportsTab from '../components/ImportsTab.jsx'
import MembersTab from '../components/MembersTab.jsx'

const TABS = ['Expenses', 'Balances', 'Members', 'Import']

export default function GroupPage() {
  const { groupId } = useParams()
  const navigate = useNavigate()
  const [group, setGroup] = useState(null)
  const [tab, setTab] = useState('Expenses')
  const [error, setError] = useState(null)

  const reload = useCallback(
    () => api(`/groups/${groupId}/`).then(setGroup).catch((e) => setError(e.message)),
    [groupId],
  )
  useEffect(() => {
    reload()
  }, [reload])

  if (error)
    return (
      <div className="page">
        <div className="error-box">{error}</div>
      </div>
    )
  if (!group) return null

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 10 }}>
        <button onClick={() => navigate('/')}>← Groups</button>
        <h1 style={{ margin: 0 }}>{group.name}</h1>
        <span className="muted">base currency {group.base_currency}</span>
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
      {tab === 'Members' && <MembersTab group={group} onChange={reload} />}
      {tab === 'Import' && <ImportsTab group={group} onCommitted={reload} />}
    </div>
  )
}
