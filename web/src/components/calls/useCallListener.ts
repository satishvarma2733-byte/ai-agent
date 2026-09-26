import { useCallback, useEffect, useRef, useState } from 'react'
import type { RemoteTrack, Room } from 'livekit-client'
import { callsApi } from '../../api/calls'

/** Listen to one live call at a time: joins its LiveKit room hidden and receive-only, and plays everyone's audio. */
export function useCallListener() {
  const [listeningTo, setListeningTo] = useState<string | null>(null)
  const [connecting, setConnecting] = useState<string | null>(null)
  const roomRef = useRef<Room | null>(null)
  const audioRef = useRef<HTMLElement[]>([])

  const stop = useCallback(async () => {
    audioRef.current.forEach(el => el.remove())
    audioRef.current = []
    const room = roomRef.current
    roomRef.current = null
    setListeningTo(null)
    if (room) await room.disconnect()
  }, [])

  const listen = useCallback(async (callId: string) => {
    await stop()
    setConnecting(callId)
    try {
      const grant = await callsApi.listen(callId)
      // Loaded on first use: the LiveKit client is large and only supervisors listening need it.
      const { Room: LiveKitRoom, RoomEvent, Track } = await import('livekit-client')
      const room = new LiveKitRoom()
      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind !== Track.Kind.Audio) return
        const el = track.attach()
        el.style.display = 'none'
        document.body.appendChild(el)
        audioRef.current.push(el)
      })
      room.on(RoomEvent.Disconnected, () => { void stop() })
      await room.connect(grant.url, grant.token, { autoSubscribe: true })
      // Browsers only play audio after a user gesture; this click was one.
      await room.startAudio()
      roomRef.current = room
      setListeningTo(callId)
    } finally {
      setConnecting(null)
    }
  }, [stop])

  useEffect(() => () => { void stop() }, [stop])

  return { listeningTo, connecting, listen, stop }
}
