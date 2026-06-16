'use client';

import { useState, useRef, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { Mic, MicOff, Play, Pause, Square, Trash2, ArrowLeft, CheckCircle2, X } from 'lucide-react';
import { enrollBackendSpeaker } from '@/lib/api';
import { addSpeaker, refreshSpeakers, deleteSpeaker, getSpeakers, getNormalSpeakers } from '@/lib/speakers-store';

interface RemovalModalProps {
  isOpen: boolean;
  onClose: () => void;
  formData: { needsAccessibility: boolean };
  onConfirm: (speakerId: string) => void;
  speakers: any[];
}

function RemovalModal({ isOpen, onClose, formData, onConfirm, speakers }: RemovalModalProps) {
  const [selectedSpeaker, setSelectedSpeaker] = useState<string | null>(null);

  if (!isOpen) return null;

  const filteredSpeakers = formData.needsAccessibility 
    ? speakers.filter(s => s.isAccessible) 
    : speakers.filter(s => !s.isAccessible);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-card rounded-lg max-w-md w-full p-6 border border-border shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-foreground">
            {formData.needsAccessibility ? 'Accessibility Voice Limit' : 'Speaker Limit Reached'}
          </h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="text-muted-foreground mb-6">
          {formData.needsAccessibility 
            ? 'Only one accessibility-enabled speaker is allowed. Which existing speaker would you like to replace?' 
            : 'You have reached the maximum of 5 healthy speakers. Which speaker would you like to remove to add this new one?'}
        </p>
        
        <div className="space-y-2 max-h-64 overflow-y-auto mb-6">
          {filteredSpeakers.map(speaker => (
            <button
              key={speaker.id}
              onClick={() => setSelectedSpeaker(speaker.id)}
              className={`w-full text-left p-3 rounded-lg border transition-all ${
                selectedSpeaker === speaker.id
                  ? 'border-primary bg-primary/10'
                  : 'border-border hover:bg-secondary/50'
              }`}
            >
              <p className="font-medium text-foreground">{speaker.name}</p>
              <p className="text-sm text-muted-foreground">
                {speaker.isAccessible ? 'Accessibility enabled' : `Priority ${speaker.priority}`}
              </p>
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-border px-4 py-2 font-semibold text-foreground hover:bg-secondary"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              if (selectedSpeaker) {
                onConfirm(selectedSpeaker);
              }
            }}
            disabled={!selectedSpeaker}
            className="flex-1 rounded-lg bg-primary px-4 py-2 font-semibold text-primary-foreground hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {formData.needsAccessibility ? 'Replace & Continue' : 'Remove & Add New'}
          </button>
        </div>
      </div>
    </div>
  );
}

const MUSIC_GENRES = [
  'Pop', 'Rock', 'Jazz', 'Classical', 'Hip-Hop', 'Electronic', 'Country', 'R&B', 'Indie', 'Folk', 'Metal', 'Latin', 'Other'
];

const VOICE_SCRIPTS = [
  {
    id: 1,
    label: 'Script 1 — Natural Speech',
    instruction: 'Speak clearly and naturally at your normal pace.',
    text: 'Canary, my name is [your name]. Today I am recording my voice profile for speaker identification. I am speaking naturally and clearly so the system can learn the characteristics of my voice.',
  },
  {
    id: 2,
    label: 'Script 2 — Varied Pace',
    instruction: 'Start a little faster, then slow down — vary your rhythm.',
    text: 'Canary, I would like to test different speaking styles. Sometimes I speak quickly, sometimes slowly, and sometimes with more excitement. This recording helps capture those variations.',
  },
  {
    id: 3,
    label: 'Script 3 — Questions & Commands',
    instruction: 'Use natural question and command intonation.',
    text: 'Canary, can you tell me the weather today? Canary, please play some relaxing music. Canary, remind me about my meeting tomorrow morning.',
  },
];

const ACCESSIBILITY_QUESTIONS = [
  "How was your day today?",
  "What have you been working on?",
  "What's your favorite memory?"
];

