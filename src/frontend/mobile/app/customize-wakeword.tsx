import { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Alert } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAudioRecorder, useAudioPlayer, AudioModule, RecordingPresets } from 'expo-audio';
import { ArrowLeft, Mic, MicOff, Play, Pause, Square, CheckCircle2, X } from 'lucide-react-native';
import { COLORS, SPACING, RADIUS } from '../constants/theme';
import { ENDPOINTS } from '../constants/api';

export default function CustomizeWakewordPage() {
  const router = useRouter();
  const [recordings, setRecordings] = useState<(string | null)[]>([null, null, null]);
  const [isRecording, setIsRecording] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);

  const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const player = useAudioPlayer(null);

  const startRecording = async (index: number) => {
    const perm = await AudioModule.requestRecordingPermissionsAsync();
    if (!perm.granted) { Alert.alert('Permission Required', 'Microphone access is needed.'); return; }
    await audioRecorder.prepareToRecordAsync();
    audioRecorder.record();
    setIsRecording(true);
    setActiveIndex(index);
  };

  const stopRecording = async () => {
    await audioRecorder.stop();
    const uri = audioRecorder.uri;
    if (uri && activeIndex !== null) {
      setRecordings(prev => { const n = [...prev]; n[activeIndex] = uri; return n; });
    }
    setIsRecording(false);
    setActiveIndex(null);
  };

  const deleteRecording = (index: number) => {
    if (playingIndex === index) { player.pause(); setPlayingIndex(null); }
    setRecordings(prev => { const n = [...prev]; n[index] = null; return n; });
  };

  const togglePlay = (index: number) => {
    const uri = recordings[index];
    if (!uri) return;
    if (playingIndex === index) {
      player.playing ? player.pause() : player.play();
    } else {
      player.replace({ uri });
      player.play();
      setPlayingIndex(index);
    }
  };

  const stopPlayback = () => { player.pause(); setPlayingIndex(null); };

  // Use XMLHttpRequest — React Native's fetch doesn't support { uri, type, name } FormData reliably
  const handleSubmit = async () => {
    if (recordings.some(r => !r)) { setError('Please complete all 3 recordings'); return; }
    setError('');
    setIsSubmitting(true);
    try {
      await new Promise<void>((resolve, reject) => {
        const fd = new FormData();
        recordings.forEach((uri, i) => {
          fd.append('audio_files', { uri: uri!, type: 'audio/m4a', name: `wakeword_${i + 1}.m4a` } as any);
        });
        const xhr = new XMLHttpRequest();
        xhr.open('POST', ENDPOINTS.changeWakeword);
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            const data = JSON.parse(xhr.responseText);
            Alert.alert('Success', `Wake word set to "${data.word}"!`, [
              { text: 'OK', onPress: () => router.push('/dashboard') },
            ]);
            resolve();
          } else {
            let msg = `HTTP ${xhr.status}`;
            try { msg = JSON.parse(xhr.responseText).detail || msg; } catch {}
            reject(new Error(msg));
          }
        };
        xhr.onerror = () => reject(new Error('Network error. Check your connection.'));
        xhr.send(fd);
      });
    } catch (err: any) {
      setError(err.message || 'Failed to update wake word');
    } finally {
      setIsSubmitting(false);
    }
  };

  const allDone = recordings.every(Boolean);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.push('/dashboard')} style={styles.backBtn}>
          <ArrowLeft color={COLORS.foreground} size={20} />
        </TouchableOpacity>
        <View>
          <Text style={styles.title}>Customize Wake Word</Text>
          <Text style={styles.subtitle}>Change the phrase Canary responds to</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {!!error && <View style={styles.errorBox}><Text style={styles.errorText}>{error}</Text></View>}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Voice Samples</Text>
          <Text style={styles.cardDesc}>Record yourself saying your chosen wake word 3 times to train the system.</Text>

          {[0, 1, 2].map(index => {
            const uri = recordings[index];
            const isThis = isRecording && activeIndex === index;
            const isThisPlaying = playingIndex === index;

            return (
              <View key={index} style={[styles.row, !!uri && styles.rowDone]}>
                <View style={styles.rowLeft}>
                  <View style={[styles.badge, !!uri && styles.badgeDone]}>
                    <Text style={[styles.badgeText, !!uri && { color: COLORS.success }]}>{index + 1}</Text>
                  </View>
                  <Text style={styles.rowLabel}>Sample {index + 1}</Text>
                  {!!uri && <CheckCircle2 color={COLORS.success} size={16} style={{ marginLeft: 8 }} />}
                </View>

                {!uri ? (
                  isThis ? (
                    <TouchableOpacity style={styles.stopBtn} onPress={stopRecording}>
                      <MicOff color="#fff" size={16} /><Text style={styles.stopBtnText}>Stop</Text>
                    </TouchableOpacity>
                  ) : (
                    <TouchableOpacity style={[styles.recBtn, isRecording && { opacity: 0.4 }]}
                      onPress={() => startRecording(index)} disabled={isRecording}>
                      <Mic color={COLORS.primaryForeground} size={16} /><Text style={styles.recBtnText}>Record</Text>
                    </TouchableOpacity>
                  )
                ) : (
                  <View style={styles.playbackRow}>
                    <TouchableOpacity style={styles.playBtn} onPress={() => togglePlay(index)}>
                      {isThisPlaying && player.playing
                        ? <Pause color={COLORS.foreground} size={16} />
                        : <Play color={COLORS.foreground} size={16} />}
                    </TouchableOpacity>
                    {isThisPlaying && (
                      <TouchableOpacity style={styles.playBtn} onPress={stopPlayback}>
                        <Square color={COLORS.foreground} size={16} />
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity style={styles.deleteBtn} onPress={() => deleteRecording(index)}>
                      <X color={COLORS.destructive} size={16} />
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            );
          })}
        </View>

        <View style={styles.actions}>
          <TouchableOpacity style={styles.cancelBtn} onPress={() => router.push('/dashboard')}>
            <Text style={styles.cancelText}>Cancel</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.submitBtn, (!allDone || isSubmitting) && { opacity: 0.5 }]}
            onPress={handleSubmit} disabled={!allDone || isSubmitting}>
            <Text style={styles.submitText}>{isSubmitting ? 'Updating...' : 'Update Wake Word'}</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.md,
    padding: SPACING.lg, borderBottomWidth: 1, borderBottomColor: COLORS.border,
    backgroundColor: COLORS.card,
  },
  backBtn: { padding: SPACING.xs },
  title: { fontSize: 20, fontWeight: 'bold', color: COLORS.foreground },
  subtitle: { fontSize: 14, color: COLORS.mutedForeground },
  content: { padding: SPACING.lg },
  errorBox: {
    backgroundColor: COLORS.recordingRedLight, borderWidth: 1, borderColor: '#fca5a5',
    padding: SPACING.md, borderRadius: RADIUS.md, marginBottom: SPACING.md,
  },
  errorText: { color: '#991b1b', fontSize: 14 },
  card: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.lg,
    borderWidth: 1, borderColor: COLORS.border,
  },
  cardTitle: { fontSize: 18, fontWeight: 'bold', color: COLORS.foreground, marginBottom: 4 },
  cardDesc: { fontSize: 14, color: COLORS.mutedForeground, marginBottom: SPACING.lg },
  row: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    padding: SPACING.md, borderWidth: 1, borderColor: COLORS.border,
    borderRadius: RADIUS.md, marginBottom: SPACING.md, backgroundColor: COLORS.secondary,
  },
  rowDone: { backgroundColor: COLORS.successLight, borderColor: COLORS.success + '40' },
  rowLeft: { flexDirection: 'row', alignItems: 'center' },
  badge: {
    width: 24, height: 24, borderRadius: 12, backgroundColor: COLORS.border,
    alignItems: 'center', justifyContent: 'center', marginRight: SPACING.sm,
  },
  badgeDone: { backgroundColor: 'transparent' },
  badgeText: { fontSize: 12, fontWeight: 'bold', color: COLORS.mutedForeground },
  rowLabel: { fontSize: 16, fontWeight: '500', color: COLORS.foreground },
  recBtn: {
    backgroundColor: COLORS.primary, flexDirection: 'row', alignItems: 'center',
    paddingVertical: SPACING.sm, paddingHorizontal: SPACING.md, borderRadius: RADIUS.full, gap: 6,
  },
  recBtnText: { color: COLORS.primaryForeground, fontWeight: 'bold', fontSize: 14 },
  stopBtn: {
    backgroundColor: COLORS.recordingRed, flexDirection: 'row', alignItems: 'center',
    paddingVertical: SPACING.sm, paddingHorizontal: SPACING.md, borderRadius: RADIUS.full, gap: 6,
  },
  stopBtnText: { color: '#fff', fontWeight: 'bold', fontSize: 14 },
  playbackRow: { flexDirection: 'row', gap: 6, alignItems: 'center' },
  playBtn: {
    borderWidth: 1, borderColor: COLORS.border, padding: 8,
    borderRadius: RADIUS.md, backgroundColor: COLORS.card,
  },
  deleteBtn: {
    borderWidth: 1, borderColor: COLORS.destructive, padding: 8,
    borderRadius: RADIUS.md, backgroundColor: COLORS.recordingRedLight,
  },
  actions: { flexDirection: 'row', gap: SPACING.md, marginTop: SPACING.xl, marginBottom: SPACING.xl },
  cancelBtn: {
    flex: 1, borderWidth: 1, borderColor: COLORS.border,
    paddingVertical: SPACING.md, borderRadius: RADIUS.md, alignItems: 'center',
  },
  cancelText: { color: COLORS.foreground, fontWeight: '600' },
  submitBtn: {
    flex: 1, backgroundColor: COLORS.primary,
    paddingVertical: SPACING.md, borderRadius: RADIUS.md, alignItems: 'center',
  },
  submitText: { color: COLORS.primaryForeground, fontWeight: 'bold', fontSize: 16 },
});
