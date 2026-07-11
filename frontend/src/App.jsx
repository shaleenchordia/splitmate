import { useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api, getToken, setToken } from './api.js'
import GroupPage from './pages/GroupPage.jsx'
import Groups from './pages/Groups.jsx'
import Login from './pages/Login.jsx'

export default function App() {
  const [user, setUser] = useState(undefined) // undefined = loading
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
          <Link to="/" className="logo">SplitMate</Link>
          <span className="muted">shared expenses, no magic numbers</span>
          <span className="spacer" />
          <span>{user.first_name || user.username}</span>
          <button onClick={logout}>Log out</button>
        </div>
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
