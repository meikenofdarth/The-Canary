'use client';

import { motion, Variants } from 'framer-motion';
import { useEffect, useState, useCallback } from 'react';
import { CanaryState } from '@/lib/types';

interface CanaryBirdProps {
  state: CanaryState;
  onClick: () => void;
  className?: string;
}

/* ── Animation Variants ─────────────────────────────────────────────── */

const bodyVariants: Variants = {
  idle: {
    scale: [1, 1.02, 1],
    transition: { repeat: Infinity, duration: 3, ease: 'easeInOut' },
  },
  listening: {
    scale: 1.04,
    transition: { type: 'spring', stiffness: 200, damping: 15 },
  },
  thinking: {
    y: [0, -4, 0],
    transition: { duration: 0.5, ease: 'easeOut' },
  },
  speaking: {
    scale: 1.02,
    transition: { type: 'spring', stiffness: 150 },
  },
};

const headVariants: Variants = {
  idle: { rotate: 0, transition: { type: 'spring', stiffness: 100 } },
  listening: { rotate: -10, transition: { type: 'spring', stiffness: 200, damping: 12 } },
  thinking: {
    rotate: [0, 8, -5, 0],
    transition: { duration: 1.2, ease: 'easeInOut' },
  },
  speaking: { rotate: 0, transition: { type: 'spring', stiffness: 100 } },
};

const wingVariants: Variants = {
  idle: {
    rotate: 0,
    transition: { duration: 0.5 },
  },
  listening: { rotate: -3, transition: { duration: 0.3 } },
  thinking: {
    rotate: [0, -15, 0, -10, 0],
    transition: { duration: 0.8, ease: 'easeInOut' },
  },
  speaking: {
    rotate: [0, -5, 0],
    transition: { repeat: Infinity, duration: 1.5, ease: 'easeInOut' },
  },
};

const tailVariants: Variants = {
  idle: {
    rotate: [0, 3, 0, -2, 0],
    transition: { repeat: Infinity, duration: 4, ease: 'easeInOut' },
  },
  listening: { rotate: 5, transition: { duration: 0.3 } },
  thinking: { rotate: -3, transition: { duration: 0.3 } },
  speaking: {
    rotate: [0, 4, -3, 0],
    transition: { repeat: Infinity, duration: 1.2 },
  },
};

const beakTopVariants: Variants = {
  idle: { rotate: 0 },
  listening: { rotate: 0 },
  thinking: { rotate: 0 },
  speaking: {
    rotate: [0, -8, 0],
    transition: { repeat: Infinity, duration: 0.4, ease: 'easeInOut' },
  },
};

const beakBottomVariants: Variants = {
  idle: { rotate: 0 },
  listening: { rotate: 0 },
  thinking: { rotate: 0 },
  speaking: {
    rotate: [0, 5, 0],
    transition: { repeat: Infinity, duration: 0.4, ease: 'easeInOut' },
  },
};

/* ── Ripple for listening state ─────────────────────────────────────── */

function ListeningRipples() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <motion.circle
          key={i}
          cx="100"
          cy="105"
          r="50"
          fill="none"
          stroke="#FFD700"
          strokeWidth="1.5"
          initial={{ scale: 0.8, opacity: 0.5 }}
          animate={{ scale: 1.6 + i * 0.3, opacity: 0 }}
          transition={{
            repeat: Infinity,
            duration: 2,
            delay: i * 0.5,
            ease: 'easeOut',
          }}
        />
      ))}
    </>
  );
}

/* ── Main Bird Component ────────────────────────────────────────────── */

