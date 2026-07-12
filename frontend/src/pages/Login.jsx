import { useState } from 'react'
import { api, setToken } from '../api.js'
import { Wallet } from '../components/icons.jsx'

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
      <div style={{ textAlign: 'center', marginBottom: 18 }}>
        <span className="logo" style={{
          fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em',
          display: 'inline-flex', alignItems: 'center', gap: 9,
          background: 'linear-gradient(100deg, var(--brand), var(--brand-2))',
          WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
        }}>
          <Wallet size={24} style={{ color: 'var(--brand)' }} /> SplitMate
        </span>
        <p className="muted" style={{ marginTop: 6 }}>
          Track shared expenses. Import your messy spreadsheet. Approve every fix.
        </p>
      </div>
      <div className="card" style={{ boxShadow: 'var(--shadow-md)' }}>
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
        {mode === 'login' && (
          <div className="notice" style={{ marginBottom: 0, marginTop: 14 }}>
            <strong>Demo account:</strong> <span className="mono">aisha</span> /{' '}
            <span className="mono">password123</span> — comes with sample groups &
            data.{' '}
            <button
              type="button"
              className="ghost"
              style={{ padding: '2px 8px', fontSize: 13 }}
              disabled={busy}
              onClick={() => {
                setMode('login')
                setForm({ ...form, username: 'aisha', password: 'password123' })
              }}
            >
              Fill it in
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
