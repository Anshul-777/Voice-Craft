import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic2, Shield, Volume2, AlertTriangle, Plus, LayoutDashboard } from 'lucide-react';
import { CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart, XAxis, YAxis } from 'recharts';
import api from '../lib/api';
import { useAuthStore } from '../store';

export default function Dashboard() {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const [stats, setStats] = useState({ voices: 0, ttsChars: 0, detectJobs: 0, deepfakesCaught: 0, ttsLimit: 10000 });
  const [usage, setUsage] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);

  useEffect(() => {
    // Attempt real data fetch
    api.get('/api/voices').then((r) => setStats((s) => ({ ...s, voices: r.data?.length || 0 }))).catch(() => {});
    api.get('/api/stats/dashboard').then((r) => {
      if (r.data) {
        setStats(s => ({ ...s, ...r.data.summary }));
        setUsage(r.data.usage || []);
        setJobs(r.data.jobs || []);
      }
    }).catch(() => {});
  }, []);

  const pct = (stats.ttsChars / stats.ttsLimit) * 100;

  return (
    <div className="main">
      <div className="page-header">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="page-title">Dashboard</h1>
            <p className="page-subtitle">Welcome back, <span className="text-violet">{user?.username}</span></p>
          </div>
          <button className="btn btn-primary" onClick={() => navigate('/voices')} title="New Voice Profile">
            <Plus size={16} /> New Voice
          </button>
        </div>
      </div>

      <div className="stats-grid">
        {[
          { icon: Mic2, label: 'Voice Profiles', value: stats.voices, colorClass: 'text-violet', bgClass: 'bg-violet-soft', delta: '' },
          { icon: Volume2, label: 'TTS Chars Used', value: stats.ttsChars.toLocaleString(), colorClass: 'text-green', bgClass: 'bg-green-soft', delta: `${pct.toFixed(0)}% of limit` },
          { icon: Shield, label: 'Detect Jobs', value: stats.detectJobs, colorClass: 'text-amber', bgClass: 'bg-amber-soft', delta: 'Total runs' },
          { icon: AlertTriangle, label: 'Deepfakes Caught', value: stats.deepfakesCaught, colorClass: 'text-red', bgClass: 'bg-red-soft', delta: `${stats.detectJobs > 0 ? ((stats.deepfakesCaught / stats.detectJobs) * 100).toFixed(0) : 0}% flagged` },
        ].map((s) => (
          <div key={s.label} className="stat-card">
            <div className={`stat-icon ${s.bgClass}`}>
              <s.icon size={20} className={s.colorClass} />
            </div>
            <div className={`stat-value ${s.colorClass}`}>{s.value}</div>
            <div className="stat-label">{s.label}</div>
            {s.delta && <div className="stat-delta text-muted">{s.delta}</div>}
          </div>
        ))}
      </div>

      <div className="card mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="card-title">TTS Characters This Month</span>
          <span className="text-sm text-muted">{stats.ttsChars.toLocaleString()} / {stats.ttsLimit.toLocaleString()}</span>
        </div>
        <div className="progress-wrap">
          <div className="progress-fill green" style={{ width: `${pct}%` } as React.CSSProperties} />
        </div>
        <div className="text-xs text-muted mt-2">{(stats.ttsLimit - stats.ttsChars).toLocaleString()} characters remaining</div>
      </div>

      <div className="grid-2 mb-6">
        <div className="card">
          <div className="card-title">TTS Usage — Last 30 Days</div>
          {usage.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={usage} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#7C3AED" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#7C3AED" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#6B7280' }} />
                <YAxis tick={{ fontSize: 10, fill: '#6B7280' }} />
                <Tooltip contentStyle={{ background: '#111827', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 8, fontSize: 12 }} />
                <Area type="monotone" dataKey="chars" stroke="#7C3AED" strokeWidth={2} fill="url(#cg)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
             <div className="flex flex-col items-center justify-center p-40 text-muted opacity-80">
                <LayoutDashboard size={32} className="mb-12" />
                <div className="text-sm">No usage data to display yet</div>
             </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">Detection Jobs — Last 30 Days</div>
          {usage.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={usage} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="cg2" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#EF4444" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#EF4444" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#6B7280' }} />
                <YAxis tick={{ fontSize: 10, fill: '#6B7280' }} />
                <Tooltip contentStyle={{ background: '#111827', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 8, fontSize: 12 }} />
                <Area type="monotone" dataKey="detections" stroke="#EF4444" strokeWidth={2} fill="url(#cg2)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
             <div className="flex flex-col items-center justify-center p-40 text-muted opacity-80">
                <Shield size={32} className="mb-12" />
                <div className="text-sm">No detection data available</div>
             </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Recent Jobs</div>
        {jobs.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Type</th><th>Voice / File</th><th>Status</th><th>Created</th><th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td><span className="badge badge-violet">{j.type}</span></td>
                    <td className="font-bold">{j.voice}</td>
                    <td>
                      <span className={`badge badge-${j.status === 'completed' ? 'green' : j.status === 'processing' ? 'amber' : 'red'}`}>
                        <span className={`status-dot ${j.status}`} />
                        {j.status}
                      </span>
                    </td>
                    <td className="text-muted text-sm">{new Date(j.created_at).toLocaleString()}</td>
                    <td className="font-mono text-sm">{j.duration || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center p-40 text-muted border border-dashed radius-sm mt-16">
             <div className="mb-8 opacity-80">No recent background jobs found.</div>
             <p className="font-13">Synthesize, clone, or analyze audio to populate the queue.</p>
          </div>
        )}
      </div>
    </div>
  );
}
