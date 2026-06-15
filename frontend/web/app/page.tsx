'use client';

import { useRouter } from 'next/navigation';
import { Timeline } from '@/components/timeline';
import { Footer } from '@/components/footer';
import { ArrowRight } from 'lucide-react';

export default function Home() {
  const router = useRouter();

  return (
    <main className="min-h-screen">
      {/* Hero Section */}
      <section className="relative overflow-hidden px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl text-center">
          <img
            src="https://hebbkx1anhila5yf.public.blob.vercel-storage.com/logo-rod6oexWJWuQxyR1VHbFvYyBq59vIN.png"
            alt="The Canary"
            className="mx-auto h-20 w-20"
          />

          <h1 className="mt-8 text-5xl font-bold leading-tight text-foreground sm:text-6xl">
            The Canary
          </h1>

          <p className="mt-6 text-xl leading-relaxed text-muted-foreground">
            Master your voice assistant platform with intelligent management, real-time analytics, and 
            seamless command prioritization. Empower your team to build better voice experiences.
          </p>

          <button
            onClick={() => router.push('/login')}
            className="mt-8 inline-flex items-center gap-2 rounded-lg bg-primary px-8 py-4 text-lg font-semibold text-primary-foreground transition-all duration-300 hover:shadow-lg hover:shadow-primary/40 hover:scale-105"
          >
            Get Started
            <ArrowRight className="h-5 w-5" />
          </button>
        </div>

        {/* Decorative gradient */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-40 right-0 h-80 w-80 rounded-full bg-primary/10 blur-3xl" />
          <div className="absolute -bottom-40 left-0 h-80 w-80 rounded-full bg-primary/5 blur-3xl" />
        </div>
      </section>

      {/* Features Section */}
      <section className="relative border-t border-border bg-secondary/20 px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-5xl">
          <h2 className="text-center text-3xl font-bold text-foreground">
            Built for Modern Teams
          </h2>
          <p className="mt-4 text-center text-lg text-muted-foreground">
            Everything you need to manage voice assistants at scale
          </p>

          <div className="mt-12 grid gap-8 md:grid-cols-3">
            <div className="rounded-lg border border-border bg-card p-6">
              <div className="h-12 w-12 rounded-lg bg-primary/20 flex items-center justify-center mb-4">
                <span className="text-xl">📊</span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">Real-Time Analytics</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Monitor performance metrics, command accuracy, and user engagement with live dashboards.
              </p>
            </div>

            <div className="rounded-lg border border-border bg-card p-6">
              <div className="h-12 w-12 rounded-lg bg-primary/20 flex items-center justify-center mb-4">
                <span className="text-xl">🎙️</span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">Voice Recording</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Capture voice profiles with precision. Record, analyze, and optimize voice interactions.
              </p>
            </div>

            <div className="rounded-lg border border-border bg-card p-6">
              <div className="h-12 w-12 rounded-lg bg-primary/20 flex items-center justify-center mb-4">
                <span className="text-xl">⚡</span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">Smart Prioritization</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Manage command priorities intelligently. Organize workflows and maximize assistant efficiency.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Timeline Section */}
      <section className="relative z-10 px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-5xl">
          <h2 className="text-center text-3xl font-bold text-foreground">
            How It Works
          </h2>
          <p className="mt-4 text-center text-lg text-muted-foreground">
            Four simple steps to master your voice assistant platform
          </p>

          <div className="mt-12">
            <Timeline />
          </div>
        </div>
      </section>

      {/* Footer */}
      <Footer />
    </main>
  );
}
