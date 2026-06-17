import { View, Text, StyleSheet, TouchableOpacity, Image } from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { LogOut } from 'lucide-react-native';
import { COLORS, SPACING, RADIUS } from '../constants/theme';

export function DashboardNavbar() {
  const router = useRouter();

  const handleLogout = async () => {
    await AsyncStorage.removeItem('isLoggedIn');
    await AsyncStorage.removeItem('phoneNumber');
    router.replace('/login');
  };

  return (
    <View style={styles.container}>
      <TouchableOpacity onPress={() => router.push('/')} style={styles.logoContainer}>
        <Image 
          source={{ uri: 'https://hebbkx1anhila5yf.public.blob.vercel-storage.com/logo-rod6oexWJWuQxyR1VHbFvYyBq59vIN.png' }} 
          style={styles.logo} 
        />
      </TouchableOpacity>
      
      <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
        <Text style={styles.logoutText}>Logout</Text>
        <LogOut color={COLORS.foreground} size={16} />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
    backgroundColor: COLORS.card,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  logoContainer: {
    padding: SPACING.xs,
  },
  logo: {
    width: 32,
    height: 32,
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.xs,
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm,
    borderRadius: RADIUS.md,
  },
  logoutText: {
    color: COLORS.foreground,
    fontSize: 14,
    fontWeight: '600',
  },
});
