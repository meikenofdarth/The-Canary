'use client';

import { AnimatePresence, motion } from 'framer-motion';

interface StatusBarProps {
  message: string;
}

export function StatusBar({ message }: StatusBarProps) {
  return (
    <div className="h-6 mt-3">
      <AnimatePresence mode="wait">
        {message && (
          <motion.p
            key={message}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            className="text-sm italic text-center"
            style={{ color: '#9CA3AF' }}
          >
            {message}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
