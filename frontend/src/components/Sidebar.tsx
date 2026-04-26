import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, BarChart3, TrendingUp, Calculator } from 'lucide-react';
import { cn } from '@/lib/utils';

const navigation = [
  { name: 'Overview', href: '/', icon: LayoutDashboard },
  { name: 'Waterfall Chart', href: '/waterfall', icon: BarChart3 },
  { name: 'Supply/Demand', href: '/supply-demand', icon: TrendingUp },
  { name: 'PD Predictor', icon: Calculator, href: '/predict' },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="flex flex-col w-64 border-r bg-slate-50/50 min-h-screen">
      <div className="p-6">
        <h1 className="text-xl font-bold text-navy-900 flex items-center gap-2">
          <span className="text-crimson-600">🇺🇸</span> Spillover Engine
        </h1>
      </div>
      <nav className="flex-1 px-4 space-y-1">
        {navigation.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors",
                isActive 
                  ? "bg-navy-900 text-white font-semibold" 
                  : "text-slate-600 hover:bg-slate-100 hover:text-navy-900"
              )}
            >
              <item.icon className="w-4 h-4" />
              {item.name}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t">
        <div className="text-xs text-slate-400">
          FY 2026/2027 Projections
        </div>
      </div>
    </div>
  );
}
