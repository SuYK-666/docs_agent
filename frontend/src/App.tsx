import GlobalHeader from '@/components/layout/GlobalHeader'
import LandingPage from '@/pages/Landing'
import DashboardPage from '@/pages/Dashboard'
import { useJobMonitor } from '@/hooks/useJobMonitor'
import TerminalPage from '@/pages/Terminal'
import WorkspacePage from '@/pages/Workspace'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

function App() {
  const { startJob, submitApproval, setDrafts, setRecipientEmails, statusData } = useJobMonitor()
  const location = useLocation()
  const showGlobalHeader = location.pathname !== '/'

  return (
    <>
      <GlobalHeader />
      <div className={showGlobalHeader ? 'min-h-screen bg-[#050914]' : ''}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/dashboard" element={<DashboardPage startJob={startJob} statusData={statusData} />} />
          <Route path="/terminal" element={<TerminalPage statusData={statusData} />} />
          <Route
            path="/workspace"
            element={
              <WorkspacePage
                statusData={statusData}
                submitApproval={submitApproval}
                setDrafts={setDrafts}
                setRecipientEmails={setRecipientEmails}
              />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </>
  )
}

export default App
