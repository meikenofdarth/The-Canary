'use client';

import { useState } from 'react';

interface TimelineItem {
  id: number;
  title: string;
  description: string;
}

const timelineData: TimelineItem[] = [
  {
    id: 1,
    title: 'Capture & Denoise',
    description: 'Voice activity detection records until silence. Spectral filtering strips background noise before any analysis begins.',
  },
  {
    id: 2,
    title: 'Separate & Transcribe',
    description: 'Neural source separation splits overlapping voices into clean individual streams. Each stream is transcribed independently.',
  },
  {
    id: 3,
    title: 'Identify & Detect Wake Word',
    description: 'Speaker biometrics match each voice to an enrolled profile. A phonetic matcher catches natural variations of the wake word.',
  },
  {
    id: 4,
    title: 'Arbitrate & Execute',
    description: 'A priority engine weighs multiple signals to pick a winner — then fires the action against live services.',
  },
];

export function Timeline() {
  const [hoveredId, setHoveredId] = useState<number | null>(null);

  return (
    <div className="relative mx-auto max-w-5xl py-16">
      <div className="space-y-0">
        {timelineData.map((item, index) => {
          const isEven = index % 2 === 0;
          return (
            <div key={item.id} className="relative py-8">
              <div className="flex items-stretch gap-4">
                {/* Left spacer / box */}
                {isEven ? (
                  <>
                    <div
                      className={`flex flex-1 transition-all duration-300 ${
                        hoveredId === item.id ? 'scale-105' : ''
                      }`}
                      onMouseEnter={() => setHoveredId(item.id)}
                      onMouseLeave={() => setHoveredId(null)}
                    >
                      <div
                        className={`w-full rounded-lg border-2 p-6 transition-all duration-300 ${
                          hoveredId === item.id
                            ? 'border-primary bg-primary/10 shadow-lg shadow-primary/20'
                            : 'border-border bg-card'
                        }`}
                      >
                        <h3 className="text-lg font-semibold text-foreground">
                          {item.title}
                        </h3>
                        <p className="mt-2 text-sm text-muted-foreground">
                          {item.description}
                        </p>
                      </div>
                    </div>

                    {/* Center connector */}
                    <div className="flex w-8 flex-col items-center py-2">
                      <div className="h-3 w-3 rounded-full bg-primary" />
                      {index !== timelineData.length - 1 && (
                        <div className="mt-1 flex-1 w-0.5 bg-gradient-to-b from-primary to-primary/30" />
                      )}
                    </div>

                    {/* Right spacer */}
                    <div className="flex-1" />
                  </>
                ) : (
                  <>
                    {/* Left spacer */}
                    <div className="flex-1" />

                    {/* Center connector */}
                    <div className="flex w-8 flex-col items-center py-2">
                      <div className="h-3 w-3 rounded-full bg-primary" />
                      {index !== timelineData.length - 1 && (
                        <div className="mt-1 flex-1 w-0.5 bg-gradient-to-b from-primary to-primary/30" />
                      )}
                    </div>

                    {/* Right box */}
                    <div
                      className={`flex flex-1 transition-all duration-300 ${
                        hoveredId === item.id ? 'scale-105' : ''
                      }`}
                      onMouseEnter={() => setHoveredId(item.id)}
                      onMouseLeave={() => setHoveredId(null)}
                    >
                      <div
                        className={`w-full rounded-lg border-2 p-6 transition-all duration-300 ${
                          hoveredId === item.id
                            ? 'border-primary bg-primary/10 shadow-lg shadow-primary/20'
                            : 'border-border bg-card'
                        }`}
                      >
                        <h3 className="text-lg font-semibold text-foreground">
                          {item.title}
                        </h3>
                        <p className="mt-2 text-sm text-muted-foreground">
                          {item.description}
                        </p>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
