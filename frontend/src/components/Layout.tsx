import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, HeartPulse, FlaskConical, Zap } from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/health', icon: HeartPulse, label: 'Health' },
  { to: '/playground', icon: FlaskConical, label: 'Playground' },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-dark-950 flex">
      <aside className="w-64 bg-dark-900 border-r border-gray-800 flex flex-col">
        <div className="p-6 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-600 rounded-lg">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-white font-bold text-sm">Token Suppressor</h1>
              <p className="text-gray-500 text-xs">Admin Dashboard</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary-600/10 text-primary-400 border border-primary-500/20'
                    : 'text-gray-400 hover:text-white hover:bg-dark-800'
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-800">
          <p className="text-gray-600 text-xs text-center">v1.0.0 — MVP Enterprise</p>
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        <div className="p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
