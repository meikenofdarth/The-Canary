// Auto-detect Mac LAN IP from the Expo dev server.
// Expo Go connects to your Mac at e.g. 172.16.137.77:8081 — we reuse
// that hostname and swap port 8081 → 8000 so the backend is reachable
// from a real Android/iOS device on the same Wi-Fi.
import Constants from "expo-constants";
import { Platform } from "react-native";

function detectApiBase(): string {
  // 1. Hardcoded override via env var
  const envBase = process.env.EXPO_PUBLIC_CANARY_API;
  if (envBase) return envBase;

  // 2. Web (browser) — same machine as the dev server
  if (Platform.OS === "web") return "http://localhost:8000";

  // 3. Native — derive host from Expo's dev server URL
  // Constants.expoConfig.hostUri looks like "172.16.137.77:8081"
  const hostUri =
    (Constants.expoConfig as any)?.hostUri ||
    (Constants.manifest2 as any)?.extra?.expoGo?.developer?.hostUri ||
    (Constants.manifest as any)?.debuggerHost ||
    "";

  if (hostUri) {
    const host = hostUri.split(":")[0];
    if (host && host !== "localhost" && host !== "127.0.0.1") {
      return `http://${host}:8000`;
    }
  }

  // 4. Last-resort fallbacks
  // Android emulator → 10.0.2.2 maps to host's localhost
  if (Platform.OS === "android") return "http://10.0.2.2:8000";
  return "http://localhost:8000";
}

export const API_BASE = detectApiBase();

if (__DEV__) {
  console.log("[canary] API_BASE =", API_BASE);
}

export const ENDPOINTS = {
  status: `${API_BASE}/api/status`,
  users: `${API_BASE}/api/users`,
  command: `${API_BASE}/api/command`,
  enroll: `${API_BASE}/api/enroll`,
  changeWakeword: `${API_BASE}/api/change-wakeword`,
} as const;
