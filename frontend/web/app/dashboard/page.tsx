'use client';

import { useEffect, useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardNavbar } from '@/components/dashboard-navbar';
import { UsageChart } from '@/components/usage-chart';
import { SpeakersList } from '@/components/speakers-list';
import { Plus, Settings, List } from 'lucide-react';
import { fetchSystemStatus } from '@/lib/api';
import { refreshSpeakers } from '@/lib/speakers-store';

export default function Dashboard() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [status, setStatus] = useState<{
    activeWakeword: string;
    enrolledUsers: number;
    online: boolean;
  }>({ activeWakeword: '—', enrolledUsers: 0, online: false });

  useEffect(() => {
    // Check if user is logged in
    const loggedIn = sessionStorage.getItem('isLoggedIn');
    if (!loggedIn) {
      router.push('/login');
    } else {
      setIsAuthenticated(true);
    }
    setIsLoading(false);
  }, [router]);

  useEffect(() => {
    if (!isAuthenticated) return;

    let alive = true;
    const load = async () => {
      try {
        const [s] = await Promise.all([fetchSystemStatus(), refreshSpeakers()]);
        if (alive) {
          setStatus({
            activeWakeword: s.active_wakeword,
            enrolledUsers: s.enrolled_users,
            online: s.status === 'ok',
          });
        }
      } catch (e) {
        console.error('Status fetch failed', e);
        if (alive) setStatus((p) => ({ ...p, online: false }));
      }
    };

    load();
    const interval = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, [isAuthenticated]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-border border-t-primary" />
          <p className="mt-4 text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <>
      <DashboardNavbar />

      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-8 flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-4xl font-bold text-foreground">Dashboard</h1>
            <p className="mt-2 text-muted-foreground">
              Welcome back. Here&apos;s your voice assistant performance overview.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 lg:flex-nowrap">
            <button
              onClick={() => startTransition(() => router.push('/customize-wakeword'))}
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-lg border-2 border-primary bg-transparent px-6 py-3 font-semibold text-primary transition-all hover:bg-primary/10 hover:shadow-md disabled:opacity-60"
            >
              <Settings className="h-5 w-5" />
              Set Up Voice Profile
            </button>
            <button
              onClick={() => startTransition(() => router.push('/manage-speakers'))}
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-lg border-2 border-primary bg-transparent px-6 py-3 font-semibold text-primary transition-all hover:bg-primary/10 hover:shadow-md disabled:opacity-60"
            >
              <List className="h-5 w-5" />
              Manage Speakers
            </button>
            <button
              onClick={() => startTransition(() => router.push('/add-speaker'))}
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 font-semibold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/40 whitespace-nowrap disabled:opacity-60"
            >
              <Plus className="h-5 w-5" />
              Add Speaker
            </button>
          </div>
        </div>

        <div className="grid gap-8 lg:grid-cols-3">
          {/* Usage Chart - Takes 2 columns on large screens */}
          <div className="lg:col-span-2">
            <UsageChart />
          </div>

          {/* Speakers List - Takes 1 column on large screens */}
          <div className="lg:col-span-1">
            <SpeakersList />
          </div>
        </div>

        {/* Live status cards driven by GET /api/status + speakers store */}
        <div className="mt-8 grid gap-4 sm:grid-cols-2 md:grid-cols-4">
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md transition-shadow">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Enrolled Speakers</p>
            <p className="mt-3 text-3xl font-bold text-foreground">{status.enrolledUsers} / 5</p>
          </div>
          <button
            onClick={() => startTransition(() => router.push('/customize-wakeword'))}
            className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md hover:border-primary/40 transition-all text-left group"
          >
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Active Wake Word</p>
            <p className="mt-3 text-3xl font-bold text-foreground">&quot;{status.activeWakeword}&quot;</p>
            <p className="mt-2 text-xs text-primary opacity-0 group-hover:opacity-100 transition-opacity">Click to change →</p>
          </button>
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md transition-shadow">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Pipeline Status</p>
            <p className={`mt-3 text-3xl font-bold ${status.online ? 'text-green-600' : 'text-red-500'}`}>
              {status.online ? 'Online' : 'Offline'}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md transition-shadow">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Capacity</p>
            <p className="mt-3 text-3xl font-bold text-foreground">{Math.max(0, 5 - status.enrolledUsers)} free</p>
          </div>
        </div>
      </main>
    </>
  );
}
