'use client';

import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import { Message } from '@/lib/types';

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const timeStr = message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={`max-w-[75%] px-4 py-3 ${
          isUser
            ? 'rounded-2xl rounded-br-sm'
            : 'rounded-2xl rounded-bl-sm border-l-[3px]'
        }`}
        style={
          isUser
            ? { backgroundColor: '#2D2D2D', color: '#FFFFFF' }
            : { backgroundColor: '#FFFDF5', color: '#2D2D2D', borderLeftColor: '#FFD700' }
        }
      >
        {isUser ? (
          <p className="text-sm leading-relaxed">{message.content}</p>
        ) : (
          <div className="canary-markdown text-sm leading-relaxed">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}
        <p
          className="text-[11px] mt-1.5 opacity-50"
          style={{ color: isUser ? '#FFFFFF' : '#9CA3AF' }}
        >
          {timeStr}
        </p>
      </div>
    </motion.div>
  );
}
