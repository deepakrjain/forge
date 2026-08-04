import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  ListTodo,
  Skull,
  Cpu,
  Activity,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { useJobEvents } from '../hooks/useJobEvents';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/jobs', icon: ListTodo, label: 'Jobs' },
  { to: '/dlq', icon: Skull, label: 'Dead Letter Queue' },
  { to: '/workers', icon: Cpu, label: 'Workers' },
];

export const Layout: React.FC = () => {
  const { isConnected } = useJobEvents();

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── Sidebar ─────────────────────────────────────── */}
      <aside className="flex flex-col w-60 shrink-0 border-r border-border bg-bg-secondary">
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-5 h-16 border-b border-border">
          <Activity className="w-5 h-5 text-accent" />
          <span className="text-lg font-semibold tracking-tight text-text-primary">
            Forge
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-3 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-accent-muted text-accent-hover'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                }`
              }
            >
              <Icon className="w-[18px] h-[18px]" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Connection Status */}
        <div className="px-5 py-4 border-t border-border">
          <div className="flex items-center gap-2 text-xs">
            {isConnected ? (
              <>
                <Wifi className="w-3.5 h-3.5 text-status-succeeded" />
                <span className="text-text-secondary">Live</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3.5 h-3.5 text-status-failed" />
                <span className="text-text-secondary">Disconnected</span>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* ── Main Content ────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto bg-bg-primary">
        <div className="max-w-7xl mx-auto px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
