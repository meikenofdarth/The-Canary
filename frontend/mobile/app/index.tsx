import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Image } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, SPACING, RADIUS } from '../constants/theme';
import { ArrowRight } from 'lucide-react-native';

export default function LandingPage() {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        
        {/* Hero Section */}
        <View style={styles.hero}>
          <Image 
            source={{ uri: 'https://hebbkx1anhila5yf.public.blob.vercel-storage.com/logo-rod6oexWJWuQxyR1VHbFvYyBq59vIN.png' }} 
            style={styles.logo} 
          />
          <Text style={styles.title}>The Canary</Text>
          <Text style={styles.subtitle}>
            A complete voice intelligence pipeline, from microphone to action. Manage, record, and prioritize your voice assistants.
          </Text>
          
          <TouchableOpacity 
            style={styles.button} 
            onPress={() => router.push('/login')}
          >
            <Text style={styles.buttonText}>Get Started</Text>
            <ArrowRight color={COLORS.primaryForeground} size={20} />
          </TouchableOpacity>
        </View>

        {/* Features Section */}
        <View style={styles.features}>
          <Text style={styles.featuresTitle}>What The Canary Does</Text>
          
          <View style={styles.featureCard}>
            <View style={styles.badge}><Text style={styles.badgeText}>01</Text></View>
            <Text style={styles.featureCardTitle}>Source Separation</Text>
            <Text style={styles.featureCardText}>Isolates target speech from background noise and other overlapping speakers.</Text>
          </View>

          <View style={styles.featureCard}>
            <View style={styles.badge}><Text style={styles.badgeText}>02</Text></View>
            <Text style={styles.featureCardTitle}>Voice Identity</Text>
            <Text style={styles.featureCardText}>Verifies the speaker's identity using advanced biometric embeddings.</Text>
          </View>

          <View style={styles.featureCard}>
            <View style={styles.badge}><Text style={styles.badgeText}>03</Text></View>
            <Text style={styles.featureCardTitle}>Arbitration</Text>
            <Text style={styles.featureCardText}>Resolves conflicts and decides which command to execute based on priority.</Text>
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
  scrollContent: {
    padding: SPACING.md,
  },
  hero: {
    alignItems: 'center',
    paddingVertical: SPACING.xl * 2,
  },
  logo: {
    width: 80,
    height: 80,
    marginBottom: SPACING.lg,
  },
  title: {
    fontSize: 48,
    fontWeight: 'bold',
    color: COLORS.foreground,
    marginBottom: SPACING.sm,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 18,
    color: COLORS.mutedForeground,
    textAlign: 'center',
    marginBottom: SPACING.xl,
    paddingHorizontal: SPACING.md,
  },
  button: {
    backgroundColor: COLORS.primary,
    paddingHorizontal: SPACING.xl,
    paddingVertical: SPACING.md,
    borderRadius: RADIUS.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.sm,
    shadowColor: COLORS.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 5,
  },
  buttonText: {
    color: COLORS.primaryForeground,
    fontSize: 18,
    fontWeight: '600',
  },
  features: {
    marginTop: SPACING.xl,
    backgroundColor: COLORS.secondary,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
  },
  featuresTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.foreground,
    marginBottom: SPACING.lg,
    textAlign: 'center',
  },
  featureCard: {
    backgroundColor: COLORS.card,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    marginBottom: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  badge: {
    backgroundColor: COLORS.primary + '33', // 20% opacity
    width: 32,
    height: 32,
    borderRadius: RADIUS.sm,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: SPACING.sm,
  },
  badgeText: {
    color: COLORS.foreground,
    fontWeight: 'bold',
  },
  featureCardTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: COLORS.foreground,
    marginBottom: SPACING.xs,
  },
  featureCardText: {
    color: COLORS.mutedForeground,
    lineHeight: 22,
  },
});