export default function AddSpeakerPage() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [allSpeakers, setAllSpeakers] = useState<any[]>([]);
  
  // Form Data
  const [formData, setFormData] = useState({
    name: '',
    city: '',
    country: '',
    musicGenre: '',
    priority: 1,
    needsAccessibility: false,
  });

  // Recording State
  const [selectedScript, setSelectedScript] = useState<number | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingType, setRecordingType] = useState<'standard' | 'accessibility' | null>(null);
  const [standardRecordings, setStandardRecordings] = useState<{ [key: number]: Blob }>({});
  const [accessibilityRecordings, setAccessibilityRecordings] = useState<Blob[]>([]);
  const [currentAccessibilityQuestion, setCurrentAccessibilityQuestion] = useState(0);
  const [recordingTime, setRecordingTime] = useState(0);
  const [showRemovalModal, setShowRemovalModal] = useState(false);
  const [speakerToRemove, setSpeakerToRemove] = useState<string | null>(null);
  const [showAddVoiceConfirm, setShowAddVoiceConfirm] = useState(false);
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Process script with speaker name
  const script = selectedScript ? VOICE_SCRIPTS[selectedScript - 1] : null;
  const processedScript = script
    ? script.text.replace('[your name]', formData.name || 'your name')
    : '';

  const startRecording = async (type: 'standard' | 'accessibility') => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        
        if (type === 'standard' && selectedScript) {
          setStandardRecordings(prev => ({
            ...prev,
            [selectedScript]: blob
          }));
        } else if (type === 'accessibility') {
          const newRecordings = [...accessibilityRecordings];
          newRecordings[currentAccessibilityQuestion] = blob;
          setAccessibilityRecordings(newRecordings);
        }
        
        setIsRecording(false);
        setRecordingType(null);
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingType(type);
      setRecordingTime(0);

      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } catch (error) {
      console.error('Recording error:', error);
      alert('Unable to access microphone. Please check permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    }
  };

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playingBlob, setPlayingBlob] = useState<Blob | null>(null);
  const [isPaused, setIsPaused] = useState(false);

  const playRecording = (blob: Blob) => {
    // Stop current playback if any
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      audioRef.current = null;
    }
    if (playingBlob === blob && !isPaused) {
      // Same blob — was playing, now stopped
      setPlayingBlob(null);
      setIsPaused(false);
      return;
    }
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audioRef.current = audio;
    setPlayingBlob(blob);
    setIsPaused(false);
    audio.play();
    audio.onended = () => {
      URL.revokeObjectURL(url);
      setPlayingBlob(null);
      setIsPaused(false);
      audioRef.current = null;
    };
  };

  const pauseRecording = () => {
    if (audioRef.current && !audioRef.current.paused) {
      audioRef.current.pause();
      setIsPaused(true);
    } else if (audioRef.current && audioRef.current.paused) {
      audioRef.current.play();
      setIsPaused(false);
    }
  };

  const stopRecordingPlayback = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      audioRef.current = null;
    }
    setPlayingBlob(null);
    setIsPaused(false);
  };

  const PlaybackControls = ({ blob }: { blob: Blob }) => {
    const isThisPlaying = playingBlob === blob && !isPaused;
    const isThisPaused = playingBlob === blob && isPaused;
    return (
      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => isThisPlaying ? pauseRecording() : (isThisPaused ? pauseRecording() : playRecording(blob))}
          className="inline-flex items-center justify-center rounded-lg border border-border p-2 text-foreground hover:bg-secondary transition-colors"
          aria-label={isThisPlaying ? 'Pause' : 'Play'}
        >
          {isThisPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </button>
        {(isThisPlaying || isThisPaused) && (
          <button
            type="button"
            onClick={stopRecordingPlayback}
            className="inline-flex items-center justify-center rounded-lg border border-border p-2 text-foreground hover:bg-secondary transition-colors"
            aria-label="Stop"
          >
            <Square className="h-4 w-4" />
          </button>
        )}
      </div>
    );
  };

  const [submitError, setSubmitError] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError('');

    if (!formData.name || !formData.city || !formData.country || !formData.musicGenre) {
      setSubmitError('Please fill all required fields');
      return;
    }

    // Check if all 3 scripts have recordings for normal mode
    if (!formData.needsAccessibility) {
      const hasAllRecordings = VOICE_SCRIPTS.every(script => standardRecordings[script.id]);
      if (!hasAllRecordings) {
        setSubmitError('Please record all 3 scripts before submitting');
        return;
      }

      // Capacity check: max 5 healthy speakers
      const existingSpeakers = getSpeakers();
      setAllSpeakers(existingSpeakers);
      const healthySpeakers = existingSpeakers.filter(s => !s.isAccessible);

      if (healthySpeakers.length >= 5) {
        setShowRemovalModal(true);
        return;
      }

      setShowAddVoiceConfirm(true);
      return;
    }

    if (formData.needsAccessibility && accessibilityRecordings.length !== ACCESSIBILITY_QUESTIONS.length) {
      setSubmitError('Please complete all accessibility recordings');
      return;
    }

    // Only 1 accessibility speaker allowed
    const existingSpeakers = getSpeakers();
    setAllSpeakers(existingSpeakers);
    const accessibilitySpeakers = existingSpeakers.filter(s => s.isAccessible);

    if (accessibilitySpeakers.length > 0) {
      setSpeakerToRemove(accessibilitySpeakers[0].id);
      setShowRemovalModal(true);
      return;
    }

    completeAddSpeaker();
  };

  const completeAddSpeaker = async (speakerIdToRemove?: string) => {
    setIsSubmitting(true);
    setSubmitError('');

    try {
      // 1. Delete the chosen-to-replace speaker first (calls DELETE /api/users/{name})
      if (speakerIdToRemove) {
        await deleteSpeaker(speakerIdToRemove);
      }

      // 2. Collect the 3 audio blobs (standard or accessibility)
      const blobs: Blob[] = formData.needsAccessibility
        ? accessibilityRecordings.slice(0, 3)
        : VOICE_SCRIPTS.map(s => standardRecordings[s.id]);

      if (blobs.length < 3 || blobs.some(b => !b)) {
        throw new Error('Three voice recordings are required.');
      }

      // 3. Hit the real backend
      await enrollBackendSpeaker({
        name: formData.name,
        city: formData.city,
        newsCountry: formData.country,
        favoriteGenre: formData.musicGenre,
        audioBlobs: blobs,
      });

      // 4. Persist UI-only fields (priority + animal icon + accessibility flag)
      const ANIMAL_EMOJIS = ['🦁', '🦉', '🦊', '🦅', '🐺', '🐻', '🐼', '🦝', '🦌', '🦆'];
      const normalSpeakers = getNormalSpeakers();
      const nextPriority = formData.needsAccessibility
        ? 0
        : Math.max(1, Math.min(5, normalSpeakers.length + 1));

      addSpeaker({
        id: '0', // backend will assign real id; refresh will replace
        name: formData.name,
        city: formData.city,
        country: formData.country,
        musicGenre: formData.musicGenre,
        priority: nextPriority,
        isAccessible: formData.needsAccessibility,
        icon: ANIMAL_EMOJIS[Math.floor(Math.random() * ANIMAL_EMOJIS.length)],
      });

      // 5. Refresh from backend so the dashboard list updates
      await refreshSpeakers();

      setShowRemovalModal(false);
      setShowAddVoiceConfirm(false);
      startTransition(() => {
        router.push('/dashboard');
      });
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Enrollment failed.');
      setShowAddVoiceConfirm(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAccessibilityChange = (checked: boolean) => {
    setFormData({ ...formData, needsAccessibility: checked });
    setSelectedScript(null);
    setStandardRecordings({});
    setCurrentAccessibilityQuestion(0);
    setAccessibilityRecordings([]);
  };

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Register New Speaker</h1>
            <p className="mt-2 text-muted-foreground">Add and manage speaker profiles with voice samples</p>
          </div>
          <button
            onClick={() => startTransition(() => router.push('/dashboard'))}
            disabled={isPending}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-secondary disabled:opacity-60"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column - Form */}
          <div>
            <form onSubmit={handleFormSubmit} className="space-y-6 rounded-lg border border-border bg-card p-6 sticky top-6">
              
              {/* Speaker Name */}
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Speaker Name *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Enter speaker name"
                  className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
                />
              </div>

              {/* City */}
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  City - Where do you live? *
                </label>
                <input
                  type="text"
                  value={formData.city}
                  onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                  placeholder="Enter your city"
                  className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
                />
              </div>

              {/* Country */}
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Country - Which country are you from? *
                </label>
                <input
                  type="text"
                  value={formData.country}
                  onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                  placeholder="Enter your country"
                  className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
                />
              </div>

              {/* Music Genre */}
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Favorite Music Genre *
                </label>
                <select
                  value={formData.musicGenre}
                  onChange={(e) => setFormData({ ...formData, musicGenre: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground focus:border-primary focus:outline-none"
                >
                  <option value="">Select a genre</option>
                  {MUSIC_GENRES.map(genre => (
                    <option key={genre} value={genre}>{genre}</option>
                  ))}
                </select>
              </div>

  {/* Priority - Hidden for accessibility mode */}
  {!formData.needsAccessibility && (
    <div>
      <label className="block text-sm font-semibold text-foreground mb-2">
        Speaker Priority *
      </label>
      <select
        value={formData.priority}
        onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) })}
        className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground focus:border-primary focus:outline-none"
      >
        {[1, 2, 3, 4, 5].map(p => (
          <option key={p} value={p}>Priority {p}</option>
        ))}
      </select>
    </div>
  )}

              {/* Accessibility Checkbox */}
              <div className="p-4 rounded-lg border-2 border-primary/30 bg-primary/5">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.needsAccessibility}
                    onChange={(e) => handleAccessibilityChange(e.target.checked)}
                    className="mt-1 w-5 h-5"
                  />
                  <div>
                    <p className="font-semibold text-foreground">For people with speech differences or challenges</p>
                    <p className="text-sm text-muted-foreground">If checked, you'll answer simple questions instead of reading scripts</p>
                  </div>
                </label>
              </div>

            </form>
          </div>

          {/* Right Column - Recording Interface */}
          <div className="rounded-lg border border-border bg-card p-6">
            <h3 className="text-lg font-semibold text-foreground mb-6">Voice Recording</h3>
            {selectedScript === null && !formData.needsAccessibility ? (
              // Show script selection boxes on the right when no script is selected
              <div className="space-y-4">
                <p className="text-sm font-semibold text-muted-foreground mb-3">Choose a Script to Record</p>
                {VOICE_SCRIPTS.map(voiceScript => (
                  <button
                    key={voiceScript.id}
                    type="button"
                    onClick={() => setSelectedScript(voiceScript.id)}
                    className={`w-full p-4 rounded-lg border-2 cursor-pointer transition-all text-left flex items-center justify-between ${
                      standardRecordings[voiceScript.id]
                        ? 'border-green-400 bg-green-50 dark:bg-green-950/30'
                        : 'border-border hover:border-primary/50 hover:bg-secondary/30'
                    }`}
                  >
                    <div className="flex-1">
                      <p className="font-semibold text-foreground">{voiceScript.label}</p>
                      <p className="text-sm text-muted-foreground mt-1">{voiceScript.instruction}</p>
                    </div>
                    {standardRecordings[voiceScript.id] && (
                      <CheckCircle2 className="h-6 w-6 text-green-600 ml-4 flex-shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            ) : selectedScript !== null && !formData.needsAccessibility ? (
              // Recording interface for selected script
              <div className="space-y-4">
                <div className="p-4 rounded-lg bg-secondary/30 border border-border">
                  <p className="text-sm font-semibold text-muted-foreground mb-2">Say this:</p>
                  <p className="text-base text-foreground italic">{processedScript}</p>
                </div>

                {!isRecording ? (
                  <button
                    type="button"
                    onClick={() => startRecording('standard')}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-4 font-semibold text-primary-foreground transition-all hover:shadow-lg text-lg"
                  >
                    <Mic className="h-6 w-6" />
                    Start Recording
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={stopRecording}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-red-500 px-6 py-4 font-semibold text-white transition-all hover:bg-red-600 text-lg animate-pulse"
                  >
                    <MicOff className="h-6 w-6" />
                    Stop Recording ({recordingTime}s)
                  </button>
                )}

                {standardRecordings[selectedScript] && (
                  <div className="space-y-2 p-4 rounded-lg bg-green-50 border-2 border-green-300">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-5 w-5 text-green-600" />
                      <p className="font-semibold text-green-700">Recording Complete</p>
                    </div>
                    <div className="flex gap-2">
                      <PlaybackControls blob={standardRecordings[selectedScript]} />
                      <button
                        type="button"
                        onClick={() => setStandardRecordings(prev => {
                          const updated = { ...prev };
                          delete updated[selectedScript];
                          return updated;
                        })}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-300 px-4 py-2 font-semibold text-red-600 hover:bg-red-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => setSelectedScript(null)}
                  className="w-full rounded-lg border border-border px-4 py-2 font-semibold text-foreground hover:bg-secondary"
                >
                  Back to Scripts
                </button>
              </div>
            ) : formData.needsAccessibility ? (
              // Accessibility mode - show questions list
              <div className="space-y-4">
                <p className="text-sm font-semibold text-muted-foreground mb-3">Answer these questions</p>
                {ACCESSIBILITY_QUESTIONS.map((question, index) => (
                  <button
                    key={index}
                    type="button"
                    onClick={() => setCurrentAccessibilityQuestion(index)}
                    className={`w-full p-4 rounded-lg border-2 cursor-pointer transition-all text-left flex items-center justify-between ${
                      accessibilityRecordings[index]
                        ? 'border-green-400 bg-green-50 dark:bg-green-950/30'
                        : 'border-border hover:border-primary/50 hover:bg-secondary/30'
                    }`}
                  >
                    <div className="flex-1">
                      <p className="font-semibold text-foreground">Question {index + 1}</p>
                      <p className="text-sm text-muted-foreground mt-1">{question}</p>
                    </div>
                    {accessibilityRecordings[index] && (
                      <CheckCircle2 className="h-6 w-6 text-green-600 ml-4 flex-shrink-0" />
                    )}
                  </button>
                ))}

                {/* Show recording interface when a question is selected */}
                {accessibilityRecordings.length > 0 || currentAccessibilityQuestion > 0 ? (
                  <div className="space-y-4 mt-6 pt-6 border-t border-border">
                    <div className="p-4 rounded-lg bg-secondary/30 border border-border">
                      <p className="text-sm font-semibold text-muted-foreground mb-2">Recording Question {currentAccessibilityQuestion + 1}:</p>
                      <p className="text-lg text-foreground font-medium">{ACCESSIBILITY_QUESTIONS[currentAccessibilityQuestion]}</p>
                    </div>

                    {!isRecording ? (
                      <button
                        type="button"
                        onClick={() => startRecording('accessibility')}
                        className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-4 font-semibold text-primary-foreground transition-all hover:shadow-lg text-lg"
                      >
                        <Mic className="h-6 w-6" />
                        Record Answer
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={stopRecording}
                        className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-red-500 px-6 py-4 font-semibold text-white transition-all hover:bg-red-600 text-lg animate-pulse"
                      >
                        <MicOff className="h-6 w-6" />
                        Stop Recording ({recordingTime}s)
                      </button>
                    )}

                    {accessibilityRecordings[currentAccessibilityQuestion] && (
                      <div className="flex gap-2">
                        <PlaybackControls blob={accessibilityRecordings[currentAccessibilityQuestion]} />
                        <button
                          type="button"
                          onClick={() => {
                            const newRecordings = accessibilityRecordings.filter((_, i) => i !== currentAccessibilityQuestion);
                            setAccessibilityRecordings(newRecordings);
                          }}
                          className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-300 px-4 py-2 font-semibold text-red-600 hover:bg-red-50"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    )}

                    <div className="flex gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => setCurrentAccessibilityQuestion(currentAccessibilityQuestion - 1)}
                        disabled={currentAccessibilityQuestion === 0}
                        className="flex-1 rounded-lg border border-border px-4 py-2 font-semibold text-foreground hover:bg-secondary disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Previous
                      </button>
                      {currentAccessibilityQuestion < ACCESSIBILITY_QUESTIONS.length - 1 ? (
                        <button
                          type="button"
                          onClick={() => setCurrentAccessibilityQuestion(currentAccessibilityQuestion + 1)}
                          disabled={!accessibilityRecordings[currentAccessibilityQuestion]}
                          className="flex-1 rounded-lg bg-primary px-4 py-2 font-semibold text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Next Question
                        </button>
                      ) : null}
                    </div>

                    {accessibilityRecordings.length === ACCESSIBILITY_QUESTIONS.length && (
                      <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                        <p className="text-sm text-green-700 font-medium">✓ All recordings complete</p>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-muted-foreground">Select a script above to begin recording</p>
              </div>
            )}
          </div>
        </div>

        {/* Submit Section - Below both columns */}
        <form onSubmit={handleFormSubmit} className="mt-8">
          <div className="rounded-lg border border-border bg-card p-6">
            {submitError && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                {submitError}
              </div>
            )}
            {/* Submit Buttons */}
            <div className="flex gap-2 pt-6 border-t border-border mt-6">
              <button
                type="button"
                onClick={() => startTransition(() => router.back())}
                disabled={isPending || isSubmitting}
                className="flex-1 rounded-lg border border-border px-6 py-3 font-semibold text-foreground hover:bg-secondary disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 rounded-lg bg-primary px-6 py-3 font-semibold text-primary-foreground hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isSubmitting || isRecording || (!formData.needsAccessibility && Object.keys(standardRecordings).length < 3) || (formData.needsAccessibility && accessibilityRecordings.length !== ACCESSIBILITY_QUESTIONS.length)}
              >
                {isSubmitting ? 'Enrolling…' : 'Confirm Add Voice'}
              </button>
            </div>
          </div>
        </form>

        {/* Add Voice Confirmation Modal - appears after Script 3 */}
        {showAddVoiceConfirm && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-card rounded-lg max-w-md w-full p-6 border border-border shadow-2xl">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-foreground">Confirm Add Voice</h2>
                <button
                  onClick={() => setShowAddVoiceConfirm(false)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <p className="text-muted-foreground mb-6">All 3 scripts have been recorded successfully. Ready to add <span className="font-semibold text-foreground">{formData.name}</span> to your voice assistants?</p>
              
              <div className="flex gap-2">
                <button
                  onClick={() => setShowAddVoiceConfirm(false)}
                  disabled={isSubmitting}
                  className="flex-1 rounded-lg border border-border px-4 py-2 font-semibold text-foreground hover:bg-secondary disabled:opacity-60"
                >
                  Cancel
                </button>
                <button
                  onClick={() => completeAddSpeaker()}
                  disabled={isSubmitting}
                  className="flex-1 rounded-lg bg-primary px-4 py-2 font-semibold text-primary-foreground hover:shadow-lg disabled:opacity-60"
                >
                  {isSubmitting ? 'Enrolling…' : 'Confirm Add Voice'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Removal Modal - for healthy speaker limit (5 max) or accessibility limit */}
        <RemovalModal 
          isOpen={showRemovalModal} 
          onClose={() => setShowRemovalModal(false)}
          formData={formData}
          speakers={allSpeakers}
          onConfirm={(speakerId) => completeAddSpeaker(speakerId)}
        />
      </div>
    </div>
  );
}
