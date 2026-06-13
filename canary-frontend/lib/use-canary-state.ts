'use client';

import { useState, useCallback } from 'react';
import { CanaryState } from '@/lib/types';

const THINKING_MESSAGES = ['Let me check that.', 'Thinking...', 'One moment...'];
const SPEAKING_MESSAGES = ["Here's what I found.", 'Found something for you.'];

function pickRandom(arr: string[]): string {
  return arr[Math.floor(Math.random() * arr.length)];
}

export interface UseCanaryStateReturn {
  state: CanaryState;
  startListening: () => void;
  stopListening: () => void;
  startThinking: () => void;
  startSpeaking: () => void;
  goIdle: () => void;
  statusMessage: string;
}

export function useCanaryState(): UseCanaryStateReturn {
  const [state, setState] = useState<CanaryState>('idle');
  const [statusMessage, setStatusMessage] = useState('');

  const startListening = useCallback(() => {
    setState('listening');
    setStatusMessage('Listening...');
  }, []);

  const stopListening = useCallback(() => {
    setState('idle');
    setStatusMessage('');
  }, []);

  const startThinking = useCallback(() => {
    setState('thinking');
    setStatusMessage(pickRandom(THINKING_MESSAGES));
  }, []);

  const startSpeaking = useCallback(() => {
    setState('speaking');
    setStatusMessage(pickRandom(SPEAKING_MESSAGES));
  }, []);

  const goIdle = useCallback(() => {
    setState('idle');
    setStatusMessage('');
  }, []);

  return { state, startListening, stopListening, startThinking, startSpeaking, goIdle, statusMessage };
}
