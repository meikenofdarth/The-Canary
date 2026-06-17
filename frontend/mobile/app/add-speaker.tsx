import { useState, useRef, useEffect } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView, Switch, KeyboardAvoidingView, Platform, Alert, Modal } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Audio } from 'expo-av';
import { ArrowLeft, Mic, MicOff, Play, Pause, Square, CheckCircle2, X } from 'lucide-react-native';
import { COLORS, SPACING, RADIUS } from '../constants/theme';
import { enrollBackendSpeaker } from '../lib/api';
import { addSpeaker, refreshSpeakers, getSpeakers, getNormalSpeakers, deleteSpeaker } from '../lib/speakers-store';

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
  
  const [formData, setFormData] = useState({
    name: '',
    city: '',
    country: '',
    musicGenre: '',
    priority: 1,
    needsAccessibility: false,
  });

  const [selectedScript, setSelectedScript] = useState<number | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [recordingTime, setRecordingTime] = useState(0);
  
  const [standardRecordings, setStandardRecordings] = useState<{ [key: number]: string }>({});
  const [accessibilityRecordings, setAccessibilityRecordings] = useState<string[]>([]);
  const [currentAccessibilityQuestion, setCurrentAccessibilityQuestion] = useState(0);
  
  const [sound, setSound] = useState<Audio.Sound | null>(null);
  const [playingUri, setPlayingUri] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  
  const [showRemovalModal, setShowRemovalModal] = useState(false);
  const [allSpeakers, setAllSpeakers] = useState<any[]>([]);
  const [selectedSpeakerToRemove, setSelectedSpeakerToRemove] = useState<string | null>(null);

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return sound ? () => { sound.unloadAsync(); } : undefined;
  }, [sound]);

  const script = selectedScript ? VOICE_SCRIPTS[selectedScript - 1] : null;
  const processedScript = script ? script.text.replace('[your name]', formData.name || 'your name') : '';

  const startRecording = async (type: 'standard' | 'accessibility') => {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (permission.status !== 'granted') {
        Alert.alert('Permission Denied', 'Microphone access is required to record voice samples.');
        return;
      }
      
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const { recording } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      setRecording(recording);
      setIsRecording(true);
      setRecordingTime(0);

      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      console.error('Failed to start recording', err);
    }
  };

  const stopRecording = async (type: 'standard' | 'accessibility') => {
    if (!recording) return;

    if (timerRef.current) clearInterval(timerRef.current);
    
    await recording.stopAndUnloadAsync();
    const uri = recording.getURI();
    setRecording(null);
    setIsRecording(false);

    if (uri) {
      if (type === 'standard' && selectedScript) {
        setStandardRecordings(prev => ({ ...prev, [selectedScript]: uri }));
      } else if (type === 'accessibility') {
        const newRecordings = [...accessibilityRecordings];
        newRecordings[currentAccessibilityQuestion] = uri;
        setAccessibilityRecordings(newRecordings);
      }
    }
  };

  const playRecording = async (uri: string) => {
    if (sound) {
      await sound.unloadAsync();
    }
    
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
      playsInSilentModeIOS: true,
    });

    const { sound: newSound } = await Audio.Sound.createAsync({ uri }, { shouldPlay: true });
    setSound(newSound);
    setPlayingUri(uri);
    setIsPlaying(true);

    newSound.setOnPlaybackStatusUpdate((status) => {
      if (status.isLoaded && status.didJustFinish) {
        setIsPlaying(false);
        setPlayingUri(null);
      }
    });
  };

  const pausePlayback = async () => {
    if (sound) {
      await sound.pauseAsync();
      setIsPlaying(false);
    }
  };

  const stopPlayback = async () => {
    if (sound) {
      await sound.stopAsync();
      setIsPlaying(false);
      setPlayingUri(null);
    }
  };

  const deleteRecording = (type: 'standard' | 'accessibility', id: number) => {
    if (type === 'standard') {
      const newRecs = { ...standardRecordings };
      delete newRecs[id];
      setStandardRecordings(newRecs);
    } else {
      const newRecs = [...accessibilityRecordings];
      newRecs[id] = '';
      setAccessibilityRecordings(newRecs.filter(r => r !== ''));
    }
  };

  const handleFormSubmit = async () => {
    setSubmitError('');

    if (!formData.name || !formData.city || !formData.country || !formData.musicGenre) {
      setSubmitError('Please fill all required fields');
      return;
    }

    if (!formData.needsAccessibility) {
      const hasAllRecordings = VOICE_SCRIPTS.every(s => standardRecordings[s.id]);
      if (!hasAllRecordings) {
        setSubmitError('Please record all 3 scripts before submitting');
        return;
      }

      const existingSpeakers = await getSpeakers();
      setAllSpeakers(existingSpeakers);
      const healthySpeakers = existingSpeakers.filter(s => !s.isAccessible);

      if (healthySpeakers.length >= 5) {
        setShowRemovalModal(true);
        return;
      }
    } else {
      if (accessibilityRecordings.length !== ACCESSIBILITY_QUESTIONS.length) {
        setSubmitError('Please complete all accessibility recordings');
        return;
      }

      const existingSpeakers = await getSpeakers();
      setAllSpeakers(existingSpeakers);
      const accessSpeakers = existingSpeakers.filter(s => s.isAccessible);

      if (accessSpeakers.length > 0) {
        setShowRemovalModal(true);
        return;
      }
    }

    if (Platform.OS === 'web') {
      if (window.confirm("Are you sure you want to enroll this speaker?")) {
        completeAddSpeaker();
      }
    } else {
      Alert.alert(
        "Confirm Add Voice",
        "Are you sure you want to enroll this speaker?",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Confirm", onPress: () => completeAddSpeaker() }
        ]
      );
    }
  };

  const completeAddSpeaker = async (speakerToRemoveId?: string) => {
    setIsSubmitting(true);
    try {
      if (speakerToRemoveId) {
        await deleteSpeaker(speakerToRemoveId);
      }

      const uris = formData.needsAccessibility
        ? accessibilityRecordings.slice(0, 3)
        : VOICE_SCRIPTS.map(s => standardRecordings[s.id]);

      // Note: React Native fetch with FormData for files requires special format
      const audioBlobs = await Promise.all(uris.map(async (uri) => {
        const response = await fetch(uri);
        return await response.blob();
      }));

      await enrollBackendSpeaker({
        name: formData.name,
        city: formData.city,
        newsCountry: formData.country,
        favoriteGenre: formData.musicGenre,
        audioBlobs: audioBlobs,
      });

      const ANIMAL_EMOJIS = ['🦁', '🦉', '🦊', '🦅', '🐺', '🐻', '🐼', '🦝', '🦌', '🦆'];
      const normalSpeakers = await getNormalSpeakers();
      const nextPriority = formData.needsAccessibility
        ? 0
        : Math.max(1, Math.min(5, normalSpeakers.length + 1));

      await addSpeaker({
        id: '0',
        name: formData.name,
        city: formData.city,
        country: formData.country,
        musicGenre: formData.musicGenre,
        priority: nextPriority,
        isAccessible: formData.needsAccessibility,
        icon: ANIMAL_EMOJIS[Math.floor(Math.random() * ANIMAL_EMOJIS.length)],
      });

      await refreshSpeakers();
      setShowRemovalModal(false);
      router.replace('/dashboard');
    } catch (err: any) {
      setSubmitError(err.message || 'Enrollment failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredModalSpeakers = formData.needsAccessibility 
    ? allSpeakers.filter(s => s.isAccessible) 
    : allSpeakers.filter(s => !s.isAccessible);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scrollContent}>
          
          <View style={styles.header}>
            <TouchableOpacity onPress={() => router.push('/dashboard')} style={styles.backButton}>
              <ArrowLeft color={COLORS.foreground} size={20} />
            </TouchableOpacity>
            <View>
              <Text style={styles.title}>Register New Speaker</Text>
              <Text style={styles.subtitle}>Add and manage speaker profiles with voice samples</Text>
            </View>
          </View>

          {/* Form Section */}
          <View style={styles.card}>
            {submitError ? (
              <View style={styles.errorBox}>
                <Text style={styles.errorText}>{submitError}</Text>
              </View>
            ) : null}

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Speaker Name</Text>
              <TextInput
                style={styles.input}
                placeholder="Enter speaker name"
                placeholderTextColor={COLORS.mutedForeground}
                value={formData.name}
                onChangeText={(t) => setFormData({...formData, name: t})}
              />
            </View>
            
            <View style={styles.inputGroup}>
              <Text style={styles.label}>City</Text>
              <TextInput
                style={styles.input}
                placeholder="Enter your city"
                placeholderTextColor={COLORS.mutedForeground}
                value={formData.city}
                onChangeText={(t) => setFormData({...formData, city: t})}
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Country</Text>
              <TextInput
                style={styles.input}
                placeholder="Enter your country"
                placeholderTextColor={COLORS.mutedForeground}
                value={formData.country}
                onChangeText={(t) => setFormData({...formData, country: t})}
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Favorite Music Genre</Text>
              {/* Using simple text input for simplicity, web uses native select which is hard in RN without external lib */}
              <TextInput
                style={styles.input}
                placeholder="Pop, Rock, Jazz..."
                placeholderTextColor={COLORS.mutedForeground}
                value={formData.musicGenre}
                onChangeText={(t) => setFormData({...formData, musicGenre: t})}
              />
            </View>

            <View style={styles.accessibilityBox}>
              <View style={styles.accessibilityHeader}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Accessibility Mode</Text>
                  <Text style={styles.accessibilityText}>For people with speech differences or challenges. You'll answer simple questions instead of reading scripts.</Text>
                </View>
                <Switch 
                  value={formData.needsAccessibility}
                  onValueChange={(val) => setFormData({...formData, needsAccessibility: val})}
                  trackColor={{ true: COLORS.primary }}
                />
              </View>
            </View>
          </View>

          {/* Recording Section */}
          <View style={[styles.card, { marginTop: SPACING.lg }]}>
            <Text style={styles.cardTitle}>Voice Samples</Text>
            
            {!formData.needsAccessibility ? (
              <View>
                {VOICE_SCRIPTS.map(s => {
                  const hasRecording = !!standardRecordings[s.id];
                  const isSelected = selectedScript === s.id;
                  
                  return (
                    <TouchableOpacity 
                      key={s.id} 
                      style={[
                        styles.scriptButton, 
                        isSelected && styles.scriptButtonSelected,
                        hasRecording && styles.scriptButtonRecorded
                      ]}
                      onPress={() => setSelectedScript(s.id)}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={styles.scriptLabel}>{s.label}</Text>
                        <Text style={styles.scriptInstruction}>{s.instruction}</Text>
                      </View>
                      {hasRecording && <CheckCircle2 color={COLORS.success} size={20} />}
                    </TouchableOpacity>
                  );
                })}

                {selectedScript && (
                  <View style={styles.recordingArea}>
                    <Text style={styles.scriptTextToRead}>{processedScript}</Text>
                    
                    {!standardRecordings[selectedScript] ? (
                      <View style={{ alignItems: 'center' }}>
                        {isRecording ? (
                          <TouchableOpacity style={styles.stopButton} onPress={() => stopRecording('standard')}>
                            <MicOff color="white" size={24} />
                            <Text style={styles.stopButtonText}>Stop ({recordingTime}s)</Text>
                          </TouchableOpacity>
                        ) : (
                          <TouchableOpacity style={styles.recordButton} onPress={() => startRecording('standard')}>
                            <Mic color={COLORS.primaryForeground} size={24} />
                            <Text style={styles.recordButtonText}>Start Recording</Text>
                          </TouchableOpacity>
                        )}
                      </View>
                    ) : (
                      <View style={styles.playbackControls}>
                        <TouchableOpacity style={styles.playButton} onPress={() => {
                          const uri = standardRecordings[selectedScript];
                          if (playingUri === uri && isPlaying) pausePlayback();
                          else playRecording(uri);
                        }}>
                          {playingUri === standardRecordings[selectedScript] && isPlaying ? 
                            <Pause color={COLORS.foreground} size={20} /> : 
                            <Play color={COLORS.foreground} size={20} />
                          }
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.playButton} onPress={stopPlayback}>
                          <Square color={COLORS.foreground} size={20} />
                        </TouchableOpacity>
                        <TouchableOpacity style={[styles.playButton, { borderColor: COLORS.destructive }]} onPress={() => deleteRecording('standard', selectedScript)}>
                          <X color={COLORS.destructive} size={20} />
                        </TouchableOpacity>
                      </View>
                    )}
                  </View>
                )}
              </View>
            ) : (
              <View>
                <Text style={styles.label}>Question {currentAccessibilityQuestion + 1} of 3</Text>
                <Text style={styles.scriptTextToRead}>{ACCESSIBILITY_QUESTIONS[currentAccessibilityQuestion]}</Text>
                
                {!accessibilityRecordings[currentAccessibilityQuestion] ? (
                  <View style={{ alignItems: 'center' }}>
                    {isRecording ? (
                      <TouchableOpacity style={styles.stopButton} onPress={() => stopRecording('accessibility')}>
                        <MicOff color="white" size={24} />
                        <Text style={styles.stopButtonText}>Stop ({recordingTime}s)</Text>
                      </TouchableOpacity>
                    ) : (
                      <TouchableOpacity style={styles.recordButton} onPress={() => startRecording('accessibility')}>
                        <Mic color={COLORS.primaryForeground} size={24} />
                        <Text style={styles.recordButtonText}>Start Recording</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                ) : (
                  <View style={styles.playbackControls}>
                    <TouchableOpacity style={styles.playButton} onPress={() => {
                      const uri = accessibilityRecordings[currentAccessibilityQuestion];
                      if (playingUri === uri && isPlaying) pausePlayback();
                      else playRecording(uri);
                    }}>
                      {playingUri === accessibilityRecordings[currentAccessibilityQuestion] && isPlaying ? 
                        <Pause color={COLORS.foreground} size={20} /> : 
                        <Play color={COLORS.foreground} size={20} />
                      }
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.playButton} onPress={stopPlayback}>
                      <Square color={COLORS.foreground} size={20} />
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.playButton, { borderColor: COLORS.destructive }]} onPress={() => deleteRecording('accessibility', currentAccessibilityQuestion)}>
                      <X color={COLORS.destructive} size={20} />
                    </TouchableOpacity>
                  </View>
                )}

                <View style={styles.navRow}>
                  <TouchableOpacity 
                    disabled={currentAccessibilityQuestion === 0}
                    onPress={() => setCurrentAccessibilityQuestion(prev => prev - 1)}
                    style={[styles.outlineButton, currentAccessibilityQuestion === 0 && { opacity: 0.5 }]}
                  >
                    <Text style={styles.outlineButtonText}>Previous</Text>
                  </TouchableOpacity>
                  
                  <TouchableOpacity 
                    disabled={currentAccessibilityQuestion === 2}
                    onPress={() => setCurrentAccessibilityQuestion(prev => prev + 1)}
                    style={[styles.outlineButton, currentAccessibilityQuestion === 2 && { opacity: 0.5 }]}
                  >
                    <Text style={styles.outlineButtonText}>Next</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
          </View>

          <View style={styles.submitSection}>
            <TouchableOpacity style={styles.outlineButton} onPress={() => router.push('/dashboard')}>
              <Text style={styles.outlineButtonText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.submitButton, isSubmitting && { opacity: 0.5 }]} 
              onPress={handleFormSubmit}
              disabled={isSubmitting}
            >
              <Text style={styles.submitButtonText}>{isSubmitting ? 'Enrolling...' : 'Confirm Add Voice'}</Text>
            </TouchableOpacity>
          </View>

        </ScrollView>
      </KeyboardAvoidingView>

      {/* Removal Modal */}
      <Modal visible={showRemovalModal} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{formData.needsAccessibility ? 'Accessibility Limit' : 'Speaker Limit'}</Text>
              <TouchableOpacity onPress={() => setShowRemovalModal(false)}><X color={COLORS.foreground} size={20}/></TouchableOpacity>
            </View>
            
            <Text style={styles.modalSubtitle}>
              {formData.needsAccessibility 
                ? 'Only 1 accessibility speaker allowed. Select the speaker to replace.' 
                : 'Maximum 5 speakers reached. Select one to remove.'}
            </Text>

            <ScrollView style={{ maxHeight: 200, marginVertical: SPACING.md }}>
              {filteredModalSpeakers.map(s => (
                <TouchableOpacity 
                  key={s.id} 
                  style={[styles.modalItem, selectedSpeakerToRemove === s.id && styles.modalItemSelected]}
                  onPress={() => setSelectedSpeakerToRemove(s.id)}
                >
                  <Text style={styles.modalItemName}>{s.name}</Text>
                  <Text style={styles.modalItemDesc}>{s.isAccessible ? 'Accessible' : `Priority ${s.priority}`}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            <View style={styles.navRow}>
              <TouchableOpacity style={styles.outlineButton} onPress={() => setShowRemovalModal(false)}>
                <Text style={styles.outlineButtonText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                style={[styles.submitButton, !selectedSpeakerToRemove && { opacity: 0.5 }]} 
                disabled={!selectedSpeakerToRemove}
                onPress={() => completeAddSpeaker(selectedSpeakerToRemove!)}
              >
                <Text style={styles.submitButtonText}>Remove & Add New</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  scrollContent: {
    padding: SPACING.lg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: SPACING.xl,
    gap: SPACING.md,
  },
  backButton: {
    padding: SPACING.xs,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.foreground,
  },
  subtitle: {
    fontSize: 14,
    color: COLORS.mutedForeground,
  },
  card: {
    backgroundColor: COLORS.card,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 2,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: COLORS.foreground,
    marginBottom: SPACING.md,
  },
  inputGroup: {
    marginBottom: SPACING.md,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.foreground,
    marginBottom: SPACING.xs,
  },
  input: {
    backgroundColor: COLORS.secondary,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.md,
    fontSize: 16,
    color: COLORS.foreground,
  },
  accessibilityBox: {
    backgroundColor: COLORS.primary + '1A', // 10% opacity
    borderWidth: 2,
    borderColor: COLORS.primary + '4D', // 30%
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    marginTop: SPACING.sm,
  },
  accessibilityHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  accessibilityText: {
    fontSize: 12,
    color: COLORS.mutedForeground,
    marginTop: 4,
  },
  scriptButton: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: SPACING.md,
    borderWidth: 2,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    marginBottom: SPACING.sm,
  },
  scriptButtonSelected: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primary + '1A',
  },
  scriptButtonRecorded: {
    borderColor: COLORS.success,
    backgroundColor: COLORS.successLight,
  },
  scriptLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.foreground,
  },
  scriptInstruction: {
    fontSize: 12,
    color: COLORS.mutedForeground,
    marginTop: 2,
  },
  recordingArea: {
    backgroundColor: COLORS.secondary + '4D',
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    marginTop: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  scriptTextToRead: {
    fontSize: 16,
    lineHeight: 24,
    color: COLORS.foreground,
    marginBottom: SPACING.lg,
    fontStyle: 'italic',
  },
  recordButton: {
    backgroundColor: COLORS.primary,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: SPACING.md,
    paddingHorizontal: SPACING.xl,
    borderRadius: RADIUS.full,
    gap: SPACING.sm,
  },
  recordButtonText: {
    color: COLORS.primaryForeground,
    fontWeight: 'bold',
    fontSize: 16,
  },
  stopButton: {
    backgroundColor: COLORS.recordingRed,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: SPACING.md,
    paddingHorizontal: SPACING.xl,
    borderRadius: RADIUS.full,
    gap: SPACING.sm,
  },
  stopButtonText: {
    color: 'white',
    fontWeight: 'bold',
    fontSize: 16,
  },
  playbackControls: {
    flexDirection: 'row',
    gap: SPACING.sm,
    justifyContent: 'center',
  },
  playButton: {
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: SPACING.sm,
    borderRadius: RADIUS.md,
    backgroundColor: COLORS.card,
  },
  navRow: {
    flexDirection: 'row',
    gap: SPACING.sm,
    marginTop: SPACING.md,
  },
  outlineButton: {
    flex: 1,
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingVertical: SPACING.md,
    borderRadius: RADIUS.md,
    alignItems: 'center',
  },
  outlineButtonText: {
    color: COLORS.foreground,
    fontWeight: '600',
  },
  submitSection: {
    flexDirection: 'row',
    gap: SPACING.md,
    marginTop: SPACING.xl,
    marginBottom: SPACING.xl,
  },
  submitButton: {
    flex: 1,
    backgroundColor: COLORS.primary,
    paddingVertical: SPACING.md,
    borderRadius: RADIUS.md,
    alignItems: 'center',
  },
  submitButtonText: {
    color: COLORS.primaryForeground,
    fontWeight: 'bold',
    fontSize: 16,
  },
  errorBox: {
    backgroundColor: COLORS.recordingRedLight,
    borderWidth: 1,
    borderColor: '#fca5a5',
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    marginBottom: SPACING.md,
  },
  errorText: {
    color: '#991b1b',
    fontSize: 14,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    padding: SPACING.lg,
  },
  modalCard: {
    backgroundColor: COLORS.card,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: COLORS.foreground,
  },
  modalSubtitle: {
    fontSize: 14,
    color: COLORS.mutedForeground,
  },
  modalItem: {
    padding: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    marginBottom: SPACING.xs,
  },
  modalItemSelected: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primary + '1A',
  },
  modalItemName: {
    fontWeight: '600',
    color: COLORS.foreground,
  },
  modalItemDesc: {
    fontSize: 12,
    color: COLORS.mutedForeground,
  },
});
