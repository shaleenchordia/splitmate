// Thin fetch wrapper: token auth + JSON errors surfaced as exceptions.

const TOKEN_KEY = 'splitmate_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(status, body) {
    super(typeof body === 'string' ? body : body?.detail || JSON.stringify(body))
    this.status = status
    this.body = body
  }
}

export async function api(path, { method = 'GET', body, formData } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Token ${token}`
  if (body) headers['Content-Type'] = 'application/json'
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: formData || (body ? JSON.stringify(body) : undefined),
  })
  if (res.status === 204) return null
  let data = null
  try {
    data = await res.json()
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) throw new ApiError(res.status, data)
  return data
}

// Money is minor units (paise) everywhere in the API; format at the edge.
export function fmtMoney(minor, currency = 'INR') {
  const symbol = { INR: '₹', USD: '$' }[currency] || `${currency} `
  const sign = minor < 0 ? '−' : ''
  return `${sign}${symbol}${(Math.abs(minor) / 100).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}
