import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Camera, Sparkle } from './icons.jsx'

// Natural-language / receipt-photo expense entry. The AI only produces a
// proposal — the prefilled ExpenseForm opens for the human to confirm.

const EXAMPLES = [
  'Dinner at Truffles 1200, Aisha paid, split with Rohan and Priya',
  'Uber $25 yesterday, Sam paid',
  'Groceries 900 — Aisha 60% and Rohan 40%',
  'Wifi bill 850',
]

export default function SmartAdd({ group, onProposal }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [ai, setAi] = useState(null) // {gemini, model}
  const [hint, setHint] = useState(0)
  const fileRef = useRef()

  useEffect(() => {
    api('/ai/status/').then(setAi).catch(() => setAi({ gemini: false }))
  }, [])
  useEffect(() => {
    const t = setInterval(() => setHint((h) => (h + 1) % EXAMPLES.length), 5000)
    return () => clearInterval(t)
  }, [])

  const parse = async (e) => {
    e.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    try {
      const res = await api(`/groups/${group.id}/ai/parse-expense/`, {
        method: 'POST',
        body: { text },
      })
      setText('')
      onProposal(res)
    } catch (err) {
      setError(err.body?.detail || err.message)
    } finally {
      setBusy(false)
    }
  }

  const scan = async (file) => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('image', file)
      const res = await api(`/groups/${group.id}/ai/scan-receipt/`, {
        method: 'POST',
        formData: fd,
      })
      onProposal(res)
    } catch (err) {
      setError(err.body?.detail || err.message)
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="ai-panel">
      <h3>
        <Sparkle size={16} /> Smart add
        {ai && (
          <span className="ai-source" style={{ fontWeight: 400 }}>
            {ai.gemini ? `· ${ai.model}` : '· offline parser (add GEMINI_API_KEY for full power)'}
          </span>
        )}
      </h3>
      <form className="smart-add-input" onSubmit={parse}>
        <input
          placeholder={`Try: “${EXAMPLES[hint]}”`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
        />
        <button className="ai" type="submit" disabled={busy || !text.trim()}>
          <Sparkle size={14} /> {busy ? 'Thinking…' : 'Parse'}
        </button>
        <button
          type="button"
          className="icon-btn"
          title={
            ai?.gemini
              ? 'Scan a receipt photo'
              : 'Receipt scanning needs the Gemini API key'
          }
          disabled={busy || !ai?.gemini}
          onClick={() => fileRef.current?.click()}
        >
          <Camera size={16} />
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(e) => scan(e.target.files[0])}
        />
      </form>
      <p className="muted" style={{ margin: '8px 0 0' }}>
        Describe the expense in plain words{ai?.gemini ? ' or snap the receipt' : ''} — you
        review the parsed form before anything is saved.
      </p>
      {error && <div className="error-box">{error}</div>}
    </div>
  )
}
