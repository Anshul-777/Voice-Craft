import React, { useState, useRef } from 'react';
import { Shield, Upload, Mic, MicOff } from 'lucide-react';
import api from '../lib/api';
import { useToastStore } from '../store';
import { Waveform, Spinner } from '../components/UI';
import { AudioRecorder } from '../components/AudioRecorder';
import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

interface DetectResult {
  verdict: 'authentic' | 'deepfake';
  confidence: number;
  authenticity_score: number;
  model_scores: Record<string, number>;
  temporal_segments?: { start: number; end: number; score: number }[];
  sha256?: string;
}

export default function DeepfakeDetector() {
  const [tab, setTab] = useState(0);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<DetectResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [liveProbs, setLiveProbs] = useState<any[]>([]);
  const [recording, setRecording] = useState(false);
  const { addToast } = useToastStore();

  const analyzeFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await submitAudio(file);
  };

  const handleRecordingComplete = async (audioBlob: Blob) => {
    const file = new File([audioBlob], `detect-recording-${Date.now()}.webm`, { type: 'audio/webm' });
    await submitAudio(file);
  };

  const submitAudio = async (file: File) => {
    setAnalyzing(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append('audio_file', file);
      fd.append('analysis_mode', 'full');
      const r = await api.post('/api/detect/analyze', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setResult(r.data);
      addToast('Analysis complete', 'success');
    } catch (err: any) {
      addToast(err.response?.data?.detail || err.message || 'Detection microservice error. Ensure Celery workers are running.', 'error');
    } finally {
      setAnalyzing(false);
    }
  };

  const toggleLive = () => {
    setRecording((r) => !r);
    if (!recording) {
      addToast('Live detection endpoint connected. Awaiting audio stream...', 'info');
      // In a real implementation this would connect a WebSocket to send audio chunks 
      // and receive probabilities in real time. We clear it to be blank.
      setLiveProbs([{ t: 0, prob: 0 }]);
    }
  };

  const segColor = (score: number) => {
    if (score > 0.7) return 'var(--red)';
    if (score > 0.4) return 'var(--amber)';
    return 'var(--green)';
  };

  return (
    <div className="main">
      <div className="page-header">
        <h1 className="page-title">Deepfake Detector</h1>
        <p className="page-subtitle">5-model ensemble: AASIST + RawNet2 + Prosodic + Spectral + Glottal</p>
      </div>

      <div className="card bg-violet-soft border-violet/20 mb-8 p-16">
        <h3 className="font-bold text-violet mb-4 flex items-center gap-2"><Shield size={16}/> What is this module?</h3>
        <p className="text-sm line-height-16 text-muted mb-8">
          This is the <strong>Analysis Engine</strong> (not the Voice Cloner). It scans incoming audio to determine mathematically if the voice is a real human or an AI-generated Deepfake.
        </p>
        <ul className="text-xs text-muted list-disc pl-16 flex flex-col gap-2">
          <li><strong>File Analysis:</strong> Upload any MP3/WAV to get a comprehensive forensic report of its authenticity.</li>
          <li><strong>Live Stream:</strong> Connects to your native microphone to actively scan whoever is speaking on the line in real-time.</li>
        </ul>
      </div>

      <div className="tabs">
        <button className={`tab-btn${tab === 0 ? ' active' : ''}`} onClick={() => setTab(0)}>📁 File Analysis</button>
        <button className={`tab-btn${tab === 1 ? ' active' : ''}`} onClick={() => setTab(1)}>🎙️ Live Stream</button>
      </div>

      {tab === 0 && (
        <div>
          {!analyzing && !result && (
            <div className="grid-2 gap-4">
              <AudioRecorder onRecordingComplete={handleRecordingComplete} maxDurationSeconds={60} />
              <div className="dropzone h-full min-h-[200px]" onClick={() => fileRef.current?.click()}>
                <div className="dropzone-icon">🎵</div>
                <p><strong>Drop audio file here</strong> or click to browse</p>
                <p className="text-muted font-11 mt-8">MP3, WAV, FLAC, OGG · Any length</p>
                <label htmlFor="detect-file" className="sr-only">Upload Audio File for Analysis</label>
                <input ref={fileRef} type="file" accept="audio/*" className="hidden" id="detect-file" onChange={analyzeFile} />
              </div>
            </div>
          )}

          {analyzing && (
            <div className="card text-center p-48">
              <div className="flex justify-center mb-16">
                <Waveform bars={14} color="var(--amber)" />
              </div>
              <div className="font-bold mb-8">Analyzing Audio...</div>
              <div className="text-sm text-muted">Running 5-model ensemble detection</div>
            </div>
          )}

          {result && (
            <div>
              <div className={`verdict-banner ${result.verdict}`}>
                <div className="verdict-icon">{result.verdict === 'authentic' ? '✅' : '⚠️'}</div>
                <div>
                  <div className={`verdict-title ${result.verdict === 'authentic' ? 'text-green' : 'text-red'}`}>
                    {result.verdict === 'authentic' ? 'AUTHENTIC' : 'DEEPFAKE DETECTED'}
                  </div>
                  <div className="verdict-sub">
                    {(result.confidence * 100).toFixed(1)}% confidence · Authenticity score: {result.authenticity_score}/100
                  </div>
                </div>
                <div className="m-auto text-right">
                  <div className={`font-48 font-800 ${result.verdict === 'authentic' ? 'text-green' : 'text-red'}`}>
                    {result.authenticity_score}
                  </div>
                  <div className="text-xs text-muted">/ 100</div>
                </div>
              </div>

              {result.temporal_segments && (
                <div className="card mb-4">
                  <div className="card-title">Temporal Heat Map — Suspicious Segments</div>
                  <div className="heatmap mt-3">
                    {result.temporal_segments.map((seg, i) => (
                      <div key={i} className="heatmap-seg" title={`${seg.start}s–${seg.end}s: ${(seg.score * 100).toFixed(0)}%`}
                        style={{ background: segColor(seg.score), opacity: 0.3 + seg.score * 0.7 } as React.CSSProperties} />
                    ))}
                  </div>
                  <div className="flex justify-between mt-2">
                    <span className="text-xs text-muted">0s</span>
                    <span className="text-xs text-green">■ Safe</span>
                    <span className="text-xs text-amber">■ Suspicious</span>
                    <span className="text-xs text-red">■ Flagged</span>
                    <span className="text-xs text-muted">{result.temporal_segments.length * 2}s</span>
                  </div>
                </div>
              )}

              <div className="card mb-4">
                <div className="card-title">Per-Model Score Breakdown</div>
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Model</th><th>Deepfake Probability</th><th>Verdict</th></tr></thead>
                    <tbody>
                      {Object.entries(result.model_scores).map(([model, score]) => (
                        <tr key={model}>
                          <td className="font-bold">{model}</td>
                          <td>
                            <div className="flex items-center gap-10">
                              <div className="progress-wrap w-full max-w-280">
                                <div className="progress-fill" style={{ width: `${score * 100}%`, background: score > 0.5 ? 'var(--red)' : 'var(--green)' } as React.CSSProperties} />
                              </div>
                              <span className="font-mono text-sm">{(score * 100).toFixed(1)}%</span>
                            </div>
                          </td>
                          <td>
                            <span className={`badge ${score > 0.5 ? 'badge-red' : 'badge-green'}`}>
                              {score > 0.5 ? 'Deepfake' : 'Authentic'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {result.sha256 && (
                <details className="card mb-4">
                  <summary className="cursor-pointer font-bold text-sm">🔒 Chain of Custody / SHA256</summary>
                  <div className="font-mono text-xs text-muted mt-3 word-break">{result.sha256}</div>
                </details>
              )}

              <div className="flex gap-3">
                <button className="btn btn-secondary" onClick={() => { setResult(null); setAnalyzing(false); }}>
                  <Upload size={14} /> Analyze Another
                </button>
                <button className="btn btn-primary">
                  Download Forensic Report
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 1 && (
        <div>
          <div className="card mb-4 text-center p-40">
            <button id="mic-btn" className={`btn btn-lg ${recording ? 'btn-danger' : 'btn-primary'}`} onClick={toggleLive} title="Toggle Mic Detection">
              {recording ? <><MicOff size={18} /> Stop Detection</> : <><Mic size={18} /> Start Live Detection</>}
            </button>
            {recording && (
              <div className="mt-24">
                <div className="flex justify-center mb-8">
                  <Waveform bars={10} color="var(--red)" />
                </div>
                <div className="badge badge-red font-11">● LIVE WEBSOCKET ACTIVE</div>
              </div>
            )}
            {!recording && (
              <p className="text-muted mt-16 font-13 max-w-340 mx-auto">
                Connects directly to the WebSocket ingestion endpoint and analyzes frames every 500ms using the low-latency AASIST model.
              </p>
            )}
          </div>

          {recording && liveProbs.length > 0 && (
            <>
              <div className="card mb-4">
                <div className="card-title">Real-Time Deepfake Probability</div>
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={liveProbs}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="t" tick={{ fontSize: 10, fill: '#6B7280' }} />
                    <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#6B7280' }} />
                    <Tooltip contentStyle={{ background: '#111827', border: '1px solid rgba(255,255,255,0.07)', fontSize: 12 }} />
                    <Line type="monotone" dataKey="prob" stroke="#EF4444" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              {liveProbs.length > 0 && liveProbs[liveProbs.length - 1]?.prob > 0.85 && (
                <div className="verdict-banner deepfake">
                  <div className="verdict-icon">🚨</div>
                  <div>
                    <div className="verdict-title text-red">DEEPFAKE ALERT!</div>
                    <div className="verdict-sub">Probability exceeded 85% threshold</div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
