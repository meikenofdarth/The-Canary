// Update this to your machine's local IP when testing on a real device via Expo Go
// For Android emulator: http://10.0.2.2:8000
// For iOS simulator: http://localhost:8000
// For physical device: http://<your-machine-IP>:8000
export const API_BASE = "http://localhost:8000";

export const ENDPOINTS = {
  status: `${API_BASE}/api/status`,
  users: `${API_BASE}/api/users`,
  command: `${API_BASE}/api/command`,
  enroll: `${API_BASE}/api/enroll`,
  changeWakeword: `${API_BASE}/api/change-wakeword`,
} as const;
