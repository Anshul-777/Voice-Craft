import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Globe, User, Star } from 'lucide-react';
import api from '../lib/api';
import { useToastStore } from '../store';
import { Modal, Spinner } from '../components/UI';

interface Voice {
  id: string; name: string; description?: string;
  language?: string; gender?: string;
  quality_score?: number; status: string; generation_count?: number;
}

const statusColors: Record<string, string> = {
  ready: 'badge-green', processing: 'badge-amber', pending: 'badge-gray', failed: 'badge-red',
};

export default function VoiceLibrary() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ 
    mode: 'clone', 
    name: '', 
    description: '', 
    language: 'en',
    gender: 'male',
    age: 'middle-aged',
    accent: 'american',
    tone: 'conversational' 
  });
  const { addToast } = useToastStore();
  const navigate = useNavigate();

  const systemVoices: Voice[] = [
    { id: 'sys-rachel', name: 'Rachel - Conversational', description: 'Warm, engaging, and professional. Perfect for casual conversations and narration.', language: 'en', gender: 'Female', status: 'ready', generation_count: 1420, quality_score: 98 },
    { id: 'sys-drew', name: 'Drew - Newscast', description: 'Authoritative, clear, and confident. Best suited for news, announcements, and corporate videos.', language: 'en', gender: 'Male', status: 'ready', generation_count: 853, quality_score: 95 },
    { id: 'sys-clyde', name: 'Clyde - Narration', description: 'Deep, resonant, and cinematic. Excellent for storytelling and documentary narratives.', language: 'en', gender: 'Male', status: 'ready', generation_count: 2105, quality_score: 99 },
  ];

  useEffect(() => {
    api.get('/api/voices').then((r) => setVoices([...systemVoices, ...(r.data || [])])).catch(() => {
      // Fallback to system voices if API fails
      setVoices(systemVoices);
    });
  }, []);

  const createVoice = async () => {
    if (!form.name) return;
    setLoading(true);
    try {
      const r = await api.post('/api/voices', form);
      setVoices((v) => [...v, r.data]);
      setShowModal(false);
      setForm({ 
        mode: 'clone', 
        name: '', 
        description: '', 
        language: 'en',
        gender: 'male',
        age: 'middle-aged',
        accent: 'american',
        tone: 'conversational' 
      });
      addToast('Voice profile created!', 'success');
    } catch (err: any) {
      addToast(err.message || 'Failed to create voice', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="main">
      <div className="page-header">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="page-title">Voice Library</h1>
            <p className="page-subtitle">{voices.length} voice profile{voices.length !== 1 ? 's' : ''}</p>
          </div>
          <button className="btn btn-primary" onClick={() => setShowModal(true)} title="Create Profile">
            <Plus size={16} /> New Voice
          </button>
        </div>
      </div>

      <div className="card bg-violet-soft border-violet/20 mb-8 p-16">
        <h3 className="font-bold text-violet mb-4 flex items-center gap-2"><User size={16}/> What is this module?</h3>
        <p className="text-sm line-height-16 text-muted mb-8">
          This is the <strong>Voice Cloning Engine</strong> (not the Deepfake Detector). Use this to create permanent "Voice Profiles" by uploading a 6-second sample. Once a profile is created, you click on it to synthesize custom text-to-speech audio using that exact voice.
        </p>
      </div>

      <div className="voice-grid">
        {voices.length <= 3 && ( // Only system voices exist
          <div className="card text-center p-48 w-full" style={{ gridColumn: '1 / -1' }}>
            <div className="flex justify-center mb-16 opacity-80 mt-16 text-violet"><Plus size={48} /></div>
            <h2 className="font-bold font-24 mb-8">No Custom Profiles Yet</h2>
            <p className="text-muted max-w-340 mx-auto mb-24 line-height-16">
              Create your first AI voice persona. You can clone any human voice with a simple 6-second audio reference, or just use the System Templates above!
            </p>
            <button className="btn btn-primary m-auto" onClick={() => setShowModal(true)}>
              <Plus size={16} /> Create First Clone
            </button>
          </div>
        )}
        {voices.map((v) => (
          <div key={v.id} className="voice-card hover-glow" onClick={() => {
            if (v.id.startsWith('sys-')) navigate('/studio'); // Redirect system templates to studio
            else navigate(`/voices/${v.id}`);
          }}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="avatar bg-violet text-white font-bold p-8 radius-md font-14">
                  {v.name.slice(0, 2).toUpperCase()}
                </div>
                <div className="voice-card-name font-bold font-18">{v.name}</div>
              </div>
              <span className={`badge ${statusColors[v.status] || 'badge-gray'}`}>
                <span className={`status-dot ${v.status}`} />
                {v.status}
              </span>
            </div>
            
            {v.description ? (
              <p className="text-sm text-muted mb-4 line-clamp-2" style={{ minHeight: '40px' }}>
                {v.description}
              </p>
            ) : (
              <p className="text-sm text-dim mb-4 italic" style={{ minHeight: '40px' }}>
                No description provided.
              </p>
            )}

            <div className="voice-card-meta border-t border-[var(--glass-border)] pt-4 mt-2">
              <div className="flex gap-2">
                {v.language && <span className="badge badge-gray"><Globe size={11} className="mr-1" /> {v.language.toUpperCase()}</span>}
                {v.gender && <span className="badge badge-gray"><User size={11} className="mr-1" /> {v.gender}</span>}
                {v.generation_count !== undefined && <span className="badge badge-violet">{v.generation_count} gens</span>}
              </div>
            </div>
            
            {v.quality_score !== undefined && v.quality_score > 0 && (
              <div className="quality-bar mt-4 bg-[var(--surface-color)] p-8 radius-sm flex items-center gap-3">
                <div className="progress-wrap flex-1 bg-[var(--background-color)]">
                  <div className="progress-fill bg-violet" style={{ width: `${v.quality_score}%` } as React.CSSProperties} />
                </div>
                <div className="quality-score font-12 text-violet font-bold">
                  <Star size={12} className="inline mr-1" />
                  {v.quality_score}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {showModal && (
        <Modal title="Create New Voice" onClose={() => setShowModal(false)}>
          <div className="tabs mb-6">
            <button className={`tab-btn${form.mode === 'clone' ? ' active' : ''}`} onClick={() => setForm(f => ({...f, mode: 'clone'}))}>
              🎙️ Voice Clone
            </button>
            <button className={`tab-btn${form.mode === 'design' ? ' active' : ''}`} onClick={() => setForm(f => ({...f, mode: 'design'}))}>
              ✨ Voice Design
            </button>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="voice-name">Voice Name *</label>
            <input id="voice-name" className="form-input" placeholder="e.g. My Custom Voice" value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} />
          </div>

          {form.mode === 'clone' ? (
            <>
              <div className="form-group">
                <label className="form-label" htmlFor="voice-desc">Description (Optional)</label>
                <input id="voice-desc" className="form-input" placeholder="Optional notes about this speaker..." value={form.description} onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="voice-lang">Primary Language</label>
                <select id="voice-lang" className="form-select" value={form.language} title="Select Language" onChange={(e) => setForm(f => ({ ...f, language: e.target.value }))}>
                  {['en','es','fr','de','it','pt','zh','ja','ko','ar','hi','ru','tr','nl','pl','sv','cs'].map(l => (
                    <option key={l} value={l}>{l.toUpperCase()}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-muted mb-4">You will upload or record the voice samples on the next screen.</p>
            </>
          ) : (
            <div className="animate-fade-in">
              <div className="form-group">
                <label className="form-label" htmlFor="voice-prompt">Voice Description</label>
                <textarea id="voice-prompt" className="form-textarea min-h-[80px]" placeholder="A middle-aged British man with a deep, authoritative newscaster tone..." value={form.description} onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))} />
              </div>

              <div className="grid-2 mb-4">
                <div className="form-group">
                  <label className="form-label">Gender</label>
                  <select className="form-select" title="Voice Gender" value={form.gender || 'male'} onChange={(e) => setForm(f => ({ ...f, gender: e.target.value }))}>
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                    <option value="non-binary">Non-binary</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Age Group</label>
                  <select className="form-select" title="Voice Age Group" value={form.age || 'middle-aged'} onChange={(e) => setForm(f => ({ ...f, age: e.target.value }))}>
                    <option value="young">Young (18-30)</option>
                    <option value="middle-aged">Middle-aged (30-50)</option>
                    <option value="elderly">Elderly (50+)</option>
                  </select>
                </div>
              </div>

              <div className="grid-2 mb-4">
                <div className="form-group">
                  <label className="form-label">Accent</label>
                  <select className="form-select" title="Voice Accent" value={form.accent || 'american'} onChange={(e) => setForm(f => ({ ...f, accent: e.target.value }))}>
                    <option value="american">American</option>
                    <option value="british">British</option>
                    <option value="australian">Australian</option>
                    <option value="european">European</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Tone & Style</label>
                  <select className="form-select" title="Voice Tone" value={form.tone || 'conversational'} onChange={(e) => setForm(f => ({ ...f, tone: e.target.value }))}>
                    <option value="conversational">Conversational</option>
                    <option value="authoritative">Authoritative / News</option>
                    <option value="narrative">Storytelling</option>
                    <option value="energetic">Energetic / Promo</option>
                  </select>
                </div>
              </div>
              <p className="text-xs text-amber mb-0 font-bold">✨ Synthesizing voice persona using VoiceCraft Designer...</p>
            </div>
          )}

          <div className="modal-actions mt-6">
            <button className="btn btn-secondary" onClick={() => setShowModal(false)} title="Cancel">Cancel</button>
            <button id="create-voice-btn" className="btn btn-primary" onClick={createVoice} disabled={loading} title="Create Voice">
              {loading ? <Spinner /> : form.mode === 'design' ? 'Generate Voice' : 'Next Step'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
