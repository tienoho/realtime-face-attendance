import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react'
import { io, Socket } from 'socket.io-client'

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:5001'

interface SocketContextType {
  socket: Socket | null
  isConnected: boolean
  streamCamera: (cameraId: string) => void
  stopStreamCamera: (cameraId: string) => void
  subscribeCamera: (cameraId: string) => void
  unsubscribeCamera: (cameraId: string) => void
  onCameraFrame: (callback: (data: CameraFrameData) => void) => () => void
  onAttendance: (callback: (data: AttendanceEventData) => void) => () => void
  onFacesDetected: (callback: (data: FacesDetectedData) => void) => () => void
}

interface CameraFrameData {
  camera_id: string
  frame: string
  timestamp: number
}

interface AttendanceEventData {
  camera_id: string
  person_id: string
  confidence: number
  timestamp: number
}

interface FacesDetectedData {
  camera_id: string
  count: number
  timestamp: number
}

const SocketContext = createContext<SocketContextType | undefined>(undefined)

export function SocketProvider({ children }: { children: ReactNode }) {
  const [socket, setSocket] = useState<Socket | null>(null)
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('fa_token')
    if (!token) return

    const newSocket = io(SOCKET_URL, {
      auth: { token },
      transports: ['websocket'],
      // Reconnection configuration
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      // Timeout settings
      timeout: 10000,
      // Auto-connect
      autoConnect: true,
    })

    newSocket.on('connect', () => {
      console.log('Socket connected:', newSocket.id)
      setIsConnected(true)
    })

    newSocket.on('disconnect', (reason) => {
      console.log('Socket disconnected:', reason)
      setIsConnected(false)
      // If server disconnected, try to reconnect
      if (reason === 'io server disconnect') {
        newSocket.connect()
      }
    })

    newSocket.on('connect_error', (error) => {
      console.error('Socket connection error:', error.message)
      setIsConnected(false)
      
      // Handle authentication errors
      if (error.message === 'Invalid token' || error.message === 'Token has expired') {
        console.warn('Socket auth error, clearing token')
        localStorage.removeItem('fa_token')
        newSocket.close()
      }
    })

    // Handle reconnection events
    newSocket.on('reconnect', (attemptNumber) => {
      console.log(`Socket reconnected after ${attemptNumber} attempts`)
      setIsConnected(true)
    })

    newSocket.on('reconnect_attempt', (attemptNumber) => {
      console.log(`Socket reconnection attempt ${attemptNumber}`)
    })

    newSocket.on('reconnect_failed', () => {
      console.error('Socket reconnection failed')
      setIsConnected(false)
    })

    setSocket(newSocket)

    return () => {
      newSocket.close()
    }
  }, [])

  const streamCamera = useCallback((cameraId: string) => {
    socket?.emit('stream_camera', { camera_id: cameraId })
  }, [socket])

  const stopStreamCamera = useCallback((cameraId: string) => {
    socket?.emit('stop_stream_camera', { camera_id: cameraId })
  }, [socket])

  const subscribeCamera = useCallback((cameraId: string) => {
    socket?.emit('subscribe_camera', { camera_id: cameraId })
  }, [socket])

  const unsubscribeCamera = useCallback((cameraId: string) => {
    socket?.emit('unsubscribe_camera', { camera_id: cameraId })
  }, [socket])

  const onCameraFrame = useCallback((callback: (data: CameraFrameData) => void): (() => void) => {
    if (!socket) return () => {}
    socket.on('camera_frame', callback)
    return () => {
      socket.off('camera_frame', callback)
    }
  }, [socket])

  const onAttendance = useCallback((callback: (data: AttendanceEventData) => void): (() => void) => {
    if (!socket) return () => {}
    socket.on('attendance', callback)
    return () => {
      socket.off('attendance', callback)
    }
  }, [socket])

  const onFacesDetected = useCallback((callback: (data: FacesDetectedData) => void): (() => void) => {
    if (!socket) return () => {}
    socket.on('faces_detected', callback)
    return () => {
      socket.off('faces_detected', callback)
    }
  }, [socket])

  const value = {
    socket,
    isConnected,
    streamCamera,
    stopStreamCamera,
    subscribeCamera,
    unsubscribeCamera,
    onCameraFrame,
    onAttendance,
    onFacesDetected,
  }

  return <SocketContext.Provider value={value}>{children}</SocketContext.Provider>
}

export function useSocket() {
  const context = useContext(SocketContext)
  if (context === undefined) {
    throw new Error('useSocket must be used within a SocketProvider')
  }
  return context
}
