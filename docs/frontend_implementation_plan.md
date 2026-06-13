# Canary Frontend — Implementation Plan

Build a warm, bird-themed frontend for the Canary AI voice assistant using Next.js + TypeScript + Tailwind + shadcn/ui + Framer Motion.

## User Review Required

> [!IMPORTANT]
> **Project Location**: The frontend will be created at `/Users/sanchitkumardogra/kaam/Samsung Ennovatex /canary-frontend/`. This keeps it inside the existing project but separate from the Python backend. Is this acceptable?

> [!IMPORTANT]
> **Backend Integration**: The current execution engine runs as a Python CLI. For the frontend demo, I'll create a lightweight Next.js API route that shells out to the Python execution engine (or mocks the responses for demo purposes). We can wire up real WebSocket streaming later. Which do you prefer for now?

## Open Questions

> [!IMPORTANT]
> **Voice Input**: The Web Speech API (`webkitSpeechRecognition`) works well in Chrome but has limited cross-browser support. For the demo, should I use the browser's built-in speech recognition, or should the frontend just send audio blobs to the Python backend (Hemang's Whisper pipeline)?

> [!IMPORTANT]
> **Scope for Demo**: Should this be a fully functional end-to-end demo (frontend → backend → APIs → TTS response), or is a polished UI with mocked responses sufficient for now?

---

## Proposed Changes

### Design System & Visual Identity

The entire app is built around the Canary bird metaphor — warm yellows, cream backgrounds, charcoal text, natural tones. No dark mode. No neon. No sci-fi.

| Token | Value | Usage |
|-------|-------|-------|
| `canary-yellow` | `#FFD700` / `#FFC107` | Primary accent, bird color |
| `cream` | `#FFF8E7` | Page background |
| `warm-white` | `#FFFDF5` | Card backgrounds |
| `charcoal` | `#2D2D2D` | Primary text |
| `soft-gray` | `#9CA3AF` | Secondary text |
| `feather-gold` | `#F5C842` | Hover / active states |
| `nest-brown` | `#8B7355` | Subtle borders |

Typography: **Inter** for body, clean and modern.

---

### Component Architecture

#### 1. `CanaryBird` — The Core Character (SVG + Framer Motion)

The bird is **not** a static image. It is a multi-part SVG with independently animated segments:

- **Body**: Slight breathing scale animation (idle)
- **Head**: Tilts toward sound source (listening)
- **Eye**: Blinks every 3-5 seconds randomly (idle), widens (listening)
- **Beak**: Opens/closes rhythmically (speaking)
- **Wing**: Tiny flutter on task completion
- **Tail feathers**: Gentle sway

**State machine:**
```
IDLE → LISTENING → THINKING → SPEAKING → IDLE
```

Each state triggers different Framer Motion `variants` on the SVG sub-elements. Transitions are spring-based with natural easing.

#### 2. `ConversationPanel` — Chat History

- Clean message list, scrollable
- **User messages**: Right-aligned, minimal pill shape, charcoal background with white text
- **Canary messages**: Left-aligned, warm cream background, charcoal text, subtle left border in canary-yellow
- Supports markdown rendering (via `react-markdown`)
- Smooth scroll-to-bottom on new messages
- Typing indicator shows the bird "thinking" with animated dots

#### 3. `VoiceInput` — Natural Voice Interaction

- **Tap the bird** to start listening (primary interaction)
- **Hold spacebar** as alternative
- No giant microphone button
- When listening: soft concentric ripples emanate from the bird
- When not listening: bird returns to idle
- Small waveform visualization near the bird during active recording

#### 4. `StatusBar` — Friendly Status Messages

Instead of generic "Processing...", use personality-driven messages:
- "Listening..." (bird tilts head)
- "Let me check that." (bird hops)
- "Found something for you." (bird flutters wings)
- "Here you go." (bird settles)

#### 5. `Header` — Minimal Branding

- "Canary" wordmark in warm charcoal
- Small bird silhouette icon
- No navigation clutter

---

### File Structure

```
canary-frontend/
├── app/
│   ├── layout.tsx          # Root layout with fonts, metadata
│   ├── page.tsx            # Main conversation page
│   ├── globals.css         # Tailwind config + custom tokens
│   └── api/
│       └── chat/
│           └── route.ts    # API route to bridge to Python backend
├── components/
│   ├── canary-bird.tsx     # Animated SVG bird component
│   ├── conversation-panel.tsx
│   ├── message-bubble.tsx
│   ├── voice-input.tsx
│   ├── status-bar.tsx
│   ├── header.tsx
│   └── typing-indicator.tsx
├── lib/
│   ├── use-voice.ts        # Custom hook for voice recording
│   ├── use-canary-state.ts # State machine for bird animations
│   └── types.ts            # Shared TypeScript types
├── public/
│   └── fonts/
├── tailwind.config.ts
├── package.json
└── tsconfig.json
```

---

### Animation Strategy (Framer Motion)

All bird animations use Framer Motion `variants` with `transition` configs:

```typescript
// Example: Bird breathing (idle)
const bodyVariants = {
  idle: {
    scale: [1, 1.02, 1],
    transition: { repeat: Infinity, duration: 3, ease: "easeInOut" }
  },
  listening: {
    scale: 1.05,
    transition: { type: "spring", stiffness: 200 }
  }
}
```

Key principles:
- Spring animations for organic feel
- Stagger children for sequential body part movement
- `AnimatePresence` for message enter/exit
- No `keyframes` longer than 4 seconds
- Random intervals for blinking (using `useEffect` + `setTimeout`)

---

### Voice Input Implementation

```
User taps bird → Start recording (MediaRecorder API)
→ Bird transitions to LISTENING state
→ Concentric ripples animate outward
→ User taps again or releases spacebar → Stop recording
→ Bird transitions to THINKING state
→ Audio blob sent to API route
→ API route forwards to Python backend
→ Response received
→ Bird transitions to SPEAKING state
→ Message appears in conversation
→ Bird transitions back to IDLE
```

---

## Verification Plan

### Manual Verification
- Visual inspection of all four bird states (idle, listening, thinking, speaking)
- Test voice input in Chrome (Web Speech API)
- Responsive layout check on desktop and mobile viewport
- Verify conversation scroll behavior
- Confirm Tailwind theme tokens render correctly
