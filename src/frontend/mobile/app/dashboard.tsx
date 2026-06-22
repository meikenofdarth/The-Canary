import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { COLORS, SPACING, RADIUS } from '../constants/theme';
import { DashboardNavbar } from '../components/DashboardNavbar';
import { SpeakersList } from '../components/SpeakersList';
import { UsageChart } from '../components/UsageChart';
import { fetchSystemStatus } from '../lib/api';
import { refreshSpeakers } from '../lib/speakers-store';
import { Settings, List, Plus } from 'lucide-react-native';

export default function DashboardPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(true);
  const [status, setStatus] = useState({
    active_wakeword: 'canary',
    enrolled_users: 0,
    status: 'Online'
  });

  useEffect(() => {
    const init = async () => {
      const loggedIn = await AsyncStorage.getItem('isLoggedIn');
      if (!loggedIn) {
        router.replace('/login');
        return;
      }

      try {
        await refreshSpeakers();
        const sysStatus = await fetchSystemStatus();
        setStatus(sysStatus);
      } catch (err) {
        console.error('Failed to fetch status', err);
      } finally {
        setIsLoading(false);
      }
    };

    init();
    
    // Poll every 15s
    const interval = setInterval(async () => {
      try {
        await refreshSpeakers();
        const sysStatus = await fetchSystemStatus();
        setStatus(sysStatus);
      } catch (err) {}
    }, 15000);
    
    return () => clearInterval(interval);
  }, []);

  if (isLoading) {
    return (
      <SafeAreaView style={[styles.container, styles.center]}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <DashboardNavbar />
      
      <ScrollView contentContainerStyle={styles.scrollContent}>
        
        <View style={styles.header}>
          <Text style={styles.title}>Dashboard</Text>
          <Text style={styles.subtitle}>Welcome back. Here's your voice assistant performance overview.</Text>
        </View>

        <View style={styles.actionsRow}>
          <TouchableOpacity 
            style={[styles.actionButton, styles.outlineButton]} 
            onPress={() => router.push('/customize-wakeword')}
          >
            <Settings color={COLORS.primary} size={18} />
            <Text style={styles.outlineButtonText}>Set Up Voice Profile</Text>
          </TouchableOpacity>
          
          <TouchableOpacity 
            style={[styles.actionButton, styles.outlineButton]} 
            onPress={() => router.push('/manage-speakers')}
          >
            <List color={COLORS.primary} size={18} />
            <Text style={styles.outlineButtonText}>Manage Speakers</Text>
          </TouchableOpacity>
          
          <TouchableOpacity 
            style={[styles.actionButton, styles.primaryButton]} 
            onPress={() => router.push('/add-speaker')}
          >
            <Plus color={COLORS.primaryForeground} size={18} />
            <Text style={styles.primaryButtonText}>Add Speaker</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.statsGrid}>
          <View style={styles.statCard}>
            <Text style={styles.statLabel}>Enrolled Speakers</Text>
            <Text style={styles.statValue}>{status.enrolled_users} / 5</Text>
          </View>
          
          <TouchableOpacity 
            style={styles.statCard}
            onPress={() => router.push('/customize-wakeword')}
          >
            <Text style={styles.statLabel}>Active Wake Word</Text>
            <Text style={styles.statValue}>"{status.active_wakeword}"</Text>
          </TouchableOpacity>
          
          <View style={styles.statCard}>
            <Text style={styles.statLabel}>Pipeline Status</Text>
            <Text style={[
              styles.statValue, 
              { color: status.status === 'Online' ? COLORS.success : COLORS.destructive }
            ]}>
              {status.status}
            </Text>
          </View>
          
          <View style={styles.statCard}>
            <Text style={styles.statLabel}>Capacity</Text>
            <Text style={styles.statValue}>{Math.max(0, 5 - status.enrolled_users)} free</Text>
          </View>
        </View>

        <View style={styles.mainGrid}>
          <UsageChart />
          
          <View style={styles.listContainer}>
            <SpeakersList />
          </View>
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
  center: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollContent: {
    padding: SPACING.lg,
  },
  header: {
    marginBottom: SPACING.lg,
  },
  title: {
    fontSize: 36,
    fontWeight: 'bold',
    color: COLORS.foreground,
    marginBottom: SPACING.xs,
  },
  subtitle: {
    fontSize: 16,
    color: COLORS.mutedForeground,
  },
  actionsRow: {
    flexDirection: 'column', // flex-col on small screens, can use flex-row if width allows
    gap: SPACING.md,
    marginBottom: SPACING.xl,
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: SPACING.sm,
    paddingVertical: SPACING.md,
    paddingHorizontal: SPACING.lg,
    borderRadius: RADIUS.md,
  },
  outlineButton: {
    borderWidth: 2,
    borderColor: COLORS.primary,
    backgroundColor: 'transparent',
  },
  outlineButtonText: {
    color: COLORS.primary,
    fontWeight: '600',
    fontSize: 14,
  },
  primaryButton: {
    backgroundColor: COLORS.primary,
  },
  primaryButtonText: {
    color: COLORS.primaryForeground,
    fontWeight: '600',
    fontSize: 14,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: SPACING.md,
    marginBottom: SPACING.xl,
  },
  statCard: {
    width: '47%', // 2 columns roughly
    backgroundColor: COLORS.card,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 2,
  },
  statLabel: {
    fontSize: 12,
    fontWeight: '500',
    color: COLORS.mutedForeground,
    marginBottom: SPACING.xs,
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.foreground,
  },
  mainGrid: {
    flexDirection: 'column',
    gap: SPACING.xl,
  },
  listContainer: {
    // Spans 1 column on web, here takes full width
  },
});
