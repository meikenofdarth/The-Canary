// Speakers store: merges live data from the Canary backend
// (GET /api/users) with UI-only fields kept in localStorage.
//
// Backend owns: name, recording_count, city, news_country, favorite_genre, created_at, voice biometrics.
// Frontend keeps (per name): icon (animal emoji), priority (1-5), isAccessible flag.

import { fetchBackendUsers, deleteBackendUser, updateUserPriority, type BackendUser } from "./api";

export interface Speaker {
  // From backend
  id: string;
  name: string;
  city?: string;
  country?: string;
  musicGenre?: string;
  recordingCount?: number;
  createdAt?: string;
  // UI-only (stored locally)
  priority: number;
  icon: string;
  isAccessible: boolean;
  // For compatibility with existing components
  status?: "active" | "scheduled" | "completed";
}

const ANIMAL_ICONS = ["🦁", "🦉", "🦊", "🐺", "🦅", "🐻", "🐼", "🦝", "🦌", "🦆"];
const UI_KEY = "canary_ui_overrides_v1";
const CACHE_KEY = "canary_speakers_cache_v1";

interface UIOverride {
  priority: number;
  icon: string;
  isAccessible: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
//  UI override helpers (localStorage)
// ─────────────────────────────────────────────────────────────────────────────

function loadOverrides(): Record<string, UIOverride> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(UI_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveOverrides(map: Record<string, UIOverride>): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(UI_KEY, JSON.stringify(map));
  // Notify listeners (manage-speakers + speakers-list both watch storage)
  window.dispatchEvent(new Event("storage"));
}

function pickIcon(used: Set<string>): string {
  const free = ANIMAL_ICONS.find((i) => !used.has(i));
  return free ?? ANIMAL_ICONS[Math.floor(Math.random() * ANIMAL_ICONS.length)];
}

// ─────────────────────────────────────────────────────────────────────────────
//  Cache (so server-rendered pages have something to show before fetch)
// ─────────────────────────────────────────────────────────────────────────────

function readCache(): Speaker[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeCache(s: Speaker[]): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(CACHE_KEY, JSON.stringify(s));
  window.dispatchEvent(new Event("storage"));
}

// ─────────────────────────────────────────────────────────────────────────────
//  Merge backend record + UI overrides
// ─────────────────────────────────────────────────────────────────────────────

function toSpeaker(
  u: BackendUser,
  overrides: Record<string, UIOverride>,
  usedIcons: Set<string>,
  fallbackPriority: number,
): Speaker {
  const o = overrides[u.name];
  const icon = o?.icon ?? pickIcon(usedIcons);
  usedIcons.add(icon);
  return {
    id: String(u.speaker_id),
    name: u.name,
    city: u.city ?? undefined,
    country: u.news_country ?? undefined,
    musicGenre: u.favorite_genre ?? undefined,
    recordingCount: u.recording_count,
    createdAt: u.created_at,
    // Priority comes from the backend DB; fall back to local override only if missing
    priority: u.priority ?? o?.priority ?? fallbackPriority,
    icon,
    isAccessible: o?.isAccessible ?? false,
    status: "scheduled",
  };
}

// ─────────────────────────────────────────────────────────────────────────────
//  Public API
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Synchronous read used by components on first render.
 * Returns the last cached snapshot. Components should also call refreshSpeakers().
 */
export function getSpeakers(): Speaker[] {
  return readCache();
}

/** Hit the backend, merge UI overrides, persist cache, dispatch storage event. */
export async function refreshSpeakers(): Promise<Speaker[]> {
  const overrides = loadOverrides();
  const used = new Set<string>();
  let fallbackPriority = 5;

  let users: BackendUser[];
  try {
    users = await fetchBackendUsers();
  } catch (e) {
    console.error("[speakers-store] backend fetch failed:", e);
    return readCache();
  }

  const merged = users.map((u) => {
    const s = toSpeaker(u, overrides, used, fallbackPriority);
    if (overrides[u.name]?.priority === undefined) fallbackPriority = Math.max(1, fallbackPriority - 1);
    return s;
  });

  writeCache(merged);
  return merged;
}

/** Replace the full speaker list (used after drag-and-drop reorder). */
export function setSpeakers(speakers: Speaker[]): void {
  const overrides = loadOverrides();
  speakers.forEach((s) => {
    overrides[s.name] = {
      priority: s.priority,
      icon: s.icon,
      isAccessible: s.isAccessible,
    };
  });
  saveOverrides(overrides);
  writeCache(speakers);
}

export function getNormalSpeakers(): Speaker[] {
  return getSpeakers()
    .filter((s) => !s.isAccessible)
    .sort((a, b) => b.priority - a.priority);
}

export function getAccessibilitySpeaker(): Speaker | null {
  return getSpeakers().find((s) => s.isAccessible) ?? null;
}

/**
 * Persist a UI override for a newly enrolled speaker (priority + icon + accessibility flag).
 * The backend already created the row via /api/enroll; we just attach UI metadata.
 */
export function addSpeaker(speaker: Speaker): void {
  const overrides = loadOverrides();
  overrides[speaker.name] = {
    priority: speaker.priority,
    icon: speaker.icon || pickIcon(new Set(Object.values(overrides).map((o) => o.icon))),
    isAccessible: speaker.isAccessible,
  };
  saveOverrides(overrides);
  // refreshSpeakers() is awaited by callers right after addSpeaker
}

/** Update one speaker's priority — persists to backend DB and updates local cache. */
export async function changePriority(speakerId: string, newPriority: number): Promise<void> {
  const speakers = getSpeakers();
  const s = speakers.find((x) => x.id === speakerId);
  if (!s || s.isAccessible) return;

  // Persist to backend first
  await updateUserPriority(s.name, newPriority);

  // Update icon/isAccessible override in localStorage (priority no longer stored here)
  const overrides = loadOverrides();
  overrides[s.name] = {
    priority: newPriority, // keep for offline fallback
    icon: overrides[s.name]?.icon ?? s.icon,
    isAccessible: overrides[s.name]?.isAccessible ?? false,
  };
  saveOverrides(overrides);

  const updated = speakers.map((x) =>
    x.id === speakerId ? { ...x, priority: newPriority } : x,
  );
  writeCache(updated);
}

/** Delete: hits backend DELETE /api/users/{name}, then strips override + cache. */
export async function deleteSpeaker(id: string): Promise<void> {
  const speakers = getSpeakers();
  const target = speakers.find((s) => s.id === id);
  if (!target) return;

  try {
    await deleteBackendUser(target.name);
  } catch (e) {
    console.error("[speakers-store] delete failed:", e);
    throw e;
  }

  const overrides = loadOverrides();
  delete overrides[target.name];
  saveOverrides(overrides);
  writeCache(speakers.filter((s) => s.id !== id));
}

/** Synchronous delete kept for legacy callers; queues the async operation. */
export function deleteSpeakerSync(id: string): void {
  void deleteSpeaker(id);
}
