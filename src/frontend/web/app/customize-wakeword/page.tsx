'use client';

import { useState, useRef, useEffect, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { Mic, MicOff, ArrowLeft, CheckCircle2, Zap, Radio, Headphones, Play, Pause, Square } from 'lucide-react';
import { changeBackendWakeword } from '@/lib/api';

export default function CustomizeWakewordPage() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [recordingPhase, setRecordingPhase] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const [recordings, setRecordings] = useState<Blob[]>([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [detectedText, setDetectedText] = useState('');
  const [sessionActive, setSessionActive] = useState(false);
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const animationRef = useRef<number | null>(null);
  const recognitionRef = useRef<any>(null);

  // Playback state for completed recordings
  const playbackRef = useRef<HTMLAudioElement | null>(null);
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);
  const [isPausedIndex, setIsPausedIndex] = useState<number | null>(null);

  const handlePlay = (index: number) => {
    // Stop any current playback
    if (playbackRef.current) {
      playbackRef.current.pause();
      playbackRef.current.src = '';
      playbackRef.current = null;
    }
    // If clicking the currently playing one, treat as stop
    if (playingIndex === index) {
      setPlayingIndex(null);
      setIsPausedIndex(null);
      return;
    }
    const url = URL.createObjectURL(recordings[index]);
    const audio = new Audio(url);
    playbackRef.current = audio;
    setPlayingIndex(index);
    setIsPausedIndex(null);
    audio.play();
    audio.onended = () => {
      URL.revokeObjectURL(url);
      setPlayingIndex(null);
      setIsPausedIndex(null);
      playbackRef.current = null;
    };
  };

  const handlePause = () => {
    if (!playbackRef.current) return;
    if (playbackRef.current.paused) {
      playbackRef.current.play();
      setIsPausedIndex(null);
    } else {
      playbackRef.current.pause();
      setIsPausedIndex(playingIndex);
    }
  };

  const handleStop = () => {
    if (playbackRef.current) {
      playbackRef.current.pause();
      playbackRef.current.src = '';
      playbackRef.current = null;
    }
    setPlayingIndex(null);
    setIsPausedIndex(null);
  };

  // Initialize speech recognition
  useEffect(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = true;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.lang = 'en-US';

      recognitionRef.current.onresult = (event: any) => {
        let interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            setDetectedText(transcript);
          } else {
            interimTranscript += transcript;
          }
        }
      };

      recognitionRef.current.onerror = (event: any) => {
        console.log('Speech recognition error:', event.error);
      };
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  // TODO: API Integration - Fetch current wake word settings
  // GET /api/wakeword/settings
  // Response: { wakeWord: string, recordings: number, complexity: 'easy' }

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      // Setup audio context for visualization
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const analyser = audioContext.createAnalyser();
      analyserRef.current = analyser;
      analyser.minDecibels = -90;
      analyser.maxDecibels = -10;

      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      // Monitor audio levels to show speaking feedback
      const frequencyData = new Uint8Array(analyser.frequencyBinCount);
      const monitorAudio = () => {
        analyser.getByteFrequencyData(frequencyData);
        const average = frequencyData.reduce((a, b) => a + b) / frequencyData.length;
        setIsSpeaking(average > 40);
        
        if (isRecording) {
          animationRef.current = requestAnimationFrame(monitorAudio);
        }
      };

      mediaRecorder.ondataavailable = (event) => {
        chunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setRecordings([...recordings, blob]);
        stream.getTracks().forEach(track => track.stop());
        
        if (recognitionRef.current) {
          recognitionRef.current.stop();
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
      setDetectedText('');
      setSessionActive(true);

      // Start speech recognition
      if (recognitionRef.current) {
        recognitionRef.current.start();
      }

      monitorAudio();
    } catch (err) {
      console.error('Error accessing microphone:', err);
      alert('Unable to access microphone. Please check permissions.');
    }
  };

  const stopRecording = () => {
    // TODO: API Integration - Save wake word recording phase
    // POST /api/wakeword/session/save-phase
    // Payload: { phase: number, audioBlob: Blob, detectedText: string }
    // Response: { phaseId: string, savedAt: timestamp, nextPhase: number }
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      setSessionActive(false);
      
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }

      if (recordingPhase < 3) {
        setRecordingPhase(recordingPhase + 1);
      }
    }
  };

  const handleComplete = async () => {
    if (recordings.length !== 3) return;
    try {
      const result = await changeBackendWakeword(recordings);
      alert(`Wake word set to "${result.word}". Generated ${result.variants_generated} phonetic variants.`);
      startTransition(() => {
        router.push('/dashboard');
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Wake-word change failed.';
      alert(msg);
    }
  };

  const handleStart = () => {
    setRecordingPhase(1);
    startRecording();
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-secondary/20">
      {/* Header */}
      <div className="absolute top-6 left-6">
        <button
          onClick={() => startTransition(() => router.back())}
          disabled={isPending}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-60"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
      </div>

      {/* Main Content */}
      <div className="flex h-screen">
        {/* Left Sidebar - Tips & Information */}
        <div className="hidden lg:flex w-64 flex-col justify-center px-8 py-12 border-r border-border/20">
          <div className="space-y-6">
            <div>
              <div className="flex items-start gap-3 mb-4">
                <Zap className="w-5 h-5 text-primary mt-1 flex-shrink-0" />
                <div>
                  <h3 className="font-semibold text-foreground text-sm">Take Your Time</h3>
                  <p className="text-xs text-muted-foreground mt-1">Speak at your natural pace and rhythm</p>
                </div>
              </div>
            </div>

            <div>
              <div className="flex items-start gap-3 mb-4">
                <Radio className="w-5 h-5 text-primary mt-1 flex-shrink-0" />
                <div>
                  <h3 className="font-semibold text-foreground text-sm">Quiet Space</h3>
                  <p className="text-xs text-muted-foreground mt-1">Find a calm environment for better accuracy</p>
                </div>
              </div>
            </div>

            <div>
              <div className="flex items-start gap-3 mb-4">
                <Headphones className="w-5 h-5 text-primary mt-1 flex-shrink-0" />
                <div>
                  <h3 className="font-semibold text-foreground text-sm">3-5 Seconds</h3>
                  <p className="text-xs text-muted-foreground mt-1">Each recording should be natural length</p>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-border/20">
              <p className="text-xs text-muted-foreground italic">
                Your voice is unique. We'll learn to recognize your natural speaking style.
              </p>
            </div>
          </div>
        </div>

        {/* Center - Main Recording Interface */}
        <div className="flex-1 flex flex-col items-center justify-center px-4 sm:px-8 py-12">
          {recordingPhase === 0 ? (
            // Start Screen
            <div className="text-center max-w-md">
              <h1 className="text-4xl sm:text-5xl font-bold text-foreground font-manrope mb-4">
                Train Your Voice
              </h1>
              <p className="text-lg text-muted-foreground font-mulish mb-2">
                Record three natural examples of your voice
              </p>
              <p className="text-sm text-muted-foreground mb-12">
                We'll use these to learn your unique speaking style. Just speak naturally whenever you're ready.
              </p>

              <button
                onClick={handleStart}
                className="px-8 py-4 bg-primary text-primary-foreground rounded-lg font-semibold transition-all hover:shadow-lg hover:shadow-primary/40 text-lg"
              >
                Begin Recording
              </button>
            </div>
          ) : (
            // Recording Screen
            <div className="w-full max-w-lg">
              <div className="text-center mb-12">
                <h2 className="text-3xl font-bold text-foreground font-manrope mb-2">
                  Recording {Math.min(recordings.length + 1, 3)} of 3
                </h2>
                <p className={`text-sm transition-colors ${
                  isSpeaking ? 'text-primary font-semibold' : 'text-muted-foreground'
                }`}>
                  {isSpeaking ? '🎤 Listening...' : isRecording ? 'Speaking?' : 'Ready to record'}
                </p>
              </div>

              {/* Microphone Visualization */}
              <div className="flex justify-center mb-12">
                <div className="relative w-80 h-80 flex items-center justify-center">
                  {/* Outer Ring - Only when speaking */}
                  <div
                    className="absolute inset-0 rounded-full border-8 transition-all duration-150"
                    style={{
                      borderColor: isSpeaking && isRecording ? 'rgba(253, 212, 58, 0.8)' : 'transparent',
                      boxShadow: isSpeaking && isRecording
                        ? '0 0 40px rgba(253, 212, 58, 0.5), 0 0 80px rgba(253, 212, 58, 0.25)'
                        : 'none',
                    }}
                  ></div>

                  {/* Center Circle */}
                  <div
                    className={`relative z-10 w-56 h-56 rounded-full flex items-center justify-center transition-all duration-200 ${
                      isRecording
                        ? 'bg-gradient-to-br from-red-600 to-red-500 shadow-2xl shadow-red-600/50 scale-105'
                        : 'bg-gradient-to-br from-primary via-yellow-400 to-primary shadow-lg shadow-primary/30 border-4 border-primary/30'
                    }`}
                  >
                    {isRecording ? (
                      <MicOff className="w-28 h-28 text-white animate-pulse" />
                    ) : (
                      <Mic className="w-28 h-28 text-primary-foreground" />
                    )}
                  </div>
                </div>
              </div>

              {/* Detected Text Display */}
              {detectedText && (
                <div className="mb-8 p-4 bg-secondary/50 border border-primary/30 rounded-lg text-center">
                  <p className="text-sm text-muted-foreground mb-1">What we heard:</p>
                  <p className="text-lg font-semibold text-foreground italic">"{detectedText}"</p>
                </div>
              )}

              {/* Recording Controls */}
              <div className="flex gap-4 justify-center mb-8">
                {!isRecording ? (
                  <button
                    onClick={startRecording}
                    disabled={recordings.length >= 3}
                    className="px-8 py-4 bg-primary text-primary-foreground rounded-lg font-semibold transition-all hover:shadow-lg hover:shadow-primary/40 disabled:opacity-50 disabled:cursor-not-allowed text-lg"
                  >
                    Start Recording
                  </button>
                ) : (
                  <button
                    onClick={stopRecording}
                    className="px-8 py-4 bg-red-600 text-white rounded-lg font-semibold transition-all hover:shadow-lg hover:shadow-red-600/40 text-lg animate-pulse"
                  >
                    Stop Recording
                  </button>
                )}
              </div>

              {/* Progress Bar */}
              <div className="mb-8">
                <div className="mb-3 flex items-center justify-between">
                  <label className="text-sm font-semibold text-foreground">Progress</label>
                  <span className="text-sm text-muted-foreground font-semibold">{recordings.length}/3</span>
                </div>
                <div className="w-full h-4 bg-secondary rounded-full overflow-hidden border border-border/50">
                  <div
                    className="h-full bg-gradient-to-r from-primary via-yellow-400 to-primary transition-all duration-300 ease-out"
                    style={{ width: `${(recordings.length / 3) * 100}%` }}
                  ></div>
                </div>

                {/* Checkpoint Indicators */}
                {recordingPhase > 0 && (
                  <div className="mt-4 flex gap-2">
                    {[1, 2, 3].map((i) => (
                      <div
                        key={i}
                        className={`flex-1 h-3 rounded-full transition-all ${
                          i <= recordings.length
                            ? 'bg-gradient-to-r from-primary via-yellow-400 to-primary'
                            : 'bg-secondary/40'
                        }`}
                      ></div>
                    ))}
                  </div>
                )}
              </div>

              {/* Quick Tips during recording */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <div className="flex gap-2">
                  <div className="text-blue-600 mt-0.5">💡</div>
                  <div>
                    <p className="text-sm text-blue-900">
                      {isSpeaking ? 'Keep speaking naturally at your own pace' : 'Click Start when ready to record'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Complete Button */}
              {recordings.length === 3 && (
                <button
                  onClick={handleComplete}
                  className="w-full px-8 py-4 bg-gradient-to-r from-primary via-yellow-400 to-primary text-primary-foreground rounded-lg font-semibold transition-all hover:shadow-lg hover:shadow-primary/50 text-lg flex items-center justify-center gap-2"
                >
                  <CheckCircle2 className="w-5 h-5" />
                  Complete Training
                </button>
              )}
            </div>
          )}
        </div>

        {/* Right Sidebar - Recording Boxes Only */}
        <div className="hidden lg:flex w-72 flex-col justify-center px-8 py-12 border-l border-border/20">
          <div className="space-y-6">
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Recording Boxes</p>
              <div className="space-y-3">
                {[1, 2, 3].map((i) => {
                  const idx = i - 1;
                  const isDone = recordings.length >= i;
                  const isActive = recordingPhase === i && !isDone;
                  const isThisPlaying = playingIndex === idx;
                  const isThisPaused = isPausedIndex === idx;

                  return (
                    <div
                      key={i}
                      className={`px-4 py-4 rounded-lg border-2 transition-all ${
                        isDone
                          ? 'bg-green-50 border-green-300'
                          : isActive
                          ? 'bg-primary/10 border-primary'
                          : 'bg-secondary/20 border-secondary/40'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-foreground">Recording {i}</span>
                        {isDone ? (
                          <CheckCircle2 className="w-5 h-5 text-green-600" />
                        ) : isActive ? (
                          <div className="w-5 h-5 rounded-full border-2 border-primary animate-spin border-t-transparent" />
                        ) : (
                          <div className="w-5 h-5 rounded-full border-2 border-secondary/40" />
                        )}
                      </div>

                      {isDone && (
                        <div className="mt-3 flex items-center gap-1.5">
                          {/* Play / Pause toggle */}
                          <button
                            type="button"
                            onClick={() => isThisPlaying && !isThisPaused ? handlePause() : isThisPaused ? handlePause() : handlePlay(idx)}
                            className="flex items-center justify-center w-8 h-8 rounded-full bg-green-600 hover:bg-green-700 text-white transition-colors"
                            aria-label={isThisPlaying && !isThisPaused ? 'Pause' : 'Play'}
                          >
                            {isThisPlaying && !isThisPaused
                              ? <Pause className="w-3.5 h-3.5" />
                              : <Play className="w-3.5 h-3.5 ml-0.5" />
                            }
                          </button>

                          {/* Stop — only shown while this one is active */}
                          {(isThisPlaying || isThisPaused) && (
                            <button
                              type="button"
                              onClick={handleStop}
                              className="flex items-center justify-center w-8 h-8 rounded-full bg-secondary hover:bg-secondary/80 text-foreground transition-colors"
                              aria-label="Stop"
                            >
                              <Square className="w-3 h-3" />
                            </button>
                          )}

                          <span className="text-xs text-green-700 ml-1">
                            {isThisPlaying && !isThisPaused
                              ? 'Playing…'
                              : isThisPaused
                              ? 'Paused'
                              : '✓ Recorded'}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="pt-4 border-t border-border/20">
              <p className="text-xs text-muted-foreground">
                All recordings are processed securely. Your voice is yours alone.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
