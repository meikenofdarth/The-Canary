'use client';

import { Mic } from 'lucide-react';
import { useState, useEffect } from 'react';

interface Speaker {
  id: string;
  name: string;
  avatar: string;
  priority: number;
  status: 'active' | 'scheduled' | 'completed';
}

const defaultSpeakers: Speaker[] = [
  {
    id: '1',
    name: 'Voice Model Pro',
    avatar: '/avatars/lion.png',
    priority: 5,
    status: 'active',
  },
  {
    id: '2',
    name: 'Canary Assistant',
    avatar: '/avatars/owl.png',
    priority: 4,
    status: 'scheduled',
  },
  {
    id: '3',
    name: 'Smart Engine',
    avatar: '/avatars/fox.png',
    priority: 3,
    status: 'scheduled',
  },
  {
    id: '4',
    name: 'Advanced Listener',
    avatar: '/avatars/raven.png',
    priority: 2,
    status: 'completed',
  },
  {
    id: '5',
    name: 'Canary Neural',
    avatar: '/avatars/eagle.png',
    priority: 1,
    status: 'scheduled',
  },
];

const statusColors = {
  active: 'bg-green-100 text-green-700',
  scheduled: 'bg-blue-100 text-blue-700',
  completed: 'bg-gray-100 text-gray-700',
};

export function SpeakersList() {
  const [speakers, setSpeakers] = useState<Speaker[]>(defaultSpeakers);

  useEffect(() => {
    // Load speakers from sessionStorage if available
    const storedSpeakers = sessionStorage.getItem('speakersData');
    if (storedSpeakers) {
      try {
        setSpeakers(JSON.parse(storedSpeakers));
      } catch (err) {
        console.error('Error parsing speakers data:', err);
        setSpeakers(defaultSpeakers);
      }
    }

    // Listen for storage changes from other tabs
    const handleStorageChange = () => {
      const updated = sessionStorage.getItem('speakersData');
      if (updated) {
        try {
          setSpeakers(JSON.parse(updated));
        } catch (err) {
          console.error('Error parsing speakers data:', err);
        }
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  const sortedSpeakers = [...speakers].sort((a, b) => b.priority - a.priority);

  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <p className="mb-4 text-xs text-muted-foreground">
        Manage and monitor voice assistants
      </p>

      <div className="space-y-3">
        {sortedSpeakers.map((speaker) => (
          <div
            key={speaker.id}
            className="flex items-center gap-4 rounded-lg border border-border bg-secondary/30 p-4 transition-all duration-200 hover:bg-secondary/60"
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/20">
              <img
                src={speaker.avatar}
                alt={speaker.name}
                className="h-10 w-10 rounded-full"
              />
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
      </div>
    </div>
  );
}
