'use client';

import { useState, useEffect } from 'react';
import { getSpeakers, refreshSpeakers, type Speaker } from '@/lib/speakers-store';

export function SpeakersList() {
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;

    const load = async () => {
      // Show cached snapshot immediately, then refresh from backend
      const cached = getSpeakers();
      if (alive && cached.length) setSpeakers(cached);

      try {
        const fresh = await refreshSpeakers();
        if (alive) setSpeakers(fresh);
      } catch (err) {
        console.error('Error loading speakers:', err);
      } finally {
        if (alive) setLoading(false);
      }
    };

    load();

    const handleStorageChange = () => {
      if (alive) setSpeakers(getSpeakers());
    };
    window.addEventListener('storage', handleStorageChange);

    return () => {
      alive = false;
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  // Separate normal speakers and accessibility speaker
  const normalSpeakers = speakers
    .filter((s) => !s.isAccessible)
    .sort((a, b) => b.priority - a.priority);
  const accessibilitySpeaker = speakers.find((s) => s.isAccessible);

  if (loading && speakers.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
        <p className="text-muted-foreground text-sm">Loading speakers...</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <p className="mb-4 text-xs text-muted-foreground">
        Enrolled speakers in the database
      </p>

      <div className="space-y-3">
        {speakers.length === 0 && (
          <div className="rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center">
            <p className="text-sm text-muted-foreground">
              No speakers enrolled yet.
            </p>
          </div>
        )}

        {/* Normal Speakers */}
        {normalSpeakers.map((speaker) => (
          <div
            key={speaker.id}
            className="flex items-center gap-4 rounded-lg border border-border bg-secondary/30 p-4 transition-all duration-200 hover:bg-secondary/60"
          >
            <div className="text-2xl flex-shrink-0">{speaker.icon}</div>

            <div className="flex-1 min-w-0">
              <p className="truncate font-medium text-foreground">
                {speaker.name}
              </p>
              <p className="truncate text-sm text-muted-foreground">
                Priority: {speaker.priority} &middot; {speaker.city ?? '—'}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="inline-block rounded-full px-3 py-1 text-xs font-medium bg-green-100 text-green-700">
                {speaker.recordingCount ?? 3} rec
              </span>
            </div>
          </div>
        ))}

        {/* Accessibility Speaker (UI-only flag) */}
        {accessibilitySpeaker && (
          <div className="flex items-center gap-4 rounded-lg border-2 border-primary/40 bg-primary/5 p-4 transition-all duration-200 hover:bg-primary/10">
            <div className="text-2xl flex-shrink-0">
              {accessibilitySpeaker.icon}
            </div>

            <div className="flex-1 min-w-0">
              <p className="truncate font-medium text-foreground">
                {accessibilitySpeaker.name}
              </p>
              <p className="truncate text-sm text-muted-foreground">
                Accessibility enabled
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="inline-block rounded-full px-3 py-1 text-xs font-medium bg-blue-100 text-blue-700">
                Special
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
