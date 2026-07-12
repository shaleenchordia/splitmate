import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { ArrowRight, Avatar, Plus, Users } from '../components/icons.jsx'

export default function Groups() {
  const [groups, setGroups] = useState(null)
  const [name, setName] = useState('')
  const [error, setError] = useState(null)

  const load = () => api('/groups/').then(setGroups).catch((e) => setError(e.message))
  useEffect(() => {
    load()
  }, [])

  const create = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    await api('/groups/', { method: 'POST', body: { name, base_currency: 'INR' } })
    setName('')
    load()
  }

  return (
    <div className="page">
      <h1>Your groups</h1>
      <p className="muted" style={{ marginTop: -6 }}>
        Every flat, trip or team gets its own ledger.
      </p>
      {error && <div className="error-box">{error}</div>}
      <div className="card">
        <form className="row" onSubmit={create}>
          <div style={{ flex: 1 }}>
            <input
              placeholder="New group name (e.g. Flat 42)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <button className="primary" type="submit">
            <Plus size={15} /> Create group
          </button>
        </form>
      </div>
      {groups?.length === 0 && (
        <div className="card empty">
          <div className="glyph">🏠</div>
          No groups yet — create one above to get started.
        </div>
      )}
      {groups?.map((g) => (
        <Link key={g.id} to={`/groups/${g.id}`} style={{ color: 'inherit' }}>
          <div className="card row hoverable">
            <div style={{ flex: 1 }}>
              <h3 style={{ marginBottom: 4 }}>{g.name}</h3>
              <span className="row" style={{ gap: 4 }}>
                {g.members.slice(0, 6).map((m) => (
                  <Avatar key={m.id} name={m.name} size={24} />
                ))}
                <span className="muted" style={{ marginLeft: 6 }}>
                  <Users size={12} /> {g.members.length} members · {g.base_currency}
                </span>
              </span>
            </div>
            <ArrowRight size={17} style={{ color: 'var(--muted)' }} />
          </div>
        </Link>
      ))}
    </div>
  )
}
