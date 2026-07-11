import { useState } from 'react'
import { api, setToken } from '../api.js'

export default function Login({ onAuth }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ username: '', password: '', first_name: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const path = mode === 'login' ? '/auth/login/' : '/auth/register/'
      const data = await api(path, { method: 'POST', body: form })
      setToken(data.token)
      onAuth({ username: data.username, first_name: data.first_name })
    } catch (err) {
      const body = err.body || {}
      setError(
        body.detail ||
          body.non_field_errors?.[0] ||
          Object.entries(body)
            .map(([k, v]) => `${k}: ${v}`)
            .join('; ') ||
          'Something went wrong',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <div className="card">
        <h2 style={{ color: 'var(--brand)' }}>SplitMate</h2>
        <p className="muted">Track shared expenses. Import your messy spreadsheet. Approve every fix.</p>
        <form onSubmit={submit}>
          <div className="field">
            <label>Username</label>
            <input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              autoFocus
              required
            />
          </div>
          {mode === 'register' && (
            <div className="field">
              <label>Display name</label>
              <input
                value={form.first_name}
                onChange={(e) => setForm({ ...form, first_name: e.target.value })}
              />
            </div>
          )}
          <div className="field">
            <label>Password {mode === 'register' && <span>(min 8 chars)</span>}</label>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </div>
          {error && <div className="error-box">{error}</div>}
          <div className="row">
            <button className="primary" disabled={busy} type="submit">
              {mode === 'login' ? 'Log in' : 'Create account'}
            </button>
            <button
              type="button"
              onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
            >
              {mode === 'login' ? 'New here? Register' : 'Have an account? Log in'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
