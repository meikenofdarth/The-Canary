import { LottieAssistant } from '@/components/lottie-assistant';

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen" style={{ backgroundColor: '#FFF8E7' }}>
      <LottieAssistant />
      <p className="mt-8 text-sm text-gray-400 opacity-60 pointer-events-none">
        Tap the sparrow or hold spacebar
      </p>
    </div>
  );
}
