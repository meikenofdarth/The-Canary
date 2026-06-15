'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

const chartData = [
  { time: '00:00', commands: 240 },
  { time: '04:00', commands: 380 },
  { time: '08:00', commands: 1200 },
  { time: '12:00', commands: 2840 },
  { time: '16:00', commands: 2340 },
  { time: '20:00', commands: 3100 },
  { time: '23:59', commands: 1850 },
];

export function UsageChart() {
  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-foreground">Voice Commands vs Time</h2>
      

      <div className="mt-6">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e0d8" />
            <XAxis
              dataKey="time"
              stroke="#6b7280"
              style={{ fontSize: '12px' }}
            />
            <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#ffffff',
                border: '1px solid #e5e0d8',
                borderRadius: '8px',
              }}
              labelStyle={{ color: '#1a1a1a' }}
            />
            <Line
              type="monotone"
              dataKey="commands"
              stroke="#fcd34d"
              strokeWidth={3}
              dot={{ fill: '#fcd34d', r: 5 }}
              activeDot={{ r: 7 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
