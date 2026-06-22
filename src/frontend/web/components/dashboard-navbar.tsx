'use client';

import { useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { LogOut, Home } from 'lucide-react';

export function DashboardNavbar() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const handleLogout = () => {
    sessionStorage.removeItem('isLoggedIn');
    sessionStorage.removeItem('phoneNumber');
    startTransition(() => {
      router.push('/login');
    });
  };

  return (
    <nav className="sticky top-0 z-40 border-b border-border bg-card/80 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        {/* Home Icon - clicks to go to landing page */}
        <button
          onClick={() => startTransition(() => router.push('/'))}
          disabled={isPending}
          className="flex items-center gap-2 text-primary transition-all hover:text-primary/80 hover:scale-110 disabled:opacity-60"
          title="Go to home"
        >
          <Home className="h-6 w-6" />
        </button>

        {/* Right side - Logout */}
        <button
          onClick={handleLogout}
          disabled={isPending}
          className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-foreground transition-all duration-200 hover:bg-secondary disabled:opacity-60"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </nav>
  );
}
