import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from './store';
import { Sidebar } from './components/Sidebar';
import { ToastContainer } from './components/UI';

import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import VoiceLibrary from './pages/VoiceLibrary';
import VoiceDetail from './pages/VoiceDetail';
import Studio from './pages/Studio';
import DeepfakeDetector from './pages/Detector';
import ApiKeys from './pages/ApiKeys';
import Usage from './pages/Usage';

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30000 } } });

function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore();
  const [isCollapsed, setIsCollapsed] = useState(false);

  if (!token) return <Navigate to="/" replace />;
  return (
    <div className="layout" style={{ '--sidebar-width': isCollapsed ? '72px' : '240px' } as React.CSSProperties}>
      <Sidebar isCollapsed={isCollapsed} toggle={() => setIsCollapsed(!isCollapsed)} />
      {children}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <ToastContainer />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/dashboard" element={<ProtectedLayout><Dashboard /></ProtectedLayout>} />
          <Route path="/studio" element={<ProtectedLayout><Studio /></ProtectedLayout>} />
          <Route path="/voices" element={<ProtectedLayout><VoiceLibrary /></ProtectedLayout>} />
          <Route path="/voices/:id" element={<ProtectedLayout><VoiceDetail /></ProtectedLayout>} />
          <Route path="/detect" element={<ProtectedLayout><DeepfakeDetector /></ProtectedLayout>} />
          <Route path="/settings/api-keys" element={<ProtectedLayout><ApiKeys /></ProtectedLayout>} />
          <Route path="/settings/usage" element={<ProtectedLayout><Usage /></ProtectedLayout>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
