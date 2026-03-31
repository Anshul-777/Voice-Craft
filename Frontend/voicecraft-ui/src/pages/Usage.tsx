import React from 'react';
import { Zap } from 'lucide-react';

const plans = [
  { name: 'Free', price: '$0', voices: 2, chars: '10K', finetune: false, cls: 'text-muted', current: true },
  { name: 'Starter', price: '$29/mo', voices: 10, chars: '100K', finetune: false, cls: 'text-violet' },
  { name: 'Pro', price: '$99/mo', voices: 50, chars: '1M', finetune: true, cls: 'text-green' },
  { name: 'Enterprise', price: 'Custom', voices: '∞', chars: '∞', finetune: true, cls: 'text-amber' },
];

const features = [
  { label: 'Voice Profiles', Free: '2', Starter: '10', Pro: '50', Enterprise: '∞' },
  { label: 'TTS Chars/Month', Free: '10K', Starter: '100K', Pro: '1M', Enterprise: '∞' },
  { label: 'Fine-Tuning', Free: '❌', Starter: '❌', Pro: '✅', Enterprise: '✅' },
  { label: 'API Access', Free: '✅', Starter: '✅', Pro: '✅', Enterprise: '✅' },
  { label: 'WebSocket Streaming', Free: '✅', Starter: '✅', Pro: '✅', Enterprise: '✅' },
  { label: 'Priority Queue', Free: '❌', Starter: '❌', Pro: '✅', Enterprise: '✅' },
  { label: 'SLA', Free: '❌', Starter: '❌', Pro: '99.9%', Enterprise: '99.99%' },
  { label: 'Dedicated Support', Free: '❌', Starter: 'Email', Pro: 'Priority', Enterprise: 'Dedicated' },
];

export default function Usage() {
  const usedChars = 2437;
  const limitChars = 10000;
  const usedVoices = 1;
  const pct = (usedChars / limitChars) * 100;

  return (
    <div className="main">
      <div className="page-header">
        <h1 className="page-title">Usage & Billing</h1>
        <p className="page-subtitle">Current plan and resource consumption</p>
      </div>

      <div className="card mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="card-title">Current Plan</div>
            <div className="flex items-center gap-3 mt-4">
              <span className="font-24 font-800">Free</span>
              <span className="badge badge-gray">Active</span>
            </div>
          </div>
          <button className="btn btn-primary" title="Upgrade Plan"><Zap size={14} /> Upgrade Plan</button>
        </div>

        <div className="grid-2">
          <div>
            <div className="text-sm text-muted mb-2">TTS Characters</div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-bold">{usedChars.toLocaleString()}</span>
              <span className="text-xs text-muted">/ {limitChars.toLocaleString()}</span>
            </div>
            <div className="progress-wrap">
              <div className="progress-fill" style={{ width: `${pct}%`, background: pct > 80 ? 'var(--red)' : undefined } as React.CSSProperties} />
            </div>
            <div className="text-xs text-muted mt-2">{(limitChars - usedChars).toLocaleString()} remaining this month</div>
          </div>
          <div>
            <div className="text-sm text-muted mb-2">Voice Profiles</div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-bold">{usedVoices}</span>
              <span className="text-xs text-muted">/ 2</span>
            </div>
            <div className="progress-wrap">
              <div className="progress-fill green" style={{ width: `${(usedVoices / 2) * 100}%` } as React.CSSProperties} />
            </div>
            <div className="text-xs text-muted mt-2">1 slot remaining</div>
          </div>
        </div>
      </div>

      <h2 className="font-bold font-14 mb-4">Upgrade Your Plan</h2>
      <div className="grid-3 mb-6 flex">
        {plans.map((p) => (
          <div key={p.name} className={`card flex-1 text-center border-b`}>
            <div className={`font-11 font-bold uppercase letter-spacing-1 mb-8 ${p.cls}`}>{p.name}</div>
            <div className="font-28 font-800 mb-2">{p.price}</div>
            <div className="text-xs text-muted mb-4">{p.chars} chars/mo</div>
            {!p.current ? (
              <button className="btn btn-primary w-full btn-sm" title={`Upgrade to ${p.name}`}>Upgrade</button>
            ) : (
              <span className="badge badge-gray w-full flex justify-center">Current</span>
            )}
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Feature Comparison</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Feature</th>
                {plans.map((p) => <th key={p.name} className={p.cls}>{p.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {features.map((f) => (
                <tr key={f.label}>
                  <td className="text-sm">{f.label}</td>
                  {plans.map((p) => (
                    <td key={p.name} className="text-sm text-center">
                      {(f as any)[p.name]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
