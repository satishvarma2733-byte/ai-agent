// NeuralPulse — animated radial pulse ring for agent status indicators
interface NeuralPulseProps {
  color?: string
  size?: number
  active?: boolean
  rings?: number
}

export default function NeuralPulse({
  color = '#7B61FF',
  size = 10,
  active = true,
  rings = 2,
}: NeuralPulseProps) {
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      {/* Core dot */}
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '50%',
          background: color,
          boxShadow: active ? `0 0 ${size}px ${color}` : 'none',
          position: 'relative',
          zIndex: 2,
        }}
      />
      {/* Pulse rings */}
      {active && Array.from({ length: rings }, (_, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            border: `1.5px solid ${color}`,
            animation: `ping-violet ${1.5 + i * 0.5}s cubic-bezier(0,0,0.2,1) ${i * 0.4}s infinite`,
          }}
        />
      ))}
    </div>
  )
}
