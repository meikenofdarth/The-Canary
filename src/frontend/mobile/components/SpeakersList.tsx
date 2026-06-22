import { useEffect, useState } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Speaker, getSpeakers } from '../lib/speakers-store';
import { COLORS, SPACING, RADIUS } from '../constants/theme';

export function SpeakersList() {
  const [speakers, setSpeakers] = useState<Speaker[]>([]);

  useEffect(() => {
    const loadSpeakers = async () => {
      const data = await getSpeakers();
      setSpeakers(data.sort((a, b) => b.priority - a.priority));
    };
    loadSpeakers();
    
    // In a real app we'd want to listen for updates or poll here
    const interval = setInterval(loadSpeakers, 15000);
    return () => clearInterval(interval);
  }, []);

  const normalSpeakers = speakers.filter(s => !s.isAccessible);
  const accessibleSpeaker = speakers.find(s => s.isAccessible);

  if (speakers.length === 0) {
    return (
      <View style={styles.card}>
        <Text style={styles.title}>Enrolled speakers in the database</Text>
        <View style={styles.emptyState}>
          <Text style={styles.emptyText}>No speakers enrolled yet.</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Enrolled speakers in the database</Text>
      
      {normalSpeakers.map((speaker, i) => (
        <View key={speaker.id || i} style={styles.row}>
          <Text style={styles.icon}>{speaker.icon}</Text>
          <View style={styles.info}>
            <Text style={styles.name} numberOfLines={1}>{speaker.name}</Text>
            <Text style={styles.details}>Priority {speaker.priority} • {speaker.city || 'Unknown'}</Text>
          </View>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{speaker.recordingCount || 0} rec</Text>
          </View>
        </View>
      ))}

      {accessibleSpeaker && (
        <View style={[styles.row, styles.accessibleRow]}>
          <Text style={styles.icon}>➕</Text>
          <View style={styles.info}>
            <Text style={styles.name} numberOfLines={1}>{accessibleSpeaker.name}</Text>
            <Text style={styles.details}>{accessibleSpeaker.city || 'Unknown'}</Text>
          </View>
          <View style={styles.specialBadge}>
            <Text style={styles.specialBadgeText}>Special</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: COLORS.card,
    borderRadius: RADIUS.xl,
    padding: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 2,
  },
  title: {
    fontSize: 12,
    color: COLORS.mutedForeground,
    marginBottom: SPACING.md,
    textTransform: 'uppercase',
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
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.secondary + '4D', // 30% opacity
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: SPACING.sm,
  },
  accessibleRow: {
    borderColor: COLORS.primary + '66', // 40%
    backgroundColor: COLORS.primary + '0D', // 5%
  },
  icon: {
    fontSize: 24,
    marginRight: SPACING.md,
  },
  info: {
    flex: 1,
  },
  name: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.foreground,
  },
  details: {
    fontSize: 12,
    color: COLORS.mutedForeground,
  },
  badge: {
    backgroundColor: COLORS.successLight,
    paddingHorizontal: SPACING.md,
    paddingVertical: 4,
    borderRadius: RADIUS.full,
  },
  badgeText: {
    color: COLORS.successText,
    fontSize: 12,
    fontWeight: '600',
  },
  specialBadge: {
    backgroundColor: COLORS.scheduledLight,
    paddingHorizontal: SPACING.md,
    paddingVertical: 4,
    borderRadius: RADIUS.full,
  },
  specialBadgeText: {
    color: COLORS.scheduledText,
    fontSize: 12,
    fontWeight: '600',
  },
});
