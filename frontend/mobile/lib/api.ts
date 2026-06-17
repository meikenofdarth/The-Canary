import { ENDPOINTS } from "../constants/api";

export interface BackendUser {
  speaker_id: number;
  name: string;
  created_at: string;
  recording_count: number;
  priority?: number | null;
  pitch_mean?: number | null;
  pitch_std?: number | null;
  energy_mean?: number | null;
  speech_rate?: number | null;
  city?: string | null;
  news_country?: string | null;
  favorite_genre?: string | null;
}

export async function fetchBackendUsers(): Promise<BackendUser[]> {
  const res = await fetch(ENDPOINTS.users, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch users: HTTP ${res.status}`);
  const data = await res.json();
  return Array.isArray(data.users) ? data.users : [];
}

export async function deleteBackendUser(name: string): Promise<void> {
  const res = await fetch(`${ENDPOINTS.users}/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to delete: HTTP ${res.status}`);
  }
}

export async function updateUserPriority(name: string, priority: number): Promise<void> {
  const res = await fetch(`${ENDPOINTS.users}/${encodeURIComponent(name)}/priority`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ priority }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to update priority: HTTP ${res.status}`);
  }
}

export interface EnrollPayload {
  name: string;
  city: string;
  newsCountry: string;
  favoriteGenre: string;
  audioBlobs: Blob[]; // exactly 3
}

export async function enrollBackendSpeaker(p: EnrollPayload): Promise<{
  speaker_id: number;
  name: string;
  status: string;
  recording_count: number;
}> {
  if (p.audioBlobs.length < 3) {
    throw new Error("Three audio recordings are required.");
  }
  const fd = new FormData();
  fd.append("name", p.name);
  fd.append("city", p.city);
  fd.append("news_country", p.newsCountry);
  fd.append("favorite_genre", p.favoriteGenre);
  p.audioBlobs.slice(0, 3).forEach((b, i) => {
    fd.append("audio_files", b, `sample_${i + 1}.webm`);
  });

  const res = await fetch(ENDPOINTS.enroll, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Enrollment failed: HTTP ${res.status}`);
  }
  return res.json();
}

export async function changeBackendWakeword(audioBlobs: Blob[]): Promise<{
  word: string;
  variants_generated: number;
  transcriptions: string[];
}> {
  if (audioBlobs.length < 3) {
    throw new Error("Three wake-word recordings are required.");
  }
  const fd = new FormData();
  audioBlobs.slice(0, 3).forEach((b, i) => {
    fd.append("audio_files", b, `wakeword_${i + 1}.webm`);
  });

  const res = await fetch(ENDPOINTS.changeWakeword, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Wakeword change failed: HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchSystemStatus(): Promise<{
  active_wakeword: string;
  enrolled_users: number;
  db_exists: boolean;
  status: string;
}> {
  const res = await fetch(ENDPOINTS.status, { cache: "no-store" });
  if (!res.ok) throw new Error(`Status fetch failed: HTTP ${res.status}`);
  return res.json();
}
