import AsyncStorage from "@react-native-async-storage/async-storage";
import { fetchBackendUsers, deleteBackendUser, type BackendUser } from "./api";

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
//  UI override helpers (AsyncStorage)
// ─────────────────────────────────────────────────────────────────────────────

async function loadOverrides(): Promise<Record<string, UIOverride>> {
  try {
    const raw = await AsyncStorage.getItem(UI_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

async function saveOverrides(map: Record<string, UIOverride>): Promise<void> {
  await AsyncStorage.setItem(UI_KEY, JSON.stringify(map));
}

function pickIcon(used: Set<string>): string {
  const free = ANIMAL_ICONS.find((i) => !used.has(i));
  return free ?? ANIMAL_ICONS[Math.floor(Math.random() * ANIMAL_ICONS.length)];
}

// ─────────────────────────────────────────────────────────────────────────────
//  Cache
// ─────────────────────────────────────────────────────────────────────────────

async function readCache(): Promise<Speaker[]> {
  try {
    const raw = await AsyncStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

async function writeCache(s: Speaker[]): Promise<void> {
  await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(s));
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
    priority: o?.priority ?? fallbackPriority,
    icon,
    isAccessible: o?.isAccessible ?? false,
    status: "scheduled",
  };
}

// ─────────────────────────────────────────────────────────────────────────────
//  Public API
// ─────────────────────────────────────────────────────────────────────────────

export async function getSpeakers(): Promise<Speaker[]> {
  return await readCache();
}

export async function refreshSpeakers(): Promise<Speaker[]> {
  const overrides = await loadOverrides();
  const used = new Set<string>();
  let fallbackPriority = 5;

  let users: BackendUser[];
  try {
    users = await fetchBackendUsers();
  } catch (e) {
    console.error("[speakers-store] backend fetch failed:", e);
    return await readCache();
  }

  const merged = users.map((u) => {
    const s = toSpeaker(u, overrides, used, fallbackPriority);
    if (overrides[u.name]?.priority === undefined) fallbackPriority = Math.max(1, fallbackPriority - 1);
    return s;
  });

  await writeCache(merged);
  return merged;
}

export async function setSpeakers(speakers: Speaker[]): Promise<void> {
  const overrides = await loadOverrides();
  speakers.forEach((s) => {
    overrides[s.name] = {
      priority: s.priority,
      icon: s.icon,
      isAccessible: s.isAccessible,
    };
  });
  await saveOverrides(overrides);
  await writeCache(speakers);
}

export async function getNormalSpeakers(): Promise<Speaker[]> {
  const speakers = await getSpeakers();
  return speakers
    .filter((s) => !s.isAccessible)
    .sort((a, b) => b.priority - a.priority);
}

export async function getAccessibilitySpeaker(): Promise<Speaker | null> {
  const speakers = await getSpeakers();
  return speakers.find((s) => s.isAccessible) ?? null;
}

export async function addSpeaker(speaker: Speaker): Promise<void> {
  const overrides = await loadOverrides();
  overrides[speaker.name] = {
    priority: speaker.priority,
    icon: speaker.icon || pickIcon(new Set(Object.values(overrides).map((o) => o.icon))),
    isAccessible: speaker.isAccessible,
  };
  await saveOverrides(overrides);
}

export async function changePriority(speakerId: string, newPriority: number): Promise<void> {
  const speakers = await getSpeakers();
  const s = speakers.find((x) => x.id === speakerId);
  if (!s || s.isAccessible) return;
  const overrides = await loadOverrides();
  overrides[s.name] = {
    priority: newPriority,
    icon: overrides[s.name]?.icon ?? s.icon,
    isAccessible: overrides[s.name]?.isAccessible ?? false,
  };
  await saveOverrides(overrides);
  const updated = speakers.map((x) =>
    x.id === speakerId ? { ...x, priority: newPriority } : x,
  );
  await writeCache(updated);
}

export async function deleteSpeaker(id: string): Promise<void> {
  const speakers = await getSpeakers();
  const target = speakers.find((s) => s.id === id);
  if (!target) return;

  try {
    await deleteBackendUser(target.name);
  } catch (e) {
    console.error("[speakers-store] delete failed:", e);
    throw e;
  }

  const overrides = await loadOverrides();
  delete overrides[target.name];
  await saveOverrides(overrides);
  await writeCache(speakers.filter((s) => s.id !== id));
}

export function deleteSpeakerSync(id: string): void {
  void deleteSpeaker(id);
}
