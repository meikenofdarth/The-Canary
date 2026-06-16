'use client';

import { Mic } from 'lucide-react';
import { useState, useEffect } from 'react';

interface Speaker {
  id: string;
  name: string;
  icon: string;
  priority: number;
  status: 'active' | 'scheduled' | 'completed';
  isAccessible?: boolean;
}

const statusColors = {
  active: 'bg-green-100 text-green-700',
  scheduled: 'bg-blue-100 text-blue-700',
  completed: 'bg-gray-100 text-gray-700',
};

export function SpeakersList() {
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Load speakers from the store
    const loadSpeakers = async () => {
      try {
        const { getSpeakers } = await import('@/lib/speakers-store');
        const allSpeakers = getSpeakers();
        
        // Transform speakers data for display
        const displaySpeakers = allSpeakers.map((s: any) => ({
          id: s.id,
          name: s.name,
          icon: s.icon,
          priority: s.priority,
          status: 'scheduled' as const,
          isAccessible: s.isAccessible,
        }));
        
        setSpeakers(displaySpeakers);
      } catch (err) {
        console.error('Error loading speakers:', err);
      } finally {
        setLoading(false);
      }
    };

    loadSpeakers();

    // Listen for storage changes
    const handleStorageChange = () => {
      loadSpeakers();
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  // Separate normal speakers and accessibility speaker
  const normalSpeakers = speakers.filter(s => !s.isAccessible).sort((a, b) => b.priority - a.priority);
  const accessibilitySpeaker = speakers.find(s => s.isAccessible);

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
        <p className="text-muted-foreground text-sm">Loading speakers...</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <p className="mb-4 text-xs text-muted-foreground">
        Manage and monitor voice assistants
      </p>

      <div className="space-y-3">
        {/* Normal Speakers */}
        {normalSpeakers.map((speaker) => (
          <div
            key={speaker.id}
            className="flex items-center gap-4 rounded-lg border border-border bg-secondary/30 p-4 transition-all duration-200 hover:bg-secondary/60"
          >
            <div className="text-2xl flex-shrink-0">
              {speaker.icon}
            </div>

            <div className="flex-1 min-w-0">
              <p className="truncate font-medium text-foreground">
                {speaker.name}
              </p>
              <p className="truncate text-sm text-muted-foreground">
                Priority: {speaker.priority}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span
                className={`inline-block rounded-full px-3 py-1 text-xs font-medium ${
                  statusColors[speaker.status]
                }`}
              >
                {speaker.status.charAt(0).toUpperCase() +
                  speaker.status.slice(1)}
              </span>
            </div>
          </div>
        ))}

        {/* Accessibility Speaker (if exists) - shown separately without priority */}
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
