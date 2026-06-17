import { useState, useRef, useEffect } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView, Alert, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Audio } from 'expo-av';
import { ArrowLeft, Mic, MicOff, Play, Pause, Square, CheckCircle2, X } from 'lucide-react-native';
import { COLORS, SPACING, RADIUS } from '../constants/theme';
import { changeBackendWakeword } from '../lib/api';

export default function CustomizeWakewordPage() {
  const router = useRouter();
  const [wakeword, setWakeword] = useState('');
  
  const [recordings, setRecordings] = useState<string[]>(['', '', '']);
  const [isRecording, setIsRecording] = useState(false);
  const [currentRecordingIndex, setCurrentRecordingIndex] = useState<number | null>(null);
  
  const [recordingObj, setRecordingObj] = useState<Audio.Recording | null>(null);
  const [recordingTime, setRecordingTime] = useState(0);
  
  const [sound, setSound] = useState<Audio.Sound | null>(null);
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return sound ? () => { sound.unloadAsync(); } : undefined;
  }, [sound]);

  const startRecording = async (index: number) => {
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
      setRecordingObj(recording);
      setIsRecording(true);
      setCurrentRecordingIndex(index);
      setRecordingTime(0);

      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      console.error('Failed to start recording', err);
    }
  };

  const stopRecording = async () => {
    if (!recordingObj || currentRecordingIndex === null) return;

    if (timerRef.current) clearInterval(timerRef.current);
    
    await recordingObj.stopAndUnloadAsync();
    const uri = recordingObj.getURI();
    setRecordingObj(null);
    setIsRecording(false);

    if (uri) {
      const newRecs = [...recordings];
      newRecs[currentRecordingIndex] = uri;
      setRecordings(newRecs);
    }
    setCurrentRecordingIndex(null);
  };

  const playRecording = async (index: number) => {
    const uri = recordings[index];
    if (!uri) return;

    if (sound) {
      await sound.unloadAsync();
    }
    
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
      playsInSilentModeIOS: true,
    });

    const { sound: newSound } = await Audio.Sound.createAsync({ uri }, { shouldPlay: true });
    setSound(newSound);
    setPlayingIndex(index);
    setIsPlaying(true);

    newSound.setOnPlaybackStatusUpdate((status) => {
      if (status.isLoaded && status.didJustFinish) {
        setIsPlaying(false);
        setPlayingIndex(null);
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
      setPlayingIndex(null);
    }
  };

  const deleteRecording = (index: number) => {
    const newRecs = [...recordings];
    newRecs[index] = '';
    setRecordings(newRecs);
  };

  const handleSubmit = async () => {
    setSubmitError('');
    
    if (!wakeword.trim()) {
      setSubmitError('Please enter a wake word');
      return;
    }

    if (recordings.some(r => !r)) {
      setSubmitError('Please complete all 3 recordings');
      return;
    }

    setIsSubmitting(true);
    try {
      const audioBlobs = await Promise.all(recordings.map(async (uri) => {
        const response = await fetch(uri);
        return await response.blob();
      }));

      await changeBackendWakeword(audioBlobs);
      
      if (Platform.OS === 'web') {
        window.alert("Wake word successfully updated!");
        router.push('/dashboard');
      } else {
        Alert.alert(
          "Success",
          "Wake word successfully updated!",
          [{ text: "OK", onPress: () => router.push('/dashboard') }]
        );
      }
    } catch (err: any) {
      setSubmitError(err.message || 'Failed to update wake word');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.push('/dashboard')} style={styles.backButton}>
          <ArrowLeft color={COLORS.foreground} size={20} />
        </TouchableOpacity>
        <View>
          <Text style={styles.title}>Customize Wake Word</Text>
          <Text style={styles.subtitle}>Change the phrase Canary responds to</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent}>
        
        <View style={styles.card}>
          {submitError ? (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{submitError}</Text>
            </View>
          ) : null}

          <View style={styles.inputGroup}>
            <Text style={styles.label}>New Wake Word</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. Canary, Jarvis, Computer"
              placeholderTextColor={COLORS.mutedForeground}
              value={wakeword}
              onChangeText={setWakeword}
            />
            <Text style={styles.helperText}>
              Choose a distinct word or short phrase. Avoid very common words.
            </Text>
          </View>
        </View>

        <View style={[styles.card, { marginTop: SPACING.lg }]}>
          <Text style={styles.cardTitle}>Voice Samples</Text>
          <Text style={styles.cardDesc}>
            Record yourself saying "{wakeword || 'your wake word'}" 3 times to train the system.
          </Text>

          {[0, 1, 2].map(index => {
            const hasRecording = !!recordings[index];
            const isRecordingThis = isRecording && currentRecordingIndex === index;
            
            return (
              <View key={index} style={[styles.recordingRow, hasRecording && styles.recordingRowDone]}>
                <View style={styles.recordingInfo}>
                  <View style={[styles.recordingNumber, hasRecording && styles.recordingNumberDone]}>
                    <Text style={[styles.recordingNumberText, hasRecording && { color: COLORS.success }]}>
                      {index + 1}
                    </Text>
                  </View>
                  <Text style={styles.recordingLabel}>Sample {index + 1}</Text>
                  {hasRecording && <CheckCircle2 color={COLORS.success} size={16} style={{ marginLeft: SPACING.sm }} />}
                </View>

                {!hasRecording ? (
                  <View>
                    {isRecordingThis ? (
                      <TouchableOpacity style={styles.stopButton} onPress={stopRecording}>
                        <MicOff color="white" size={16} />
                        <Text style={styles.stopButtonText}>Stop</Text>
                      </TouchableOpacity>
                    ) : (
                      <TouchableOpacity 
                        style={[styles.recordButton, isRecording && !isRecordingThis && { opacity: 0.5 }]} 
                        onPress={() => startRecording(index)}
                        disabled={isRecording && !isRecordingThis}
                      >
                        <Mic color={COLORS.primaryForeground} size={16} />
                        <Text style={styles.recordButtonText}>Record</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                ) : (
                  <View style={styles.playbackControls}>
                    <TouchableOpacity style={styles.playButton} onPress={() => {
                      if (playingIndex === index && isPlaying) pausePlayback();
                      else playRecording(index);
                    }}>
                      {playingIndex === index && isPlaying ? 
                        <Pause color={COLORS.foreground} size={16} /> : 
                        <Play color={COLORS.foreground} size={16} />
                      }
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.playButton} onPress={stopPlayback}>
                      <Square color={COLORS.foreground} size={16} />
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.playButton, { borderColor: COLORS.destructive }]} onPress={() => deleteRecording(index)}>
                      <X color={COLORS.destructive} size={16} />
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            );
          })}
        </View>

        <View style={styles.submitSection}>
          <TouchableOpacity style={styles.outlineButton} onPress={() => router.push('/dashboard')}>
            <Text style={styles.outlineButtonText}>Cancel</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={[styles.submitButton, isSubmitting && { opacity: 0.5 }]} 
            onPress={handleSubmit}
            disabled={isSubmitting}
          >
            <Text style={styles.submitButtonText}>{isSubmitting ? 'Updating...' : 'Update Wake Word'}</Text>
          </TouchableOpacity>
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: SPACING.lg,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    backgroundColor: COLORS.card,
    gap: SPACING.md,
  },
  backButton: {
    padding: SPACING.xs,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: COLORS.foreground,
  },
  subtitle: {
    fontSize: 14,
    color: COLORS.mutedForeground,
  },
  scrollContent: {
    padding: SPACING.lg,
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
    marginBottom: SPACING.xs,
  },
  cardDesc: {
    fontSize: 14,
    color: COLORS.mutedForeground,
    marginBottom: SPACING.lg,
  },
  inputGroup: {
    marginBottom: SPACING.sm,
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
  helperText: {
    fontSize: 12,
    color: COLORS.mutedForeground,
    marginTop: 4,
  },
  recordingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    marginBottom: SPACING.md,
    backgroundColor: COLORS.secondary,
  },
  recordingRowDone: {
    backgroundColor: COLORS.successLight,
    borderColor: COLORS.success + '40',
  },
  recordingInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  recordingNumber: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: COLORS.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.sm,
  },
  recordingNumberDone: {
    backgroundColor: 'transparent',
  },
  recordingNumberText: {
    fontSize: 12,
    fontWeight: 'bold',
    color: COLORS.mutedForeground,
  },
  recordingLabel: {
    fontSize: 16,
    fontWeight: '500',
    color: COLORS.foreground,
  },
  recordButton: {
    backgroundColor: COLORS.primary,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: SPACING.sm,
    paddingHorizontal: SPACING.md,
    borderRadius: RADIUS.full,
    gap: 6,
  },
  recordButtonText: {
    color: COLORS.primaryForeground,
    fontWeight: 'bold',
    fontSize: 14,
  },
  stopButton: {
    backgroundColor: COLORS.recordingRed,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: SPACING.sm,
    paddingHorizontal: SPACING.md,
    borderRadius: RADIUS.full,
    gap: 6,
  },
  stopButtonText: {
    color: 'white',
    fontWeight: 'bold',
    fontSize: 14,
  },
  playbackControls: {
    flexDirection: 'row',
    gap: 6,
  },
  playButton: {
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 6,
    borderRadius: RADIUS.md,
    backgroundColor: COLORS.card,
  },
  submitSection: {
    flexDirection: 'row',
    gap: SPACING.md,
    marginTop: SPACING.xl,
    marginBottom: SPACING.xl,
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
});