export function CanaryBird({ state, onClick, className = '' }: CanaryBirdProps) {
  const [isBlinking, setIsBlinking] = useState(false);

  // Random blinking every 3-8 seconds
  const scheduleBlink = useCallback(() => {
    const delay = 3000 + Math.random() * 5000;
    const timeout = setTimeout(() => {
      setIsBlinking(true);
      setTimeout(() => {
        setIsBlinking(false);
        scheduleBlink();
      }, 150);
    }, delay);
    return timeout;
  }, []);

  useEffect(() => {
    const timeout = scheduleBlink();
    return () => clearTimeout(timeout);
  }, [scheduleBlink]);

  return (
    <motion.svg
      viewBox="0 0 200 200"
      className={`cursor-pointer select-none ${className}`}
      onClick={onClick}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 300, damping: 20 }}
    >
      {/* Listening ripples */}
      {state === 'listening' && <ListeningRipples />}

      {/* ── Tail feathers ── */}
      <motion.g
        variants={tailVariants}
        animate={state}
        style={{ originX: '90px', originY: '140px' }}
      >
        <ellipse cx="72" cy="142" rx="12" ry="6" fill="#F5C842" transform="rotate(-25, 72, 142)" />
        <ellipse cx="68" cy="138" rx="10" ry="5" fill="#FFD700" transform="rotate(-35, 68, 138)" />
        <ellipse cx="75" cy="146" rx="11" ry="5" fill="#E6B800" transform="rotate(-15, 75, 146)" />
      </motion.g>

      {/* ── Body ── */}
      <motion.g variants={bodyVariants} animate={state}>
        {/* Body shadow for depth */}
        <ellipse cx="102" cy="128" rx="36" ry="32" fill="#E6B800" opacity="0.4" />
        {/* Main body */}
        <ellipse cx="100" cy="125" rx="35" ry="30" fill="#FFD700" />
        {/* Belly highlight */}
        <ellipse cx="100" cy="130" rx="22" ry="18" fill="#FFE44D" opacity="0.6" />
      </motion.g>

      {/* ── Wing ── */}
      <motion.g
        variants={wingVariants}
        animate={state}
        style={{ originX: '120px', originY: '115px' }}
      >
        <ellipse cx="128" cy="120" rx="18" ry="12" fill="#F5C842" transform="rotate(15, 128, 120)" />
        <ellipse cx="130" cy="118" rx="14" ry="9" fill="#FFD700" transform="rotate(15, 130, 118)" />
      </motion.g>

      {/* ── Head ── */}
      <motion.g
        variants={headVariants}
        animate={state}
        style={{ originX: '100px', originY: '90px' }}
      >
        {/* Head shape */}
        <circle cx="100" cy="85" r="22" fill="#FFD700" />
        {/* Cheek blush */}
        <circle cx="113" cy="90" r="5" fill="#FFAA00" opacity="0.25" />

        {/* Eye */}
        <motion.ellipse
          cx="108"
          cy="82"
          rx="3.5"
          ry={isBlinking ? 0.5 : state === 'listening' ? 4 : 3.5}
          fill="#2D2D2D"
          animate={{
            ry: isBlinking ? 0.5 : state === 'listening' ? 4 : 3.5,
          }}
          transition={{ duration: 0.1 }}
        />
        {/* Eye highlight */}
        {!isBlinking && (
          <circle cx="109.5" cy="80.5" r="1.2" fill="#FFFFFF" opacity="0.8" />
        )}

        {/* ── Beak ── */}
        <motion.g style={{ originX: '120px', originY: '87px' }}>
          {/* Top beak */}
          <motion.path
            d="M118 85 L132 87 L118 89"
            fill="#FF8C00"
            variants={beakTopVariants}
            animate={state}
            style={{ originX: '118px', originY: '87px' }}
          />
          {/* Bottom beak */}
          <motion.path
            d="M118 89 L128 90 L118 92"
            fill="#E07000"
            variants={beakBottomVariants}
            animate={state}
            style={{ originX: '118px', originY: '90px' }}
          />
        </motion.g>

        {/* Small crown feather tuft */}
        <ellipse cx="95" cy="64" rx="3" ry="7" fill="#FFD700" transform="rotate(-10, 95, 64)" />
        <ellipse cx="100" cy="63" rx="2.5" ry="6" fill="#F5C842" transform="rotate(5, 100, 63)" />
      </motion.g>

      {/* ── Feet ── */}
      <g>
        {/* Left foot */}
        <line x1="90" y1="153" x2="85" y2="165" stroke="#8B7355" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="85" y1="165" x2="80" y2="168" stroke="#8B7355" strokeWidth="2" strokeLinecap="round" />
        <line x1="85" y1="165" x2="88" y2="169" stroke="#8B7355" strokeWidth="2" strokeLinecap="round" />
        {/* Right foot */}
        <line x1="110" y1="153" x2="115" y2="165" stroke="#8B7355" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="115" y1="165" x2="112" y2="169" stroke="#8B7355" strokeWidth="2" strokeLinecap="round" />
        <line x1="115" y1="165" x2="120" y2="168" stroke="#8B7355" strokeWidth="2" strokeLinecap="round" />
      </g>

      {/* ── Perch/branch ── */}
      <line x1="65" y1="168" x2="140" y2="168" stroke="#8B7355" strokeWidth="3" strokeLinecap="round" />
    </motion.svg>
  );
}
