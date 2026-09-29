import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './components/RequireAuth'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'

// RecordPage is intentionally not routed here anymore - KAN-38 re-homes it
// onto a per-session live-view route (see lib/routes.ts's liveSessionPath).
// Fine mid-phase: Phase 4 merges to main as a whole, once KAN-38 lands.
function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<HomePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
