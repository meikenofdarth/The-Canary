'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Mic, MicOff, Play, Download, ArrowLeft } from 'lucide-react';

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

interface Speaker {
  id: string;
  name: string;
  avatar: string;
  priority: number;
  status: 'active' | 'scheduled' | 'completed';
}

export default function AddSpeakerPage() {
  const router = useRouter();
  const [speakers, setSpeakers] = useState<Speaker[]>([
    {
      id: '1',
      name: 'Voice Model Pro',
      avatar: '/avatars/lion.png',
      priority: 5,
      status: 'active',
    },
    {
      id: '2',
      name: 'Canary Assistant',
      avatar: '/avatars/owl.png',
      priority: 4,
      status: 'scheduled',
    },
    {
      id: '3',
      name: 'Smart Engine',
      avatar: '/avatars/fox.png',
      priority: 3,
      status: 'scheduled',
    },
    {
      id: '4',
      name: 'Advanced Listener',
      avatar: '/avatars/raven.png',
      priority: 2,
      status: 'completed',
    },
    {
      id: '5',
      name: 'Canary Neural',
      avatar: '/avatars/eagle.png',
      priority: 1,
      status: 'scheduled',
    },
  ]);

  const [showAddForm, setShowAddForm] = useState(false);
  const [showRemoveDialog, setShowRemoveDialog] = useState(false);
  const [newSpeakerName, setNewSpeakerName] = useState('');
  const [newSpeakerPriority, setNewSpeakerPriority] = useState<number>(1);
  const [selectedScript, setSelectedScript] = useState<number | null>(null);
  const [confirmedScripts, setConfirmedScripts] = useState<number[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState<Blob | null>(null);
  const [highlightedWords, setHighlightedWords] = useState<number[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const script = selectedScript ? VOICE_SCRIPTS[selectedScript - 1] : null;
  const processedScript = script
    ? script.text.replace('[your name]', newSpeakerName || 'your name')
    : '';
  const sentences = processedScript.split(/(?<=[.!?])\s+/).filter(s => s.trim());

  const startRecording = async () => {
    // TODO: API Integration - Prepare recording session
    // POST /api/speakers/recording-session
    // Payload: { speakerName: string, scriptId: number }
    // Response: { sessionId: string, startedAt: timestamp }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      // Setup audio context for visualization
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = audioContext;
      const analyser = audioContext.createAnalyser();
      analyserRef.current = analyser;
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      // Visualize audio as sentences are spoken
      const frequencyData = new Uint8Array(analyser.frequencyBinCount);
      let sentenceIndex = 0;
      let silenceCount = 0;
      const visualizeAudio = () => {
        analyser.getByteFrequencyData(frequencyData);
        const average = frequencyData.reduce((a, b) => a + b) / frequencyData.length;

        // Highlight sentences based on audio level
        if (average > 50) {
          silenceCount = 0;
          if (sentenceIndex < sentences.length && !highlightedWords.includes(sentenceIndex)) {
            setHighlightedWords(prev => [...prev, sentenceIndex]);
          }
        } else {
          silenceCount++;
          // Move to next sentence after ~500ms of silence
          if (silenceCount > 25 && sentenceIndex < sentences.length - 1) {
            sentenceIndex++;
            silenceCount = 0;
          }
        }

        if (isRecording) {
          requestAnimationFrame(visualizeAudio);
        }
      };

      mediaRecorder.ondataavailable = (event) => {
        chunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setRecordedAudio(blob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      visualizeAudio();
    } catch (err) {
      console.error('Error accessing microphone:', err);
      alert('Unable to access microphone. Please check permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleAddSpeaker = async () => {
    if (!newSpeakerName.trim()) {
      alert('Please enter a speaker name');
      return;
    }

    // For Scripts 1 & 2: just mark as confirmed, don't add speaker yet
    if (selectedScript === 1 || selectedScript === 2) {
      setConfirmedScripts([...confirmedScripts, selectedScript]);
      setSelectedScript(null);
      setRecordedAudio(null);
      setHighlightedWords([]);
      return;
    }

    // For Script 3: add the speaker
    if (speakers.length >= 5) {
      setShowRemoveDialog(true);
      return;
    }

    // TODO: API Integration - Upload voice recording
    // POST /api/speakers/upload-recording
    // Payload: { audioBlob: Blob, speakerName: string, scriptId: number }
    // Response: { recordingId: string, processedAt: timestamp }
    const recordingId = recordedAudio ? 'recording_' + Date.now() : null;

    const newSpeaker: Speaker = {
      id: Date.now().toString(),
      name: newSpeakerName,
      avatar: `/avatars/${['lion', 'owl', 'fox', 'raven', 'eagle'][Math.floor(Math.random() * 5)]}.png`,
      priority: newSpeakerPriority,
      status: 'scheduled',
    };

    // TODO: API Integration - Create speaker
    // POST /api/speakers/create
    // Payload: { name: string, priority: number, recordingId: string, avatar: string }
    // Response: { id: string, createdAt: timestamp, status: 'scheduled' | 'active' }

    setSpeakers([...speakers, newSpeaker].sort((a, b) => b.priority - a.priority));
    setNewSpeakerName('');
    setNewSpeakerPriority(1);
    setSelectedScript(null);
    setRecordedAudio(null);
    setHighlightedWords([]);
    setConfirmedScripts([]);
    setShowAddForm(false);
    sessionStorage.setItem('speakersData', JSON.stringify([...speakers, newSpeaker].sort((a, b) => b.priority - a.priority)));
  };

  const handleRemoveSpeaker = (id: string) => {
    // TODO: API Integration - Delete speaker
    // DELETE /api/speakers/:id
    // Response: { success: boolean, deletedAt: timestamp }
    const newList = speakers.filter(s => s.id !== id);
    setSpeakers(newList);
    sessionStorage.setItem('speakersData', JSON.stringify(newList));
    setShowRemoveDialog(false);
  };

  const updatePriority = (id: string, newPriority: number) => {
    // TODO: API Integration - Update speaker priority
    // PATCH /api/speakers/:id/priority
    // Payload: { priority: number }
    // Response: { id: string, priority: number, updatedAt: timestamp }
    setSpeakers(speakers.map(s => s.id === id ? { ...s, priority: newPriority } : s).sort((a, b) => b.priority - a.priority));
  };

  const [draggedId, setDraggedId] = useState<string | null>(null);

  const handleDragStart = (e: React.DragEvent, id: string) => {
    setDraggedId(id);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e: React.DragEvent, targetId: string) => {
    e.preventDefault();
    if (draggedId && draggedId !== targetId) {
      const draggedSpeaker = speakers.find(s => s.id === draggedId);
      const targetSpeaker = speakers.find(s => s.id === targetId);

      if (draggedSpeaker && targetSpeaker) {
        // TODO: API Integration - Reorder speakers by priority
        // PATCH /api/speakers/reorder
        // Payload: { draggedId: string, targetId: string, draggedPriority: number, targetPriority: number }
        // Response: { speakers: Speaker[], reorderedAt: timestamp }
        const newSpeakers = speakers.map(s => {
          if (s.id === draggedId) return { ...s, priority: targetSpeaker.priority };
          if (s.id === targetId) return { ...s, priority: draggedSpeaker.priority };
          return s;
        }).sort((a, b) => b.priority - a.priority);
        
        setSpeakers(newSpeakers);
        sessionStorage.setItem('speakersData', JSON.stringify(newSpeakers));
      }
    }
    setDraggedId(null);
  };

  const getButtonLabel = () => {
    if (speakers.length < 2) return 'Add Voice';
    if (speakers.length < 3) return 'Add Voice';
    return 'Add Speaker';
  };

  const sortedSpeakers = [...speakers].sort((a, b) => b.priority - a.priority);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card px-6 py-6">
        <div className="mx-auto max-w-7xl">
          <button
            onClick={() => router.back()}
            className="mb-4 flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </button>
          <h1 className="text-3xl font-bold text-foreground font-manrope">Manage Speakers</h1>
          <p className="mt-1 text-muted-foreground">Add and manage voice assistants with voice recording</p>
        </div>
      </div>

      {/* Main Content */}
      <div className="mx-auto max-w-7xl px-6 py-8">
        {/* Action Buttons */}
        <div className="mb-8 flex gap-4">
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 font-semibold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/40"
          >
            <Mic className="h-5 w-5" />
            {getButtonLabel()}
          </button>
        </div>

        {/* Add Speaker Form */}
        {showAddForm && (
          <div className="mb-8 rounded-lg border border-border bg-card p-6">
            <h2 className="mb-6 text-xl font-bold text-foreground font-mulish">Register New Speaker</h2>

            <div className="grid gap-6 md:grid-cols-2">
              {/* Speaker Info */}
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-foreground">Speaker Name</label>
                  <input
                    type="text"
                    value={newSpeakerName}
                    onChange={(e) => setNewSpeakerName(e.target.value)}
                    placeholder="Enter speaker name"
                    className="mt-2 w-full rounded-lg border border-border bg-secondary px-4 py-2 text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-foreground">Speaker Priority</label>
                  <select
                    value={newSpeakerPriority}
                    onChange={(e) => setNewSpeakerPriority(parseInt(e.target.value))}
                    className="mt-2 w-full rounded-lg border border-border bg-secondary px-4 py-2 text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                  >
                    {[1, 2, 3, 4, 5].map(n => (
                      <option key={n} value={n}>Priority {n}</option>
                    ))}
                  </select>
                </div>

                {/* Script Selection */}
                <div>
                  <label className="block text-sm font-medium text-foreground">Select Recording Script</label>
                  <div className="mt-2 space-y-2">
                    {VOICE_SCRIPTS.map(s => (
                      <button
                        key={s.id}
                        onClick={() => {
                          setSelectedScript(s.id);
                          setHighlightedWords([]);
                        }}
                        className={`w-full rounded-lg border-2 p-3 text-left transition-all ${
                          confirmedScripts.includes(s.id)
                            ? 'border-green-500 bg-green-50 ring-2 ring-green-300'
                            : selectedScript === s.id
                            ? 'border-primary bg-primary/10'
                            : 'border-border hover:border-primary/50'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-semibold text-foreground">{s.label}</p>
                            <p className="text-xs text-muted-foreground mt-1">{s.instruction}</p>
                          </div>
                          {confirmedScripts.includes(s.id) && (
                            <div className="text-green-600 text-lg">✓</div>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Voice Recorder */}
              {selectedScript && (
                <div className="space-y-4">
                  <div className="rounded-lg bg-secondary/50 p-4">
                    <p className="text-sm text-muted-foreground mb-3">Script text with sentence highlighting:</p>
                    <div className="space-y-2">
                      {sentences.map((sentence, idx) => (
                        <p
                          key={idx}
                          className={`px-3 py-2 rounded text-sm transition-all font-medium ${
                            highlightedWords.includes(idx)
                              ? 'bg-red-500 text-white'
                              : 'bg-border text-foreground'
                          }`}
                        >
                          {sentence.trim()}
                        </p>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-foreground mb-3">Voice Recording</label>
                    <div className="flex gap-3">
                      {!isRecording && !recordedAudio && (
                        <button
                          onClick={startRecording}
                          className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 font-semibold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/40"
                        >
                          <Mic className="h-5 w-5" />
                          Start Recording
                        </button>
                      )}
                      {isRecording && (
                        <button
                          onClick={stopRecording}
                          className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-red-500 px-4 py-3 font-semibold text-white transition-all hover:shadow-lg hover:shadow-red-500/40 animate-pulse"
                        >
                          <MicOff className="h-5 w-5" />
                          Stop Recording
                        </button>
                      )}
                      {recordedAudio && (
                        <>
                          <button
                            onClick={() => {
                              const url = URL.createObjectURL(recordedAudio);
                              const audio = new Audio(url);
                              audio.play();
                            }}
                            className="flex-1 flex items-center justify-center gap-2 rounded-lg border-2 border-primary px-4 py-3 font-semibold text-primary transition-all hover:bg-primary/5"
                          >
                            <Play className="h-5 w-5" />
                            Play Recording
                          </button>
                          <a
                            href={URL.createObjectURL(recordedAudio)}
                            download="speaker-recording.webm"
                            className="flex items-center justify-center rounded-lg border-2 border-border px-4 py-3 font-semibold text-foreground transition-all hover:bg-secondary"
                          >
                            <Download className="h-5 w-5" />
                          </a>
                        </>
                      )}
                    </div>
                  </div>

                  {selectedScript && (
                    <button
                      onClick={handleAddSpeaker}
                      className="w-full rounded-lg bg-primary px-4 py-2 font-semibold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/40"
                    >
                      {selectedScript === 3 ? 'Confirm Add Speaker' : 'Confirm Add Voice'}
                    </button>
                  )}
                  {confirmedScripts.includes(1) && confirmedScripts.includes(2) && !selectedScript && (
                    <button
                      onClick={() => setSelectedScript(3)}
                      className="w-full rounded-lg bg-green-600 px-4 py-2 font-semibold text-white transition-all hover:shadow-lg hover:shadow-green-600/40"
                    >
                      Next: Script 3
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Speakers Table */}
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-secondary/50">
                <th className="px-6 py-4 text-left text-sm font-semibold text-foreground">Speaker</th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-foreground">Priority</th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-foreground">Status</th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-foreground">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sortedSpeakers.map((speaker, idx) => (
                <tr
                  key={speaker.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, speaker.id)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, speaker.id)}
                  className={`transition-all ${
                    draggedId === speaker.id
                      ? 'opacity-50 bg-primary/10'
                      : 'hover:bg-secondary/40 cursor-move'
                  }`}
                >
                  <td className="px-6 py-4 flex items-center gap-3">
                    <img
                      src={speaker.avatar}
                      alt={speaker.name}
                      className="h-10 w-10 rounded-full"
                    />
                    <span className="font-medium text-foreground">{speaker.name}</span>
                  </td>
                  <td className="px-6 py-4">
                    <select
                      value={speaker.priority}
                      onChange={(e) => updatePriority(speaker.id, parseInt(e.target.value))}
                      className="rounded-lg border border-border bg-secondary px-3 py-1 text-sm font-medium text-foreground focus:border-primary focus:outline-none"
                    >
                      {[1, 2, 3, 4, 5].map(n => (
                        <option key={n} value={n}>{n}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                      speaker.status === 'active' ? 'bg-green-100 text-green-800' :
                      speaker.status === 'scheduled' ? 'bg-blue-100 text-blue-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {speaker.status.charAt(0).toUpperCase() + speaker.status.slice(1)}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => handleRemoveSpeaker(speaker.id)}
                      className="text-sm text-red-600 hover:text-red-800 transition-colors font-medium"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Remove Dialog */}
      {showRemoveDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-lg bg-card p-6 shadow-xl">
            <h2 className="text-lg font-bold text-foreground">Remove a Speaker</h2>
            <p className="mt-2 text-muted-foreground">You have reached the limit of 5 speakers. Select one to remove:</p>
            <div className="mt-4 space-y-2">
              {speakers.map(s => (
                <button
                  key={s.id}
                  onClick={() => handleRemoveSpeaker(s.id)}
                  className="w-full rounded-lg border border-border p-3 text-left hover:bg-secondary/50 transition-colors text-foreground font-medium"
                >
                  {s.name}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowRemoveDialog(false)}
              className="mt-4 w-full rounded-lg border border-border px-4 py-2 font-semibold text-foreground hover:bg-secondary transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
