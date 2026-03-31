import React, { useState, useEffect } from 'react';
import { Key, Plus, Copy, Trash2 } from 'lucide-react';
import { Modal, Spinner } from '../components/UI';
import { useToastStore } from '../store';
import api from '../lib/api';

export default function ApiKeys() {
  const [keys, setKeys] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [scopes, setScopes] = useState(['tts']);
  const [keyName, setKeyName] = useState('');
  const { addToast } = useToastStore();

  useEffect(() => {
    api.get('/api/keys').then(r => setKeys(r.data || [])).catch(() => {});
  }, []);

  const createKey = async () => {
    setLoading(true);
    try {
      const r = await api.post('/api/keys', { name: keyName, scopes });
      setNewKey(r.data.key);
      setKeys((k) => [...k, r.data.metadata]);
    } catch (err: any) {
      addToast(err.message || 'Key creation failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  const copy = (text: string) => {
    navigator.clipboard.writeText(text);
    addToast('Copied to clipboard!', 'success');
  };

  const revokeKey = async (id: string) => {
    try {
      await api.delete(`/api/keys/${id}`);
      setKeys((k) => k.filter((key) => key.id !== id));
      addToast('API key revoked', 'info');
    } catch (err: any) {
      addToast('Failed to revoke key', 'error');
    }
  };

  const allScopes = ['tts', 'clone', 'detect', 'admin'];

  return (
    <div className="main">
      <div className="page-header">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="page-title">API Keys</h1>
            <p className="page-subtitle">Manage programmatic access to your VoiceCraft account</p>
          </div>
          <button className="btn btn-primary" onClick={() => { setShowCreate(true); setNewKey(''); }} title="Create Key">
            <Plus size={16} /> Create Key
          </button>
        </div>
      </div>

      <div className="card">
        {keys.length > 0 ? (
           <div className="table-wrap">
             <table>
               <thead>
                 <tr><th>Key Name/Prefix</th><th>Scopes</th><th>Last Used</th><th>Created</th><th>Actions</th></tr>
               </thead>
               <tbody>
                 {keys.map((k) => (
                   <tr key={k.id}>
                     <td>
                        <div className="font-bold">{k.name}</div>
                        <code className="font-mono text-xs text-violet mt-2">{k.prefix}</code>
                     </td>
                     <td><div className="flex gap-2 flex-wrap">{k.scopes?.map((s: string) => <span key={s} className="badge badge-violet">{s}</span>)}</div></td>
                     <td className="text-muted text-sm">{k.lastUsed || 'Never'}</td>
                     <td className="text-muted text-sm">{k.created ? new Date(k.created).toLocaleDateString() : 'Today'}</td>
                     <td>
                       <button className="btn btn-danger btn-sm" onClick={() => revokeKey(k.id)} title="Revoke Key">
                         <Trash2 size={12} /> Revoke
                       </button>
                     </td>
                   </tr>
                 ))}
               </tbody>
             </table>
           </div>
        ) : (
           <div className="text-center p-40">
              <Key size={48} className="opacity-80 text-violet m-auto mb-16" />
              <h3 className="font-bold font-24 mb-8">No API Keys Generated</h3>
              <p className="text-muted max-w-340 m-auto line-height-16 mb-24">
                Create keys with fine-grained scopes to integrate VoiceCraft audio synthesis and deepfake detection directly into your backend architecture.
              </p>
              <button className="btn btn-primary m-auto" onClick={() => { setShowCreate(true); setNewKey(''); }} title="Create Key">
                <Plus size={16} /> Generate First Key
              </button>
           </div>
        )}
      </div>

      {showCreate && (
        <Modal title="Create API Key" onClose={() => { setShowCreate(false); setNewKey(''); }}>
          {!newKey ? (
            <>
              <div className="form-group">
                <label className="form-label" htmlFor="api-key-name">Key Name</label>
                <input id="api-key-name" className="form-input" placeholder="e.g. Production App" value={keyName} onChange={(e) => setKeyName(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="api-key-scope">Scopes</label>
                <div className="flex gap-3">
                  {allScopes.map((s) => (
                    <label key={s} className="flex items-center gap-6 cursor-pointer font-13">
                      <input type="checkbox" id={`scope-${s}`} title={s} checked={scopes.includes(s)} onChange={(e) => {
                        setScopes((prev) => e.target.checked ? [...prev, s] : prev.filter((x) => x !== s));
                      }} />
                      {s}
                    </label>
                  ))}
                </div>
              </div>
              <div className="modal-actions">
                <button className="btn btn-secondary" onClick={() => setShowCreate(false)} title="Cancel">Cancel</button>
                <button id="gen-key-btn" className="btn btn-primary" onClick={createKey} title="Generate" disabled={loading}>
                  {loading ? <Spinner /> : 'Generate Key'}
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="bg-amber-soft border p-16-20 mb-16 font-13 text-amber radius-sm">
                ⚠️ <strong>This key will only be shown once.</strong> Copy it now and store it securely.
              </div>
              <div className="bg-elevated radius-sm p-16-20 flex items-center gap-3 mb-16">
                <code className="font-mono text-sm flex-1 word-break text-green">{newKey}</code>
                <button className="btn btn-secondary btn-sm" onClick={() => copy(newKey)} title="Copy Key">
                  <Copy size={14} /> Copy
                </button>
              </div>
              <div className="modal-actions">
                <button className="btn btn-primary" onClick={() => { setShowCreate(false); setNewKey(''); }} title="Done">Done</button>
              </div>
            </>
          )}
        </Modal>
      )}
    </div>
  );
}
