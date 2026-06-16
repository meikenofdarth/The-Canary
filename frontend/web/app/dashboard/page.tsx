'use client';

import { useEffect, useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardNavbar } from '@/components/dashboard-navbar';
import { UsageChart } from '@/components/usage-chart';
import { SpeakersList } from '@/components/speakers-list';
import { Plus, Settings, List } from 'lucide-react';

export default function Dashboard() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // TODO: API Integration - Fetch user session
    // GET /api/auth/session
    // Response: { userId, email, authenticated: boolean }
    
    // Check if user is logged in
    const loggedIn = sessionStorage.getItem('isLoggedIn');
    if (!loggedIn) {
      router.push('/login');
    } else {
      setIsAuthenticated(true);
    }
    setIsLoading(false);
  }, [router]);

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

        {/* Additional Stats Section */}
        {/* TODO: API Integration - Fetch dashboard metrics */}
        {/* GET /api/dashboard/metrics */}
        {/* Response: { commandsProcessed, activeSessions, avgResponseTime, accuracyRate } */}
        <div className="mt-8 grid gap-4 sm:grid-cols-2 md:grid-cols-4">
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md transition-shadow">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Voice Commands Processed</p>
            <p className="mt-3 text-3xl font-bold text-foreground">145,892</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md transition-shadow">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Active Voice Sessions</p>
            <p className="mt-3 text-3xl font-bold text-foreground">2,384</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md transition-shadow">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Avg. Response Time</p>
            <p className="mt-3 text-3xl font-bold text-foreground">320ms</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm hover:shadow-md transition-shadow">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Accuracy Rate</p>
            <p className="mt-3 text-3xl font-bold text-foreground">94.2%</p>
          </div>
        </div>
      </main>
    </>
  );
}
