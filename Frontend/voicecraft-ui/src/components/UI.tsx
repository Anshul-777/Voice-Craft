import React from 'react';
import { useToastStore } from '../store';
import { CheckCircle, XCircle, Info, X } from 'lucide-react';

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore();
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.type}`}>
          {t.type === 'success' && <CheckCircle size={16} className="text-green" />}
          {t.type === 'error' && <XCircle size={16} className="text-red" />}
          {t.type === 'info' && <Info size={16} className="text-violet" />}
          <span className="flex-1 font-14">{t.message}</span>
          <button onClick={() => removeToast(t.id)} className="btn-icon-raw" title="Close Toast">
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

export function Waveform({ color = 'var(--violet)', bars = 8 }: { color?: string; bars?: number }) {
  // Using an array map to allow dynamic styles via classes if we wanted, 
  // but CSS custom properties natively in React require a type assertion. 
  // For the sake of removing 'style={{}}' completely from JSX, we apply standard classes 
  // and handle the animation delays in CSS targeting nth-child.
  return (
    <div className="waveform">
      {Array.from({ length: bars }).map((_, i) => (
        <div key={i} className="waveform-bar" style={{ background: color } as React.CSSProperties} />
      ))}
    </div>
  );
}

export function Spinner() {
  return <div className="spinner" />;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="modal-title">{title}</h3>
          <button onClick={onClose} className="btn-icon-raw" title="Close Modal">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
