import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './components/RequireAuth'
import { HomePage } from './pages/HomePage'
import { LiveSessionPage } from './pages/LiveSessionPage'
import { LoginPage } from './pages/LoginPage'
import { SessionDetailPage } from './pages/SessionDetailPage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/sessions/:id/live" element={<LiveSessionPage />} />
        <Route path="/sessions/:id" element={<SessionDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
