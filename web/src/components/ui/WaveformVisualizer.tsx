// WaveformVisualizer — animated audio waveform bars
interface WaveformVisualizerProps {
  bars?: number
  color?: string
  height?: number
  active?: boolean
  className?: string
}

export default function WaveformVisualizer({
  bars = 16,
  color = '#7B61FF',
  height = 32,
  active = true,
  className = '',
}: WaveformVisualizerProps) {
  const delays = [0, 0.15, 0.3, 0.08, 0.22, 0.37, 0.05, 0.18, 0.33, 0.1, 0.25, 0.4, 0.03, 0.2, 0.35, 0.12]
  const durations = [0.7, 0.85, 0.65, 0.9, 0.75, 0.8, 0.6, 0.95, 0.7, 0.82, 0.68, 0.88, 0.73, 0.78, 0.63, 0.91]

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 3,
        height,
        padding: '0 4px',
      }}
    >
      {Array.from({ length: bars }, (_, i) => (
        <div
          key={i}
          style={{
            width: 3,
            height: active ? `${Math.max(25, Math.random() * 90 + 15)}%` : '20%',
            borderRadius: 3,
            background: color,
            opacity: active ? 0.85 : 0.25,
            flexShrink: 0,
            transformOrigin: 'center',
            animation: active
              ? `waveform ${durations[i % durations.length]}s ease-in-out ${delays[i % delays.length]}s infinite`
              : 'none',
          }}
        />
      ))}
    </div>
  )
}
