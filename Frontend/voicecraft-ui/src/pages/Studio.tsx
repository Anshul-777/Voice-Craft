import React, { useState, useEffect, useRef } from 'react';
import { Play, Download, Zap, UploadCloud } from 'lucide-react';
import api from '../lib/api';
import { useToastStore } from '../store';
import { Waveform, Spinner } from '../components/UI';
import { AudioRecorder } from '../components/AudioRecorder';

const LANGUAGES = ['en','es','fr','de','it','pt','zh','ja','ko','ar','hi','ru','tr','nl','pl','sv','cs'];
const EMOTIONS = [
  { emoji: '😊', label: 'happy' }, { emoji: '😢', label: 'sad' }, { emoji: '😠', label: 'angry' },
  { emoji: '😮', label: 'surprised' }, { emoji: '😌', label: 'calm' }, { emoji: '🤔', label: 'confused' },
  { emoji: '😐', label: 'neutral' }, { emoji: '😎', label: 'confident' },
];

export default function Studio() {
  const [voices, setVoices] = useState<any[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<string>('');
  const [tab, setTab] = useState(0); // 0: TTS, 1: S2S
  const { addToast } = useToastStore();
  
  const [ttsForm, setTtsForm] = useState({
    text: 'Hello! This is my cloned voice speaking. I was generated entirely from a text prompt using the Studio pipeline.',
    language: 'en', emotion: 'neutral', speed: 1.0, pitch: 0, format: 'wav',
  });
  
  const [generating, setGenerating] = useState(false);
  const [history, setHistory] = useState<any[]>([]);

  // S2S State
  const s2sFileRef = useRef<HTMLInputElement>(null);
  const [sourceAudio, setSourceAudio] = useState<File | null>(null);

  const systemVoices = [
    { id: 'sys-rachel', name: 'Rachel - Conversational', status: 'ready' },
    { id: 'sys-drew', name: 'Drew - Newscast', status: 'ready' },
    { id: 'sys-clyde', name: 'Clyde - Narration', status: 'ready' },
  ];

  useEffect(() => {
    api.get('/api/voices').then((r) => {
      const allVoices = [...systemVoices, ...(r.data || [])].filter(v => v.status === 'ready');
      setVoices(allVoices);
      if (allVoices.length > 0) setSelectedVoice(allVoices[0].id);
    }).catch(() => {
      setVoices(systemVoices);
      setSelectedVoice('sys-rachel');
    });
  }, []);

  const fetchHistory = () => {
     api.get('/api/tts/jobs?page_size=5').then((r) => setHistory(r.data || [])).catch(() => {});
  };

  useEffect(() => {
     fetchHistory();
  }, []);

  const generateTTS = async () => {
    if (!selectedVoice) return addToast('Please select a targeted voice profile.', 'error');
    setGenerating(true);
    try {
      const r = await api.post('/api/tts/generate', { voice_profile_id: selectedVoice, ...ttsForm });
      const jobId = r.data.job_id;
      for (let i = 0; i < 30; i++) {
        await new Promise((res) => setTimeout(res, 1500));
        const job = await api.get(`/api/tts/jobs/${jobId}`);
        if (job.data.status === 'completed') {
          addToast('Audio generated successfully!', 'success');
          fetchHistory();
          break;
        }
        if (job.data.status === 'failed') { addToast('Generation failed by worker', 'error'); break; }
      }
    } catch (err: any) {
       addToast(err.response?.data?.detail || err.message || 'Failed to request generation', 'error');
    } finally {
      setGenerating(false);
    }
  };

  const generateS2S = async () => {
    if (!selectedVoice) return addToast('Please select a targeted voice profile.', 'error');
    if (!sourceAudio) return addToast('Please upload a source audio file first.', 'error');
    
    setGenerating(true);
    try {
      const fd = new FormData();
      fd.append('source_audio', sourceAudio);
      fd.append('voice_profile_id', selectedVoice);
      fd.append('emotion', ttsForm.emotion);

      // This assumes the backend has the /api/s2s/generate route ready.
      const r = await api.post('/api/s2s/generate', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      addToast('Speech-to-Speech deepfake generation dispatched!', 'success');
      
      const jobId = r.data.job_id;
      for (let i = 0; i < 40; i++) {
        await new Promise((res) => setTimeout(res, 1500));
        const job = await api.get(`/api/tts/jobs/${jobId}`); // S2S outputs to the same job bucket
        if (job.data.status === 'completed') {
          addToast('S2S Audio generated successfully!', 'success');
          fetchHistory();
          break;
        }
        if (job.data.status === 'failed') { addToast('S2S Generation failed', 'error'); break; }
      }
    } catch (err: any) {
       addToast("Speech-to-Speech Deepfake Generation error. Ensure backend has the module running.", 'error');
    } finally {
      setGenerating(false);
    }
  };

  const handleS2SRecordingComplete = (audioBlob: Blob) => {
    const file = new File([audioBlob], `s2s-live-${Date.now()}.webm`, { type: 'audio/webm' });
    setSourceAudio(file);
    addToast('Live audio captured. Ready for S2S synthesis.', 'success');
  };

  const vName = voices.find(v => v.id === selectedVoice)?.name || '...';

  return (
    <div className="main flex flex-col h-[calc(100vh-64px)]" style={{ overflow: 'hidden' }}>
      {/* Top Banner */}
      <div className="bg-violet-soft border border-violet/20 p-24 px-32 radius-t-md">
        <h1 className="page-title flex items-center gap-2"><Play size={24} /> Generation Studio</h1>
        <p className="page-subtitle mb-16">The centralized hub for synthesizing deepfake audio using Voice Cloning AI.</p>
        
        <div className="form-group mb-0 max-w-400">
           <label className="form-label">Target Voice Identity</label>
           <select className="form-select bg-deep border-violet/30 focus:border-violet" value={selectedVoice} onChange={(e) => setSelectedVoice(e.target.value)}>
             {voices.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
           </select>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden border-x border-b border-violet/20 radius-b-md">
         {/* Left Controls */}
         <div className="w-1/2 border-r border-[var(--glass-border)] p-32 overflow-y-auto bg-[var(--bg-card)]">
            <div className="tabs mb-8">
              <button className={`tab-btn${tab === 0 ? ' active' : ''}`} onClick={() => setTab(0)}>📝 Text-to-Speech</button>
              <button className={`tab-btn${tab === 1 ? ' active' : ''}`} onClick={() => setTab(1)}>🎙️ Speech-to-Speech</button>
            </div>

            {tab === 0 ? (
               <div className="animate-fade-in">
                  <div className="form-group">
                    <label className="form-label" htmlFor="tts-text">Script ({ttsForm.text.length}/5000 chars)</label>
                    <textarea id="tts-text" className="form-textarea" style={{ height: '200px' }} placeholder="Enter the text prompt you want to synthesize..."
                      value={ttsForm.text} onChange={(e) => setTtsForm(f => ({ ...f, text: e.target.value }))} />
                  </div>

                  <div className="grid-2 mb-4">
                    <div className="form-group">
                      <label className="form-label">Language</label>
                      <select className="form-select" value={ttsForm.language} onChange={(e) => setTtsForm(f => ({ ...f, language: e.target.value }))}>
                        {LANGUAGES.map(l => <option key={l} value={l}>{l.toUpperCase()}</option>)}
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Output Format</label>
                      <div className="flex gap-2">
                        {['mp3','wav','ogg'].map((fmt) => (
                          <label key={fmt} className="flex items-center gap-6 cursor-pointer font-13">
                            <input type="radio" value={fmt} checked={ttsForm.format === fmt} onChange={() => setTtsForm(f => ({ ...f, format: fmt }))} />
                            {fmt.toUpperCase()}
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Voice Delivery / Emotion</label>
                    <div className="emotion-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
                      {EMOTIONS.map((em) => (
                        <button key={em.label} className={`emotion-pill${ttsForm.emotion === em.label ? ' selected' : ''}`}
                          onClick={() => setTtsForm(f => ({ ...f, emotion: em.label }))} title={`Select ${em.label} emotion`}>
                          {em.emoji} {em.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <button className="btn btn-primary w-full btn-lg mt-8" onClick={generateTTS} disabled={generating}>
                     {generating ? <><Spinner /> Synthesizing Deepfake...</> : <><Zap size={16} /> Generate "{vName}"</>}
                  </button>
               </div>
            ) : (
               <div className="animate-fade-in">
                  <div className="grid-2 gap-4 mb-8">
                     <AudioRecorder onRecordingComplete={handleS2SRecordingComplete} maxDurationSeconds={180} />
                     <div className="card bg-deep border-dashed border p-32 text-center h-full flex flex-col items-center justify-center cursor-pointer hover:bg-violet-soft/20 transition-colors" onClick={() => s2sFileRef.current?.click()}>
                        {sourceAudio ? (
                           <div className="text-violet font-bold">
                             <UploadCloud size={32} className="m-auto mb-8" />
                             Source Loaded: <br/><span className="text-sm font-mono mt-2 inline-block">{sourceAudio.name}</span>
                           </div>
                        ) : (
                           <div className="opacity-80">
                              <UploadCloud size={32} className="m-auto mb-8" />
                              <p className="font-bold">Upload Source Audio</p>
                              <p className="text-sm text-muted mt-2">Extract speech, transcribe, and re-synthesize in <strong>{vName}'s</strong> exact voice.</p>
                           </div>
                        )}
                        <input ref={s2sFileRef} type="file" accept="audio/*" className="hidden" onChange={(e) => {
                          if (e.target.files?.[0]) {
                            setSourceAudio(e.target.files[0]);
                            addToast('Audio file loaded.', 'success');
                          }
                        }} />
                     </div>
                  </div>

                  {sourceAudio && (
                    <button className="btn btn-primary w-full btn-lg mt-8" onClick={generateS2S} disabled={generating}>
                       {generating ? <><Spinner /> Transcribing & Synthesizing...</> : <><Zap size={16} /> Run Speech-to-Speech Deepfake</>}
                    </button>
                  )}
               </div>
            )}
         </div>

         {/* Right History Stream */}
         <div className="w-1/2 p-32 bg-[var(--surface-color)] overflow-y-auto">
            <h3 className="font-bold font-18 mb-16 flex items-center justify-between">
               Generation History
               <span className="badge badge-violet">{history.length}</span>
            </h3>

            {generating && (
              <div className="card p-24 mb-16 text-center border-violet/30 bg-violet-soft">
                <Waveform bars={16} color="var(--violet)" />
                <p className="text-sm mt-8 text-violet font-bold animate-pulse">Running Neural Synthesis Models...</p>
              </div>
            )}

            {history.length === 0 && !generating ? (
              <div className="text-center opacity-70 p-48 text-muted">
                 No outputs yet! 
              </div>
            ) : (
               <div className="flex flex-col gap-12">
                 {history.map((h, i) => (
                   <div key={i} className="card p-16">
                     <p className="text-sm font-bold mb-8 opacity-90">"{h.text}"</p>
                     
                     {h.status === 'completed' && h.download_url ? (
                        <div className="flex items-center justify-between gap-8 mt-12 pt-12 border-t border-[var(--glass-border)]">
                           <audio controls src={h.download_url} className="h-32 flex-1 hide-audio-bg max-w-300" />
                           <a href={h.download_url} download className="btn btn-secondary btn-sm" title="Download Audio">
                             <Download size={14} /> Download
                           </a>
                        </div>
                     ) : h.status === 'failed' ? (
                       <span className="badge badge-red mt-8">Generation Failed</span>
                     ) : (
                       <span className="badge badge-amber mt-8">Processing...</span>
                     )}
                   </div>
                 ))}
               </div>
            )}
         </div>
      </div>
    </div>
  );
}
