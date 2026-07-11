import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'

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
          <button className="primary" type="submit">Create group</button>
        </form>
      </div>
      {groups?.length === 0 && (
        <p className="muted">No groups yet — create one to get started.</p>
      )}
      {groups?.map((g) => (
        <Link key={g.id} to={`/groups/${g.id}`}>
          <div className="card row">
            <div style={{ flex: 1 }}>
              <h3>{g.name}</h3>
              <span className="muted">
                {g.members.length} members · base currency {g.base_currency}
              </span>
            </div>
            <span>→</span>
          </div>
        </Link>
      ))}
    </div>
  )
}
