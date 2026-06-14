'use client';

import { useState, useCallback, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { motion, AnimatePresence } from 'framer-motion';
import { useVoice } from '@/lib/use-voice';
import sparrowAnimation from '@/public/sparrow.json';

// Dynamically import Lottie to avoid SSR issues
const Lottie = dynamic(() => import('lottie-react'), { ssr: false });

type AssistantState = 'idle' | 'listening' | 'processing' | 'speaking';

export function LottieAssistant() {
  const [state, setState] = useState<AssistantState>('idle');
  const { isRecording, startRecording, stopRecording } = useVoice();

  const handleInteraction = useCallback(async () => {
    if (state === 'idle') {
      setState('listening');
      await startRecording();
    } else if (state === 'listening') {
      const blob = await stopRecording();
      setState('processing');

      // Simulate API processing delay
      setTimeout(() => {
        setState('speaking');
        // Simulate speaking duration
        setTimeout(() => {
          setState('idle');
        }, 3000);
      }, 1500);
    }
  }, [state, startRecording, stopRecording]);

  // Spacebar hold-to-talk support
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !e.repeat && state === 'idle') {
        e.preventDefault();
        handleInteraction();
      }
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space' && state === 'listening') {
        e.preventDefault();
        handleInteraction();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [state, handleInteraction]);

  return (
    <div className="relative flex items-center justify-center">
      {/* Listening Ripples */}
      <AnimatePresence>
        {state === 'listening' && (
          <>
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="absolute w-40 h-40 rounded-full border-2 border-yellow-400 pointer-events-none"
                initial={{ scale: 1, opacity: 0.6 }}
                animate={{ scale: 2 + i * 0.5, opacity: 0 }}
                exit={{ opacity: 0, transition: { duration: 0.3 } }}
                transition={{
                  repeat: Infinity,
                  duration: 2,
                  delay: i * 0.4,
                  ease: 'easeOut',
                }}
              />
            ))}
          </>
        )}
      </AnimatePresence>

      {/* Processing Pulse */}
      <AnimatePresence>
        {state === 'processing' && (
          <motion.div
            className="absolute w-32 h-32 rounded-full bg-yellow-400 pointer-events-none"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1.2, opacity: 0.2 }}
            exit={{ opacity: 0, transition: { duration: 0.3 } }}
            transition={{
              repeat: Infinity,
              repeatType: 'reverse',
              duration: 0.8,
              ease: 'easeInOut',
            }}
          />
        )}
      </AnimatePresence>

      {/* Speaking Halo */}
      <AnimatePresence>
        {state === 'speaking' && (
          <motion.div
            className="absolute w-32 h-32 rounded-full border-[4px] border-yellow-400 pointer-events-none"
            initial={{ scale: 1, opacity: 0 }}
            animate={{ scale: 1.3, opacity: [0.1, 0.4, 0.1] }}
            exit={{ opacity: 0, transition: { duration: 0.3 } }}
            transition={{
              repeat: Infinity,
              duration: 1,
              ease: 'easeInOut',
            }}
          />
        )}
      </AnimatePresence>

      {/* The Lottie Icon */}
      <motion.div
        className="w-48 h-48 cursor-pointer relative z-10"
        onClick={handleInteraction}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        <Lottie
          animationData={sparrowAnimation}
          loop={true}
          autoplay={true}
          style={{ width: '100%', height: '100%' }}
        />
      </motion.div>
    </div>
  );
}
