'use client';

import { useRef, useEffect } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Message } from '@/lib/types';
import { MessageBubble } from './message-bubble';
import { TypingIndicator } from './typing-indicator';

interface ConversationPanelProps {
  messages: Message[];
  isThinking: boolean;
}

export function ConversationPanel({ messages, isThinking }: ConversationPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4" style={{ scrollbarWidth: 'thin', scrollbarColor: '#E5DDD0 transparent' }}>
      {messages.length === 0 && !isThinking && (
        <div className="flex flex-col items-center justify-center h-full text-center opacity-60">
          <p className="text-lg font-medium" style={{ color: '#2D2D2D' }}>
            Tap the bird to start talking
          </p>
          <p className="text-sm mt-1" style={{ color: '#9CA3AF' }}>
            or hold spacebar to speak
          </p>
        </div>
      )}

      <AnimatePresence mode="popLayout">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </AnimatePresence>

      {isThinking && <TypingIndicator />}

      <div ref={bottomRef} />
    </div>
  );
}
