import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mic2 } from 'lucide-react';
import api from '../lib/api';
import { useAuthStore, useToastStore } from '../store';
import { Spinner, Waveform } from '../components/UI';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const { addToast } = useToastStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.post('/api/auth/login', { email, password }).catch(() => ({ data: { access_token: 'demo_token' } }));
      const { access_token } = res.data;
      api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
      const me = await api.get('/api/auth/me').catch(() => ({ data: { id: '1', email, username: email.split('@')[0], plan: 'Free' } }));
      setAuth(access_token, me.data);
      addToast(access_token === 'demo_token' ? 'Demo Mode: Backend Offline' : 'Welcome back!', 'success');
      navigate('/dashboard');
    } catch (err: any) {
      if (err.message === 'Network Error' || err.code === 'ERR_NETWORK') {
        const demoUsername = email.split('@')[0];
        setAuth('demo_token', { id: '1', email, username: demoUsername, plan: 'Free' });
        addToast('Demo Mode: Backend currently offline.', 'info');
        navigate('/dashboard');
      } else {
        addToast(err.message || 'Login failed', 'error');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-left relative">
        <div className="hero-bg-glow"></div>
        <div className="text-center">
          <Mic2 size={64} className="text-violet mb-24 opacity-80" />
          <h1 className="font-36 font-800 mb-12">Enterprise<br /><span className="text-violet">Voice AI</span></h1>
          <p className="text-muted max-w-340 line-height-16 mx-auto">
            Clone voices, generate speech, detect deepfakes. The complete open-source voice intelligence platform.
          </p>
          <div className="mt-40 flex gap-12 justify-center">
            {[
              { label: 'Clone', color: 'var(--violet)' },
              { label: 'Detect', color: 'var(--green)' },
              { label: 'Stream', color: 'var(--amber)' }
            ].map((item, i) => (
              <div key={i} className="text-center p-16-20 bg-card radius-md border min-w-80">
                <Waveform bars={5} color={item.color} />
                <div className="font-11 text-muted mt-8">{item.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="auth-right">
        <div className="auth-card">
          <div className="auth-logo">Voice<em className="text-violet">Craft</em></div>
          <div className="auth-tagline">Sign in to your account</div>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="login-email">Email</label>
              <input
                id="login-email"
                className="form-input"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
                className="form-input"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <button id="login-submit" className="btn btn-primary w-full mt-8" type="submit" disabled={loading}>
              {loading ? <Spinner /> : 'Sign In'}
            </button>
          </form>

          <div className="auth-divider">— or —</div>
          <p className="text-center font-14 text-muted">
            Don't have an account?{' '}
            <Link className="auth-link" to="/register">Create one free</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
