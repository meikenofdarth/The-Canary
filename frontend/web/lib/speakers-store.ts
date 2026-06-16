// Shared speakers database - accessed everywhere for real-time sync
export interface Speaker {
  id: string;
  name: string;
  priority: number;
  icon: string;
  isAccessible: boolean;
  recordings?: {
    script1?: Blob;
    script2?: Blob;
    script3?: Blob;
  };
}

// Default speakers data - 5 normal speakers + 1 accessibility speaker
export const DEFAULT_SPEAKERS: Speaker[] = [
  { id: '1', name: 'Voice Model Pro', priority: 5, icon: '🦁', isAccessible: false },
  { id: '2', name: 'Canary Assistant', priority: 4, icon: '🦉', isAccessible: false },
  { id: '3', name: 'Smart Engine', priority: 3, icon: '🦊', isAccessible: false },
  { id: '4', name: 'Canary Neural', priority: 2, icon: '🐺', isAccessible: false },
  { id: '5', name: 'Echo Voice', priority: 1, icon: '🦅', isAccessible: false },
  { id: 'accessibility-1', name: 'Advanced Listener', priority: 0, icon: '➕', isAccessible: true },
];

export const ACCESSIBILITY_SPEAKER: Speaker = {
  id: 'accessibility-1',
  name: 'Advanced Listener',
  priority: 0, // No priority for accessibility speaker
  icon: '➕',
  isAccessible: true,
};

// Get all speakers from sessionStorage or return defaults
export function getSpeakers(): Speaker[] {
  if (typeof window === 'undefined') return DEFAULT_SPEAKERS;
  
  const stored = sessionStorage.getItem('speakers_db');
  if (stored) {
    try {
      return JSON.parse(stored);
    } catch (e) {
      console.error('Failed to parse speakers:', e);
      return DEFAULT_SPEAKERS;
    }
  }
  return DEFAULT_SPEAKERS;
}

// Save speakers to sessionStorage
export function setSpeakers(speakers: Speaker[]): void {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem('speakers_db', JSON.stringify(speakers));
}

// Get normal speakers (non-accessibility)
export function getNormalSpeakers(): Speaker[] {
  return getSpeakers().filter(s => !s.isAccessible).sort((a, b) => b.priority - a.priority);
}

// Get accessibility speaker
export function getAccessibilitySpeaker(): Speaker | null {
  const speakers = getSpeakers();
  return speakers.find(s => s.isAccessible) || null;
}

// Add a new speaker
export function addSpeaker(speaker: Speaker): void {
  const speakers = getSpeakers();
  speakers.push(speaker);
  setSpeakers(speakers);
}

// Update speaker
export function updateSpeaker(id: string, updates: Partial<Speaker>): void {
  const speakers = getSpeakers();
  const index = speakers.findIndex(s => s.id === id);
  if (index !== -1) {
    speakers[index] = { ...speakers[index], ...updates };
    setSpeakers(speakers);
  }
}

// Delete speaker
export function deleteSpeaker(id: string): void {
  const speakers = getSpeakers().filter(s => s.id !== id);
  setSpeakers(speakers);
}

// Change priority (allows duplicate priorities)
export function changePriority(speakerId: string, newPriority: number): void {
  const speakers = getSpeakers();
  const speaker = speakers.find(s => s.id === speakerId);
  
  if (!speaker || speaker.isAccessible) return; // Can't change accessibility speaker priority
  
  // Simply update the speaker's priority - no auto-adjustment needed
  const updated = speakers.map(s => 
    s.id === speakerId ? { ...s, priority: newPriority } : s
  );
  
  setSpeakers(updated);
}
