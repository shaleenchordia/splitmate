import { useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api, getToken, setToken } from './api.js'
import { Avatar, Logout, Moon, Sun, Wallet } from './components/icons.jsx'
import GroupPage from './pages/GroupPage.jsx'
import Groups from './pages/Groups.jsx'
import Login from './pages/Login.jsx'

function useTheme() {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || 'light')
  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    localStorage.setItem('splitmate_theme', next)
    setTheme(next)
  }
  return [theme, toggle]
}

export default function App() {
  const [user, setUser] = useState(undefined) // undefined = loading
  const [theme, toggleTheme] = useTheme()
  const navigate = useNavigate()

  useEffect(() => {
    if (!getToken()) {
      setUser(null)
      return
    }
    api('/auth/me/')
      .then(setUser)
      .catch(() => {
        setToken(null)
        setUser(null)
      })
  }, [])

  const logout = () => {
    setToken(null)
    setUser(null)
    navigate('/login')
  }

  if (user === undefined) return null

  return (
    <>
      {user && (
        <div className="topbar">
          <Link to="/" className="logo">
            <Wallet size={19} /> SplitMate
          </Link>
          <span className="muted">shared expenses, no magic numbers</span>
          <span className="spacer" />
          <button className="icon-btn ghost" onClick={toggleTheme} title="Toggle theme">
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <span className="row" style={{ gap: 8 }}>
            <Avatar name={user.first_name || user.username} size={28} />
            <span style={{ fontWeight: 550 }}>{user.first_name || user.username}</span>
          </span>
          <button className="ghost" onClick={logout}>
            <Logout size={15} /> Log out
          </button>
        </div>
      )}
      {!user && (
        <button
          className="icon-btn ghost"
          onClick={toggleTheme}
          title="Toggle theme"
          style={{ position: 'fixed', top: 14, right: 14, zIndex: 6 }}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      )}
      <Routes>
        <Route
          path="/login"
          element={user ? <Navigate to="/" /> : <Login onAuth={setUser} />}
        />
        <Route path="/" element={user ? <Groups /> : <Navigate to="/login" />} />
        <Route
          path="/groups/:groupId/*"
          element={user ? <GroupPage user={user} /> : <Navigate to="/login" />}
        />
      </Routes>
    </>
  )
}
