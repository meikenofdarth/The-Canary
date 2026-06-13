export type CanaryState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface Message {
  id: string;
  role: 'user' | 'canary';
  content: string;
  timestamp: Date;
}

export interface VoiceSession {
  isRecording: boolean;
  audioBlob: Blob | null;
}
