'use client';

import { motion } from 'framer-motion';

const dotVariants = {
  bounce: {
    y: [0, -6, 0],
    transition: {
      duration: 0.6,
      repeat: Infinity,
      ease: 'easeInOut' as const,
    },
  },
};

const containerVariants = {
  animate: {
    transition: {
      staggerChildren: 0.15,
    },
  },
};

export function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -5 }}
      className="flex justify-start"
    >
      <div
        className="px-4 py-3 rounded-2xl rounded-bl-sm border-l-[3px]"
        style={{ backgroundColor: '#FFFDF5', borderLeftColor: '#FFD700' }}
      >
        <motion.div
          className="flex gap-1.5 items-center py-1"
          variants={containerVariants}
          animate="animate"
        >
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: '#FFD700' }}
              variants={dotVariants}
              animate="bounce"
              transition={{ delay: i * 0.15 }}
            />
          ))}
        </motion.div>
      </div>
    </motion.div>
  );
}
