"use client";

import { useState, useRef } from "react";
import { Mic, MicOff, Loader2, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { sendBackendCommand } from "@/lib/api";

type AssistantState = "idle" | "listening" | "processing" | "speaking";

export default function AssistantPage() {
  const [state, setState] = useState<AssistantState>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);

  const startRecording = async () => {
    try {
      setErrorMsg("");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder.current = new MediaRecorder(stream, { mimeType: "audio/webm" });
      audioChunks.current = [];

      mediaRecorder.current.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.current.push(e.data);
      };

      mediaRecorder.current.onstop = async () => {
        const audioBlob = new Blob(audioChunks.current, { type: "audio/webm" });
        await processAudio(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.current.start();
      setState("listening");
    } catch (err) {
      console.error("Error accessing microphone:", err);
      setErrorMsg("Could not access microphone.");
      setState("idle");
    }
  };

  const stopRecording = () => {
    if (mediaRecorder.current && mediaRecorder.current.state === "recording") {
      mediaRecorder.current.stop();
      setState("processing");
    }
  };

  const processAudio = async (audioBlob: Blob) => {
    try {
      const result = await sendBackendCommand(audioBlob);
      
      if (result.route === "IGNORE" || result.route === "CLARIFY") {
        setErrorMsg("Audio ignored (no wake word or command found).");
        setState("idle");
        return;
      }

      const message = result.execution_result?.message;
      if (message) {
        speakResponse(message);
      } else {
        setState("idle");
      }
    } catch (err: any) {
      console.error("Command processing failed:", err);
      setErrorMsg(err.message || "Failed to process command.");
      setState("idle");
    }
  };

  const speakResponse = (text: string) => {
    setState("speaking");
    const utterance = new SpeechSynthesisUtterance(text);
    
    utterance.onend = () => {
      setState("idle");
    };
    
    utterance.onerror = () => {
      setState("idle");
    };

    window.speechSynthesis.speak(utterance);
  };

  const handleTap = () => {
    if (state === "idle" || state === "speaking") {
      window.speechSynthesis.cancel();
      startRecording();
    } else if (state === "listening") {
      stopRecording();
    }
  };

  let iconClass = "text-yellow-400";
  let ringClass = "ring-yellow-400/20";
  let bgClass = "bg-yellow-50";
  
  if (state === "listening") {
    iconClass = "text-red-500 animate-pulse";
    ringClass = "ring-red-500/30 animate-pulse";
    bgClass = "bg-red-50";
  } else if (state === "processing") {
    iconClass = "text-blue-500 animate-spin";
    ringClass = "ring-blue-500/30";
    bgClass = "bg-blue-50";
  } else if (state === "speaking") {
    iconClass = "text-green-500";
    ringClass = "ring-green-500/30 animate-pulse";
    bgClass = "bg-green-50";
  }

  return (
    <main className="min-h-screen bg-gray-50 flex flex-col items-center justify-center relative">
      <div className="absolute top-8 left-8">
        <Link 
          href="/dashboard"
          className="text-gray-500 hover:text-gray-900 flex items-center gap-2 transition-colors font-mulish"
        >
          <ArrowLeft className="w-5 h-5" />
          Back to Dashboard
        </Link>
      </div>

      <div className="flex flex-col items-center justify-center max-w-md w-full px-6">
        <button
          onClick={handleTap}
          disabled={state === "processing"}
          className={`
            relative flex items-center justify-center w-48 h-48 rounded-full 
            shadow-xl transition-all duration-300 transform hover:scale-105 active:scale-95
            ring-8 ${ringClass} ${bgClass}
          `}
        >
          {state === "processing" ? (
            <Loader2 className={`w-20 h-20 ${iconClass}`} />
          ) : (
            <Mic className={`w-20 h-20 ${iconClass}`} />
          )}
        </button>

        <div className="mt-12 text-center h-16">
          <h2 className="text-2xl font-manrope text-gray-800 tracking-tight">
            {state === "idle" && "Tap to talk"}
            {state === "listening" && "Listening..."}
            {state === "processing" && "Thinking..."}
            {state === "speaking" && "Speaking..."}
          </h2>
          {state === "listening" && (
            <p className="text-sm text-gray-500 mt-2 font-mulish">
              Tap again when you're done
            </p>
          )}
        </div>

        {errorMsg && (
          <div className="mt-8 p-4 bg-red-50 text-red-600 rounded-xl text-sm font-mulish text-center border border-red-100">
            {errorMsg}
          </div>
        )}
      </div>
    </main>
  );
}
