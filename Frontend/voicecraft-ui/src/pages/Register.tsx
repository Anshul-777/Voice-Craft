import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mic2 } from 'lucide-react';
import api from '../lib/api';
import { useAuthStore, useToastStore } from '../store';
import { Spinner } from '../components/UI';

export default function Register() {
  const [form, setForm] = useState({ email: '', username: '', password: '' });
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const { addToast } = useToastStore();
  const navigate = useNavigate();

  const update = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post('/api/auth/register', form);
      const res = await api.post('/api/auth/login', { email: form.email, password: form.password });
      const { access_token } = res.data;
      setAuth(access_token, { id: '1', email: form.email, username: form.username, plan: 'Free' });
      addToast('Account created! Welcome to VoiceCraft.', 'success');
      navigate('/dashboard');
    } catch (err: any) {
      addToast(err.message || 'Registration failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-left relative">
        <div className="hero-bg-glow" style={{ background: 'radial-gradient(circle, rgba(16,185,129,0.08) 0%, transparent 60%)' }}></div>
        <div className="text-center">
          <Mic2 size={64} className="text-green mb-24 opacity-80" />
          <h1 className="font-32 font-800 mb-12">Start for <span className="text-green">Free</span></h1>
          <p className="text-muted max-w-320 line-height-16 mx-auto">
            2 voice profiles, 10,000 TTS characters/month, full deepfake detection. No credit card required.
          </p>
          <div className="mt-32 flex flex-col gap-10 max-w-280 mx-auto">
            {['✅ Zero-shot voice cloning from 6s audio', '🔍 5-model deepfake detection ensemble', '⚡ Real-time WebSocket streaming', '🌍 17 languages, 14 emotions'].map((f) => (
              <div key={f} className="font-13 text-dim text-left">{f}</div>
            ))}
          </div>
        </div>
      </div>
      <div className="auth-right">
        <div className="auth-card">
          <div className="auth-logo">Voice<em className="text-violet">Craft</em></div>
          <div className="auth-tagline">Create your free account</div>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="reg-email">Email</label>
              <input id="reg-email" className="form-input" type="email" placeholder="you@company.com" value={form.email} onChange={(e) => update('email', e.target.value)} required />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="reg-username">Username</label>
              <input id="reg-username" className="form-input" type="text" placeholder="yourname" value={form.username} onChange={(e) => update('username', e.target.value)} required />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="reg-password">Password</label>
              <input id="reg-password" className="form-input" type="password" placeholder="Min 8 characters" value={form.password} onChange={(e) => update('password', e.target.value)} required minLength={8} />
            </div>
            <button id="reg-submit" className="btn btn-primary w-full mt-8" type="submit" disabled={loading}>
              {loading ? <Spinner /> : 'Create Account'}
            </button>
          </form>
          <div className="auth-divider">— or —</div>
          <p className="text-center font-14 text-muted">
            Already have an account? <Link className="auth-link" to="/login">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
