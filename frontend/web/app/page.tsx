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
            Multi-speaker voice intelligence for noisy, real-world rooms. The Canary
            separates overlapping voices, identifies who&apos;s speaking, understands
            their intent, and arbitrates conflicting commands — all in real time.
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
            What The Canary Does
          </h2>
          <p className="mt-4 text-center text-lg text-muted-foreground">
            A complete voice intelligence pipeline, from microphone to action
          </p>

          <div className="mt-12 grid gap-8 md:grid-cols-3">
            <div className="rounded-lg border border-border bg-card p-6">
              <div className="h-12 w-12 rounded-lg bg-primary/20 flex items-center justify-center mb-4">
                <span className="text-base font-bold text-primary">01</span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">Source Separation</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Neural source separation untangles overlapping voices into clean,
                individually transcribable streams — even in crowded, noisy rooms.
              </p>
            </div>

            <div className="rounded-lg border border-border bg-card p-6">
              <div className="h-12 w-12 rounded-lg bg-primary/20 flex items-center justify-center mb-4">
                <span className="text-base font-bold text-primary">02</span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">Voice Identity</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Speaker biometrics match each voice to an enrolled profile across
                multiple independent acoustic feature dimensions.
              </p>
            </div>

            <div className="rounded-lg border border-border bg-card p-6">
              <div className="h-12 w-12 rounded-lg bg-primary/20 flex items-center justify-center mb-4">
                <span className="text-base font-bold text-primary">03</span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">Arbitration</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                When multiple speakers issue commands, a priority engine resolves
                conflicts and routes the right action to the right person.
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
            Four stages from raw audio to executed command
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
