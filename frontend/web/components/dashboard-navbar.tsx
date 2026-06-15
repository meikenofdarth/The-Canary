'use client';

import { useRouter } from 'next/navigation';
import { LogOut } from 'lucide-react';

export function DashboardNavbar() {
  const router = useRouter();

  const handleLogout = () => {
    sessionStorage.removeItem('isLoggedIn');
    sessionStorage.removeItem('phoneNumber');
    router.push('/login');
  };

  return (
    <nav className="sticky top-0 z-40 border-b border-border bg-card/80 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        {/* Logo - clicks to go home */}
        <button
          onClick={() => router.push('/')}
          className="flex items-center gap-2 transition-opacity hover:opacity-80"
          title="Go to home"
        >
          <img
            src="https://hebbkx1anhila5yf.public.blob.vercel-storage.com/logo-rod6oexWJWuQxyR1VHbFvYyBq59vIN.png"
            alt="The Canary"
            className="h-8 w-8"
          />
        </button>

        {/* Right side - Logout */}
        <button
          onClick={handleLogout}
          className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-foreground transition-all duration-200 hover:bg-secondary"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </nav>
  );
}
