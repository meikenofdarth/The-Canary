import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Alert, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ArrowLeft, Trash2, ArrowUp, ArrowDown } from 'lucide-react-native';
import { COLORS, SPACING, RADIUS } from '../constants/theme';
import { Speaker, getSpeakers, deleteSpeaker, changePriority } from '../lib/speakers-store';

export default function ManageSpeakersPage() {
  const router = useRouter();
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const loadSpeakers = async () => {
    setIsLoading(true);
    const data = await getSpeakers();
    setSpeakers(data.sort((a, b) => b.priority - a.priority));
    setIsLoading(false);
  };

  useEffect(() => {
    loadSpeakers();
  }, []);

  const handleDelete = (speaker: Speaker) => {
    if (Platform.OS === 'web') {
      if (window.confirm(`Are you sure you want to remove ${speaker.name}? This will delete their voice embeddings.`)) {
        deleteSpeaker(speaker.id)
          .then(() => loadSpeakers())
          .catch(() => window.alert('Failed to remove speaker'));
      }
    } else {
      Alert.alert(
        "Remove Speaker",
        `Are you sure you want to remove ${speaker.name}? This will delete their voice embeddings.`,
        [
          { text: "Cancel", style: "cancel" },
          { 
            text: "Remove", 
            style: "destructive",
            onPress: async () => {
              try {
                await deleteSpeaker(speaker.id);
                await loadSpeakers();
              } catch (err) {
                Alert.alert('Error', 'Failed to remove speaker');
              }
            }
          }
        ]
      );
    }
  };

  const handlePriorityChange = async (speakerId: string, currentPriority: number, direction: 'up' | 'down') => {
    const newPriority = direction === 'up' ? currentPriority + 1 : currentPriority - 1;
    if (newPriority < 1 || newPriority > 5) return;
    
    try {
      await changePriority(speakerId, newPriority);
      await loadSpeakers();
    } catch (err) {
      console.error(err);
    }
  };

  const normalSpeakers = speakers.filter(s => !s.isAccessible);
  const accessibleSpeaker = speakers.find(s => s.isAccessible);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.push('/dashboard')} style={styles.backButton}>
          <ArrowLeft color={COLORS.foreground} size={20} />
        </TouchableOpacity>
        <View>
          <Text style={styles.title}>Manage Speakers</Text>
          <Text style={styles.subtitle}>Prioritize speakers or remove old profiles</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent}>
        
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>Priority System</Text>
          <Text style={styles.infoText}>
            When multiple people speak at once, the system listens to the person with the highest priority (5 is highest, 1 is lowest).
          </Text>
        </View>

        {accessibleSpeaker && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Accessibility Profile (Highest Priority)</Text>
            <View style={[styles.speakerCard, styles.accessibleCard]}>
              <View style={styles.speakerInfo}>
                <Text style={styles.icon}>➕</Text>
                <View>
                  <Text style={styles.name}>{accessibleSpeaker.name}</Text>
                  <Text style={styles.details}>Special Access • {accessibleSpeaker.city || 'Unknown'}</Text>
                </View>
              </View>
              <TouchableOpacity style={styles.deleteBtn} onPress={() => handleDelete(accessibleSpeaker)}>
                <Trash2 color={COLORS.destructive} size={20} />
              </TouchableOpacity>
            </View>
          </View>
        )}

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Standard Profiles</Text>
          
          {isLoading ? (
            <Text style={styles.loadingText}>Loading...</Text>
          ) : normalSpeakers.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyText}>No standard speakers enrolled.</Text>
            </View>
          ) : (
            normalSpeakers.map((speaker) => (
              <View key={speaker.id} style={styles.speakerCard}>
                <View style={styles.speakerMain}>
                  <Text style={styles.icon}>{speaker.icon}</Text>
                  <View style={styles.infoCol}>
                    <Text style={styles.name}>{speaker.name}</Text>
                    <Text style={styles.details}>{speaker.city || 'Unknown'} • {speaker.recordingCount || 0} recs</Text>
                  </View>
                </View>
                
                <View style={styles.speakerActions}>
                  <View style={styles.priorityControl}>
                    <TouchableOpacity 
                      style={styles.priorityBtn} 
                      disabled={speaker.priority <= 1}
                      onPress={() => handlePriorityChange(speaker.id, speaker.priority, 'down')}
                    >
                      <ArrowDown color={speaker.priority <= 1 ? COLORS.mutedForeground : COLORS.foreground} size={16} />
                    </TouchableOpacity>
                    <View style={styles.priorityDisplay}>
                      <Text style={styles.priorityVal}>{speaker.priority}</Text>
                    </View>
                    <TouchableOpacity 
                      style={styles.priorityBtn}
                      disabled={speaker.priority >= 5}
                      onPress={() => handlePriorityChange(speaker.id, speaker.priority, 'up')}
                    >
                      <ArrowUp color={speaker.priority >= 5 ? COLORS.mutedForeground : COLORS.foreground} size={16} />
                    </TouchableOpacity>
                  </View>

                  <TouchableOpacity style={styles.deleteBtn} onPress={() => handleDelete(speaker)}>
                    <Trash2 color={COLORS.destructive} size={20} />
                  </TouchableOpacity>
                </View>
              </View>
            ))
          )}
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
  infoBox: {
    backgroundColor: COLORS.primary + '1A', // 10%
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.primary + '33', // 20%
    marginBottom: SPACING.xl,
  },
  infoTitle: {
    fontWeight: '600',
    color: COLORS.primary,
    marginBottom: SPACING.xs,
  },
  infoText: {
    fontSize: 14,
    color: COLORS.foreground,
    lineHeight: 20,
  },
  section: {
    marginBottom: SPACING.xl,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: COLORS.foreground,
    marginBottom: SPACING.md,
  },
  speakerCard: {
    backgroundColor: COLORS.card,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: SPACING.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: SPACING.md,
  },
  accessibleCard: {
    borderColor: COLORS.primary + '66',
    backgroundColor: COLORS.primary + '0D',
  },
  speakerMain: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    minWidth: 150,
  },
  icon: {
    fontSize: 28,
    marginRight: SPACING.md,
  },
  infoCol: {
    flex: 1,
  },
  name: {
    fontSize: 16,
    fontWeight: 'bold',
    color: COLORS.foreground,
  },
  details: {
    fontSize: 12,
    color: COLORS.mutedForeground,
  },
  speakerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.md,
  },
  priorityControl: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.secondary,
    borderRadius: RADIUS.full,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 2,
  },
  priorityBtn: {
    padding: SPACING.xs,
  },
  priorityDisplay: {
    width: 24,
    alignItems: 'center',
  },
  priorityVal: {
    fontWeight: 'bold',
    color: COLORS.foreground,
  },
  deleteBtn: {
    padding: SPACING.sm,
    backgroundColor: COLORS.recordingRedLight,
    borderRadius: RADIUS.md,
  },
  loadingText: {
    color: COLORS.mutedForeground,
  },
  emptyState: {
    padding: SPACING.xl,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
  },
  emptyText: {
    color: COLORS.mutedForeground,
  },
  speakerInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  }
});
