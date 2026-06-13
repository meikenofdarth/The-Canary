'use client';

import { useState, useCallback, useEffect } from 'react';
import { Header } from '@/components/header';
import { CanaryBird } from '@/components/canary-bird';
import { ConversationPanel } from '@/components/conversation-panel';
import { StatusBar } from '@/components/status-bar';
import { useCanaryState } from '@/lib/use-canary-state';
import { useVoice } from '@/lib/use-voice';
import { Message } from '@/lib/types';

/* ── Mock responses for the UI demo ─────────────────────────────────── */
const MOCK_RESPONSES: Record<string, string> = {
  weather: "The current weather in **Bengaluru** is 22 degrees Celsius with Heavy Rain. Carry an umbrella today!",
  news: "Here is the latest news for **Delhi**: Supreme Court issues new guidelines on environmental protection measures across major cities.",
  music: "Playing **Shape of You** by Ed Sheeran. Enjoy the music!",
  hello: "Hello! I'm Canary, your voice companion. How can I help you today?",
  default: "I heard you! I can help with **weather**, **news**, and **music**. Just ask me something like:\n\n- \"What's the weather in Mumbai?\"\n- \"Tell me the latest news\"\n- \"Play some music\"",
};

function getMockResponse(input: string): string {
  const lower = input.toLowerCase();
  if (lower.includes('weather')) return MOCK_RESPONSES.weather;
  if (lower.includes('news')) return MOCK_RESPONSES.news;
  if (lower.includes('music') || lower.includes('song') || lower.includes('play')) return MOCK_RESPONSES.music;
  if (lower.includes('hello') || lower.includes('hi') || lower.includes('hey')) return MOCK_RESPONSES.hello;
  return MOCK_RESPONSES.default;
}

/* ── Main Page ──────────────────────────────────────────────────────── */
export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const { state, startListening, startThinking, startSpeaking, goIdle, statusMessage } = useCanaryState();
  const { isRecording, startRecording, stopRecording } = useVoice();

  /* Handle bird tap — toggle listening */
  const handleBirdClick = useCallback(async () => {
    if (state === 'idle') {
      startListening();
      await startRecording();
    } else if (state === 'listening') {
      const blob = await stopRecording();
      startThinking();

      /* Simulate user message from voice (in real app, this would go through Whisper) */
      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: 'What is the weather in Bengaluru?',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);

      /* Simulate API response delay */
      setTimeout(() => {
        startSpeaking();
        const canaryMsg: Message = {
          id: `canary-${Date.now()}`,
          role: 'canary',
          content: getMockResponse(userMsg.content),
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, canaryMsg]);

        /* Return to idle after "speaking" */
        setTimeout(() => goIdle(), 3000);
      }, 1500);
    }
  }, [state, startListening, startRecording, stopRecording, startThinking, startSpeaking, goIdle]);

  /* Spacebar hold-to-talk */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !e.repeat && state === 'idle') {
        e.preventDefault();
        handleBirdClick();
      }
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space' && state === 'listening') {
        e.preventDefault();
        handleBirdClick();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [state, handleBirdClick]);

  /* Text input for testing without mic */
  const [textInput, setTextInput] = useState('');

  const handleTextSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: textInput.trim(),
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setTextInput('');

    startThinking();

    setTimeout(() => {
      startSpeaking();
      const canaryMsg: Message = {
        id: `canary-${Date.now()}`,
        role: 'canary',
        content: getMockResponse(userMsg.content),
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, canaryMsg]);
      setTimeout(() => goIdle(), 3000);
    }, 1500);
  }, [textInput, startThinking, startSpeaking, goIdle]);

  return (
    <div className="flex flex-col h-screen" style={{ backgroundColor: '#FFF8E7' }}>
      <Header />

      {/* Main content area */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">

        {/* Bird panel — left side on desktop, top on mobile */}
        <div className="flex flex-col items-center justify-center p-6 md:p-10 md:w-[340px] shrink-0">
          <CanaryBird
            state={state}
            onClick={handleBirdClick}
            className="w-40 h-40 md:w-52 md:h-52"
          />
          <StatusBar message={statusMessage} />
          <p className="text-xs mt-3 text-center" style={{ color: '#9CA3AF' }}>
            {state === 'idle' ? 'Tap the bird or hold spacebar' : ''}
          </p>
        </div>

        {/* Conversation panel — right side on desktop, bottom on mobile */}
        <div className="flex-1 flex flex-col min-h-0 border-l" style={{ borderColor: '#F0E6D3' }}>
          <ConversationPanel
            messages={messages}
            isThinking={state === 'thinking'}
          />

          {/* Text input bar (for testing without mic) */}
          <form
            onSubmit={handleTextSubmit}
            className="flex items-center gap-3 px-4 py-3 border-t"
            style={{ borderColor: '#F0E6D3', backgroundColor: '#FFFDF5' }}
          >
            <input
              type="text"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              placeholder="Type a message..."
              className="flex-1 px-4 py-2.5 rounded-xl text-sm outline-none"
              style={{
                backgroundColor: '#FFF8E7',
                color: '#2D2D2D',
                border: '1px solid #F0E6D3',
              }}
            />
            <button
              type="submit"
              disabled={!textInput.trim()}
              className="px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 disabled:opacity-40"
              style={{
                backgroundColor: '#FFD700',
                color: '#2D2D2D',
              }}
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
