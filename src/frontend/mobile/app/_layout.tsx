import { Stack } from 'expo-router';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  // Using system fonts for now as we don't have the custom font files locally
  // In a real app we would load them here via useFonts
  const [loaded] = useFonts({
    // ComicRelief: require('../assets/fonts/ComicRelief.ttf'),
    // ComicReliefBold: require('../assets/fonts/ComicRelief-Bold.ttf'),
    // Manrope: require('../assets/fonts/Manrope.ttf'),
    // Mulish: require('../assets/fonts/Mulish.ttf'),
  });

  useEffect(() => {
    // Faking font load for now
    SplashScreen.hideAsync();
  }, []);

  return (
    <SafeAreaProvider>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="login" />
        <Stack.Screen name="signup" />
        <Stack.Screen name="dashboard" />
        <Stack.Screen name="add-speaker" />
        <Stack.Screen name="manage-speakers" />
        <Stack.Screen name="customize-wakeword" />
      </Stack>
    </SafeAreaProvider>
  );
}
