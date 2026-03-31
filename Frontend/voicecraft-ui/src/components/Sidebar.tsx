import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Mic2, LayoutDashboard, Library, Shield, Key, BarChart3, LogOut, Settings, PlayCircle, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useAuthStore } from '../store';

const nav = [
  { label: 'Core', items: [
    { icon: LayoutDashboard, label: 'Dashboard', to: '/dashboard' },
    { icon: PlayCircle, label: 'Studio (Generate)', to: '/studio' },
    { icon: Library, label: 'Voice Library', to: '/voices' },
    { icon: Shield, label: 'Deepfake Detector', to: '/detect' },
  ]},
  { label: 'Settings', items: [
    { icon: Key, label: 'API Keys', to: '/settings/api-keys' },
    { icon: BarChart3, label: 'Usage & Billing', to: '/settings/usage' },
  ]},
];

export function Sidebar({ isCollapsed, toggle }: { isCollapsed?: boolean; toggle?: () => void }) {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-logo flex justify-between items-center w-full">
        <div className="flex items-center gap-10">
          <Mic2 size={22} className="text-violet" />
          {!isCollapsed && <span>Voice<em className="text-violet">Craft</em></span>}
        </div>
        {toggle && (
          <button className="text-muted hover:text-white" onClick={toggle} title="Toggle Sidebar">
            {isCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        )}
      </div>

      {nav.map((section) => (
        <div key={section.label} className="nav-section">
          {!isCollapsed && <div className="nav-label">{section.label}</div>}
          {section.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''} ${isCollapsed ? 'justify-center p-12' : ''}`}
              title={isCollapsed ? item.label : undefined}
            >
              <item.icon size={18} className={isCollapsed ? 'm-auto' : ''}/>
              {!isCollapsed && item.label}
            </NavLink>
          ))}
        </div>
      ))}

      <div className="sidebar-spacer" />
      <button className={`nav-item text-red ${isCollapsed ? 'justify-center p-12' : ''}`} onClick={handleLogout} title={isCollapsed ? "Sign Out" : undefined}>
        <LogOut size={18} className={isCollapsed ? 'm-auto' : ''}/>
        {!isCollapsed && "Sign Out"}
      </button>
      {user && (
        <div className="sidebar-user mt-32" title={isCollapsed ? user.username : undefined}>
          <div className="user-avatar">{user.username[0].toUpperCase()}</div>
          {!isCollapsed && (
            <>
              <div className="user-info">
                <div className="user-name">{user.username}</div>
                <div className="user-plan">{user.plan || 'Free'}</div>
              </div>
              <Settings size={14} className="text-muted" />
            </>
          )}
        </div>
      )}
    </div>
  );
}
