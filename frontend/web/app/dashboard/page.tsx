'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardNavbar } from '@/components/dashboard-navbar';
import { UsageChart } from '@/components/usage-chart';
import { SpeakersList } from '@/components/speakers-list';
import { Plus } from 'lucide-react';

export default function Dashboard() {
  const router = useRouter();
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
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Dashboard</h1>
            <p className="mt-2 text-muted-foreground">
              Welcome back. Here&apos;s your voice assistant performance overview.
            </p>
          </div>
          <button
            onClick={() => router.push('/add-speaker')}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 font-semibold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/40"
          >
            {/* TODO: API Integration - Replace icon with Mic if needed */}
            <Plus className="h-5 w-5" />
            Add Speaker
          </button>
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
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Voice Commands Processed</p>
            <p className="mt-2 text-2xl font-bold text-foreground">145,892</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Active Voice Sessions</p>
            <p className="mt-2 text-2xl font-bold text-foreground">2,384</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Avg. Response Time</p>
            <p className="mt-2 text-2xl font-bold text-foreground">320ms</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Accuracy Rate</p>
            <p className="mt-2 text-2xl font-bold text-foreground">94.2%</p>
          </div>
        </div>
      </main>
    </>
  );
}
