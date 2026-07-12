import { useState } from 'react'
import { api } from '../api.js'
import { Avatar, Plus, Trash } from './icons.jsx'

// Membership windows are first-class: an expense dated outside someone's
// window is flagged by the importer. Edit join/leave dates here, then
// re-run detection on a staged import.

export default function MembersTab({ group, onChange }) {
  const [form, setForm] = useState({ name: '', joined_on: '', is_guest: false })
  const [error, setError] = useState(null)

  const add = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await api(`/groups/${group.id}/members/`, {
        method: 'POST',
        body: {
          name: form.name,
          joined_on: form.joined_on || null,
          is_guest: form.is_guest,
        },
      })
      setForm({ name: '', joined_on: '', is_guest: false })
      onChange()
    } catch (err) {
      setError(err.body?.name?.[0] || err.message)
    }
  }

  const update = async (member, patch) => {
    setError(null)
    try {
      await api(`/groups/${group.id}/members/${member.id}/`, {
        method: 'PATCH',
        body: patch,
      })
      onChange()
    } catch (err) {
      setError(err.body?.detail || err.message)
    }
  }

  const remove = async (member) => {
    if (!window.confirm(`Remove ${member.name} from the group?`)) return
    setError(null)
    try {
      await api(`/groups/${group.id}/members/${member.id}/`, { method: 'DELETE' })
      onChange()
    } catch (err) {
      setError(err.body?.[0] || err.body?.detail || err.message)
    }
  }

  return (
    <>
      <div className="card">
        <h3>Members</h3>
        <p className="muted">
          Set a leave date instead of deleting someone — their history stays intact
          and new expenses after that date get flagged.
        </p>
        {error && <div className="error-box">{error}</div>}
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Joined</th>
              <th>Left</th>
              <th>Guest</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {group.members.map((m) => (
              <tr key={m.id}>
                <td>
                  <span className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
                    <Avatar name={m.name} size={24} /> {m.name}
                    {m.is_guest && <span className="badge neutral">guest</span>}
                  </span>
                </td>
                <td>
                  <input
                    type="date"
                    defaultValue={m.joined_on || ''}
                    onBlur={(e) =>
                      e.target.value !== (m.joined_on || '') &&
                      update(m, { joined_on: e.target.value || null })
                    }
                    style={{ width: 160 }}
                  />
                </td>
                <td>
                  <input
                    type="date"
                    defaultValue={m.left_on || ''}
                    onBlur={(e) =>
                      e.target.value !== (m.left_on || '') &&
                      update(m, { left_on: e.target.value || null })
                    }
                    style={{ width: 160 }}
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={m.is_guest}
                    onChange={(e) => update(m, { is_guest: e.target.checked })}
                    style={{ width: 'auto' }}
                  />
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button
                    className="icon-btn danger"
                    title="Remove member (only possible with no expense history)"
                    onClick={() => remove(m)}
                  >
                    <Trash size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Add member</h3>
        <form className="row" onSubmit={add}>
          <div style={{ flex: 2 }}>
            <label>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div style={{ flex: 1 }}>
            <label>Joined on (optional)</label>
            <input
              type="date"
              value={form.joined_on}
              onChange={(e) => setForm({ ...form, joined_on: e.target.value })}
            />
          </div>
          <div>
            <label>Guest</label>
            <input
              type="checkbox"
              checked={form.is_guest}
              onChange={(e) => setForm({ ...form, is_guest: e.target.checked })}
              style={{ width: 'auto' }}
            />
          </div>
          <div style={{ alignSelf: 'flex-end' }}>
            <button className="primary" type="submit"><Plus size={15} /> Add</button>
          </div>
        </form>
      </div>
    </>
  )
}
