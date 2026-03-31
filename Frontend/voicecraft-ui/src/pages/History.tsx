import React, { useState, useEffect } from 'react';
import { History as HistoryIcon, Play, AlertCircle, CheckCircle2, Clock } from 'lucide-react';
import api from '../lib/api';
import { useToastStore } from '../store';
import { Spinner } from '../components/UI';

interface Job {
  job_id: string;
  status: string;
  created_at: string;
  duration_seconds: number | null;
  download_url: string | null;
}

export default function History() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const { addToast } = useToastStore();

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const r = await api.get('/api/tts/jobs?page_size=50');
      setJobs(r.data || []);
    } catch (err) {
      addToast('Failed to load history', 'error');
    } finally {
      setLoading(false);
    }
  };

  const StatusIcon = ({ status }: { status: string }) => {
    if (status === 'completed') return <CheckCircle2 size={16} className="text-[var(--green)]" />;
    if (status === 'failed') return <AlertCircle size={16} className="text-[var(--red)]" />;
    return <Clock size={16} className="text-[var(--amber)]" />;
  };

  return (
    <div className="main">
      <div className="page-header">
        <h1 className="page-title flex items-center gap-2"><HistoryIcon size={24} /> Generation Log</h1>
        <p className="page-subtitle">Track and download all your past Deepfake Synths and TTS Voice Overs.</p>
      </div>

      <div className="card">
        {loading ? (
          <div className="flex justify-center p-32"><Spinner /></div>
        ) : jobs.length === 0 ? (
          <div className="text-center p-32 text-[var(--text-muted)] opacity-80">
            <HistoryIcon size={48} className="mx-auto mb-16 opacity-50" />
            <h3 className="font-bold text-lg mb-2">No Generation History</h3>
            <p>Go to the Studio to generate your first AI voice clip.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-[var(--glass-border)] text-sm text-[var(--text-muted)]">
                  <th className="pb-4 font-normal">Date</th>
                  <th className="pb-4 font-normal">Job ID</th>
                  <th className="pb-4 font-normal">Status</th>
                  <th className="pb-4 font-normal">Duration</th>
                  <th className="pb-4 font-normal">Audio</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.job_id} className="border-b border-[var(--glass-border)] border-opacity-50 hover-bg-elevated transition-colors">
                    <td className="py-4 text-sm whitespace-nowrap">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                    <td className="py-4 font-mono text-xs opacity-70">
                      ...{job.job_id.slice(-8)}
                    </td>
                    <td className="py-4">
                      <div className="flex items-center gap-2 text-sm capitalize">
                        <StatusIcon status={job.status} />
                        {job.status}
                      </div>
                    </td>
                    <td className="py-4 text-sm font-mono text-[var(--text-muted)]">
                      {job.duration_seconds ? `${job.duration_seconds.toFixed(1)}s` : '--'}
                    </td>
                    <td className="py-4">
                      {job.download_url ? (
                        <div className="flex items-center gap-3">
                          <audio src={job.download_url} controls className="h-8 w-48 accent-[var(--violet)]" />
                          <a href={job.download_url} download className="text-[var(--violet)] hover:text-violet-400 transition-colors" title="Download Audio">
                            <Play size={16} />
                          </a>
                        </div>
                      ) : (
                        <span className="text-sm text-[var(--text-muted)] italic">Not available</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
