import React, { useState, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Download, Wifi, ArrowLeft, Zap, Sparkles } from 'lucide-react';
import api from '../lib/api';
import { useToastStore } from '../store';
import { Waveform, Spinner } from '../components/UI';
import { AudioRecorder } from '../components/AudioRecorder';

const LANGUAGES = ['en','es','fr','de','it','pt','zh','ja','ko','ar','hi','ru','tr','nl','pl','sv','cs'];
const EMOTIONS = [
  { emoji: '😊', label: 'happy' }, { emoji: '😢', label: 'sad' }, { emoji: '😠', label: 'angry' },
  { emoji: '😮', label: 'surprised' }, { emoji: '😌', label: 'calm' }, { emoji: '🤔', label: 'confused' },
  { emoji: '😤', label: 'frustrated' }, { emoji: '🎉', label: 'excited' }, { emoji: '😐', label: 'neutral' },
  { emoji: '😔', label: 'melancholic' }, { emoji: '😏', label: 'sarcastic' }, { emoji: '🥰', label: 'affectionate' },
  { emoji: '😎', label: 'confident' }, { emoji: '😴', label: 'sleepy' },
];

export default function VoiceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { addToast } = useToastStore();
  const [activeTab, setActiveTab] = useState(0);
  const [voice, setVoice] = useState<any>(null);
  const [samples, setSamples] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [uploading, setUploading] = useState(false);
  const [cloning, setCloning] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [ttsForm, setTtsForm] = useState({
    text: 'Hello! This is my cloned voice speaking with natural rhythm and emotion.',
    language: 'en', emotion: 'neutral', speed: 1.0, pitch: 0, format: 'mp3',
  });
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    api.get(`/api/voices/${id}`)
      .then((r) => setVoice(r.data))
      .catch((err) => {
         addToast(err.response?.status === 404 ? 'Voice not found' : 'Failed to load voice', 'error');
         navigate('/voices');
      });
    api.get(`/api/voices/${id}/samples`).then((r) => setSamples(r.data || [])).catch(() => {});
    api.get(`/api/voices/${id}/generations`).then((r) => setHistory(r.data || [])).catch(() => {});
  }, [id, navigate, addToast]);

  const uploadSample = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await submitAudio(file);
  };

  const handleRecordingComplete = async (audioBlob: Blob) => {
    // Convert Blob to File
    const file = new File([audioBlob], `recording-${Date.now()}.webm`, { type: 'audio/webm' });
    await submitAudio(file);
  };

  const submitAudio = async (file: File) => {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('audio_file', file);
      const r = await api.post(`/api/voices/${id}/samples`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setSamples((s) => [...s, r.data]);
      addToast('Sample uploaded successfully!', 'success');
    } catch (err: any) {
      addToast(err.response?.data?.detail || err.message || 'Sample upload failed', 'error');
    } finally {
      setUploading(false);
    }
  };

  const startCloning = async () => {
    setCloning(true);
    try {
      await api.post(`/api/voices/${id}/clone`);
      addToast('Cloning dispatched to Celery worker! Check back soon.', 'success');
      setVoice((v: any) => ({ ...v, status: 'processing' }));
    } catch (err: any) {
      addToast(err.message || 'Failed to dispatch cloning job', 'error');
    } finally {
      setCloning(false);
    }
  };

  const generateTTS = async () => {
    setGenerating(true);
    try {
      const r = await api.post('/api/tts/generate', { voice_profile_id: id, ...ttsForm });
      const jobId = r.data.job_id;
      for (let i = 0; i < 30; i++) {
        await new Promise((res) => setTimeout(res, 1500));
        const job = await api.get(`/api/tts/jobs/${jobId}`);
        if (job.data.status === 'completed') {
          addToast('Audio generated successfully!', 'success');
          // Refresh history ideally
          api.get(`/api/voices/${id}/generations`).then((hr) => setHistory(hr.data || [])).catch(() => {});
          break;
        }
        if (job.data.status === 'failed') { addToast('Generation failed by worker', 'error'); break; }
      }
    } catch (err: any) {
       addToast(err.message || 'Failed to request generation', 'error');
    } finally {
      setGenerating(false);
    }
  };

  const tabs = ['Samples', 'Synthesize', 'Live Stream'];

  return (
    <div className="main">
      <button className="btn btn-secondary btn-sm mb-4" onClick={() => navigate('/voices')} title="Go back">
        <ArrowLeft size={14} /> Back to Library
      </button>

      {voice && (
        <div className="card mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="page-title">{voice.name}</h1>
              <div className="flex gap-2 mt-2">
                <span className={`badge badge-${voice.status === 'ready' ? 'green' : voice.status === 'processing' ? 'amber' : 'gray'}`}>
                  <span className={`status-dot ${voice.status}`} /> {voice.status}
                </span>
                {voice.language && <span className="badge badge-gray">{voice.language.toUpperCase()}</span>}
                {voice.quality_score && <span className="badge badge-violet">⭐ {voice.quality_score}/100</span>}
              </div>
            </div>
            {voice.status === 'processing' ? <Spinner /> : <Waveform bars={10} />}
          </div>
        </div>
      )}

      <div className="tabs">
        {tabs.map((t, i) => (
          <button key={t} className={`tab-btn${activeTab === i ? ' active' : ''}`} onClick={() => setActiveTab(i)} title={t}>{t}</button>
        ))}
      </div>

      {activeTab === 0 && (
        <div>
          <div className="grid-2 gap-4 mb-4">
            <AudioRecorder onRecordingComplete={handleRecordingComplete} maxDurationSeconds={120} />
            <div className="dropzone h-full min-h-[200px]" onClick={() => fileRef.current?.click()}>
              <div className="dropzone-icon">📁</div>
              <p><strong>Drop audio files here</strong> or click to browse</p>
              <p className="font-11 text-muted mt-8">MP3, WAV, OGG · Min 6 seconds recommended</p>
              <label htmlFor="sample-upload" className="sr-only">Upload Sample Audio</label>
              <input id="sample-upload" ref={fileRef} type="file" accept="audio/*" className="hidden" onChange={uploadSample} />
            </div>
          </div>
          {uploading && <div className="text-center mb-4"><Spinner /> Uploading & Analyzing...</div>}
          
          {samples.length > 0 ? (
            <div className="card mt-4">
              <div className="card-title">Uploaded Samples ({samples.length})</div>
              {samples.map((s: any, i: number) => (
                <div key={i} className="flex items-center justify-between border-b py-10">
                  <span className="text-sm font-mono">{s.filename || `sample_${i + 1}.wav`}</span>
                  <span className="badge badge-green">✓ {s.duration ? `${s.duration.toFixed(1)}s` : 'Uploaded'}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="card text-center p-40 mt-4 opacity-80 text-muted border-dashed border">
               To synthesize speech with this voice, you must first upload at least one clear, isolated voice sample (6-15 seconds ideal).
            </div>
          )}
          <div className="flex gap-3 mt-4">
            <button className="btn btn-primary" onClick={startCloning} disabled={cloning || samples.length === 0} title="Start Cloning">
              {cloning ? <><Spinner /> Queueing...</> : <><Zap size={14} /> Start Architecture Pipeline</>}
            </button>
            <button className="btn btn-secondary" onClick={startCloning} title="Fine-Tune Voice" disabled={samples.length === 0}>
              <Sparkles size={14} /> Fine-Tune Epochs
            </button>
          </div>
        </div>
      )}

      {activeTab === 1 && (
        <div>
          <div className="form-group">
            <label className="form-label" htmlFor="tts-text">Text ({ttsForm.text.length} chars)</label>
            <textarea id="tts-text" className="form-textarea" placeholder="Enter text to synthesize"
              value={ttsForm.text} onChange={(e) => setTtsForm(f => ({ ...f, text: e.target.value }))} />
          </div>
          <div className="grid-2 mb-4">
            <div className="form-group">
              <label className="form-label" htmlFor="tts-lang">Language</label>
              <select id="tts-lang" className="form-select" value={ttsForm.language} title="Select Language" onChange={(e) => setTtsForm(f => ({ ...f, language: e.target.value }))}>
                {LANGUAGES.map(l => <option key={l} value={l}>{l.toUpperCase()}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Output Format</label>
              <div className="flex gap-2">
                {['mp3','wav','ogg','flac'].map((fmt) => (
                  <label key={fmt} className="flex items-center gap-6 cursor-pointer font-13">
                    <input type="radio" name="format" value={fmt} checked={ttsForm.format === fmt}
                      onChange={() => setTtsForm(f => ({ ...f, format: fmt }))} />
                    {fmt.toUpperCase()}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Emotion Injection</label>
            <div className="emotion-grid">
              {EMOTIONS.map((em) => (
                <button key={em.label} className={`emotion-pill${ttsForm.emotion === em.label ? ' selected' : ''}`}
                  onClick={() => setTtsForm(f => ({ ...f, emotion: em.label }))} title={`Select ${em.label} emotion`}>
                  {em.emoji} {em.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid-2 mb-4">
            <div className="form-group">
              <label className="form-label" htmlFor="tts-speed">Speed: {ttsForm.speed}×</label>
              <div className="slider-wrap">
                <span className="text-xs text-muted">0.5×</span>
                <input id="tts-speed" type="range" className="slider" min={0.5} max={2} step={0.05}
                  value={ttsForm.speed} onChange={(e) => setTtsForm(f => ({ ...f, speed: parseFloat(e.target.value) }))} />
                <span className="text-xs text-muted">2×</span>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="tts-pitch">Pitch shift: {ttsForm.pitch > 0 ? '+' : ''}{ttsForm.pitch} st</label>
              <div className="slider-wrap">
                <span className="text-xs text-muted">-12</span>
                <input id="tts-pitch" type="range" className="slider" min={-12} max={12} step={1}
                  value={ttsForm.pitch} onChange={(e) => setTtsForm(f => ({ ...f, pitch: parseInt(e.target.value) }))} />
                <span className="text-xs text-muted">+12</span>
              </div>
            </div>
          </div>

          <button id="generate-btn" className="btn btn-primary btn-lg" onClick={generateTTS} disabled={generating || voice?.status !== 'ready'} title="Generate Speech">
             {voice?.status !== 'ready' ? 'Voice Profile not ready' : (generating ? <><Spinner /> Worker executing...</> : <><Zap size={16} /> Synthesize Speech</>)}
          </button>

          {generating && (
            <div className="card mt-4 text-center">
              <Waveform bars={12} color="var(--violet)" />
              <div className="text-sm text-muted mt-3">Synthesizing audio on Celery cluster...</div>
            </div>
          )}

          <div className="mt-8 border-t border-[var(--glass-border)] pt-8">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold font-18">Generation History</h3>
              <span className="badge badge-gray">{history.length} Output{history.length !== 1 ? 's' : ''}</span>
            </div>
            {history.length > 0 ? (
              <div className="flex flex-col gap-3">
                {history.map((h, i) => (
                  <div key={i} className="card p-16 flex items-center justify-between gap-4">
                    <div className="flex-1">
                       <p className="text-sm font-bold mb-1 line-clamp-1">{h.text}</p>
                       <p className="text-xs text-muted">
                         {new Date(h.created_at).toLocaleString()} • {h.duration ? `${h.duration.toFixed(1)}s` : 'Unknown duration'}
                       </p>
                    </div>
                    {h.url && (
                      <div className="flex items-center gap-3">
                         <audio controls src={h.url} className="h-32 w-200 hide-audio-bg" />
                         <a href={h.url} download className="btn btn-secondary btn-sm rounded-full w-32 h-32 p-0 flex items-center justify-center text-violet hover:bg-violet hover:text-white" title="Download">
                           <Download size={14} />
                         </a>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="card text-center p-32 opacity-80 border-dashed border text-muted">
                 No synthesized audio yet. Type some text above and generate your first clip!
              </div>
            )}
          </div>
        </div>
      )}


      {activeTab === 2 && (
        <div className="card">
          <div className="card-title">Real-Time WebSocket Streaming API</div>
          <p className="text-sm text-muted mb-4">Connect to the WebSocket TTS endpoint with your authentication token for extreme low-latency continuous audio ingestion via chunked streams.</p>
          <div className="flex items-center gap-3">
            <Wifi size={20} className="text-violet" />
            <code className="font-mono text-xs text-dim bg-deep p-16-20 radius-sm flex-1">
              const ws = new WebSocket(`ws://api/v1/tts/stream?token=...&voice_id=${id}`);
            </code>
          </div>
          <button className="btn btn-secondary mt-16" title="Read Docs">
            View WebRTC Documentation
          </button>
        </div>
      )}
    </div>
  );
}
