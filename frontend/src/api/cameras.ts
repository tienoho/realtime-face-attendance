import api from './axios'
import { ApiEnvelope, unwrapEnvelope, unwrapEnvelopeWithMessage } from './dto'

export interface Camera {
  camera_id: string
  type: string
  connected: boolean
  config: Record<string, unknown>
  stats: CameraStats
}

export interface CameraStats {
  frames_captured: number
  frames_dropped: number
  errors: number
  fps: number
  last_frame_time: number
}

export interface CameraStatus {
  running: boolean
  total_cameras: number
  cameras: Record<string, Camera>
}

export interface AddCameraRequest {
  camera_id: string
  type: 'usb' | 'rtsp' | 'http' | 'onvif'
  device_index?: number
  url?: string
  stream_url?: string
  ip?: string
  host?: string
  port?: number
  username?: string
  password?: string
}

export interface StreamingConfig {
  quality: number
  fps: number
  resize_width: number
}

export interface DiscoveredCamera {
  type: string
  name: string
  url: string
  ip?: string
  port?: number
  protocol: string
  device_index?: number
}

export interface DiscoverCamerasRequest {
  scan_network?: boolean
  ip_range?: string
}

export interface DiscoverCamerasResponse {
  discovered?: {
    usb: DiscoveredCamera[]
    ip: DiscoveredCamera[]
    total: number
  }
  message: string
}

export interface DiscoverJobResponse {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  discovered?: {
    usb: DiscoveredCamera[]
    ip: DiscoveredCamera[]
    total: number
  }
  error?: string
  message: string
}

export const camerasApi = {
  getCameras: async (): Promise<CameraStatus> => {
    const response = await api.get<ApiEnvelope<CameraStatus>>('/cameras')
    return unwrapEnvelope(response.data)
  },

  addCamera: async (data: AddCameraRequest): Promise<{ message: string; camera_id: string }> => {
    const response = await api.post<ApiEnvelope<{ camera_id: string }>>('/cameras', data)
    return unwrapEnvelopeWithMessage(response.data)
  },

  removeCamera: async (cameraId: string): Promise<{ message: string; camera_id: string }> => {
    const response = await api.delete<ApiEnvelope<{ camera_id: string }>>(`/cameras/${cameraId}`)
    return unwrapEnvelopeWithMessage(response.data)
  },

  startCamera: async (cameraId: string): Promise<{ message: string; camera_id: string }> => {
    const response = await api.post<ApiEnvelope<{ camera_id: string }>>(`/cameras/${cameraId}/start`)
    return unwrapEnvelopeWithMessage(response.data)
  },

  stopCamera: async (cameraId: string): Promise<{ message: string; camera_id: string }> => {
    const response = await api.post<ApiEnvelope<{ camera_id: string }>>(`/cameras/${cameraId}/stop`)
    return unwrapEnvelopeWithMessage(response.data)
  },

  getFrame: async (cameraId: string): Promise<{ camera_id: string; frame: string; timestamp: number }> => {
    const response = await api.get<ApiEnvelope<{ camera_id: string; frame: string; timestamp: number }>>(
      `/cameras/${cameraId}/frame`
    )
    return unwrapEnvelope(response.data)
  },

  getStreamingConfig: async (): Promise<StreamingConfig> => {
    const response = await api.get<ApiEnvelope<StreamingConfig>>('/streaming/config')
    return unwrapEnvelope(response.data)
  },

  updateStreamingConfig: async (config: Partial<StreamingConfig>): Promise<StreamingConfig> => {
    const response = await api.post<ApiEnvelope<StreamingConfig>>('/streaming/config', config)
    return unwrapEnvelope(response.data)
  },

  discoverCameras: async (request?: DiscoverCamerasRequest): Promise<DiscoverCamerasResponse> => {
    const response = await api.post<ApiEnvelope<DiscoverCamerasResponse>>('/cameras/discover', request || {})
    return unwrapEnvelope(response.data)
  },

  // Start discovery and poll for results
  discoverCamerasWithPolling: async (
    request?: DiscoverCamerasRequest,
    onProgress?: (status: string) => void,
    maxPolls: number = 60,
    pollIntervalMs: number = 2000
  ): Promise<DiscoverCamerasResponse> => {
    // Start discovery job
    const startResponse = await api.post<ApiEnvelope<DiscoverJobResponse>>('/cameras/discover', request || {})
    const startData = unwrapEnvelope(startResponse.data)
    
    const jobId = startData.job_id
    onProgress?.('starting')
    
    // Poll for results
    for (let i = 0; i < maxPolls; i++) {
      await new Promise(resolve => setTimeout(resolve, pollIntervalMs))
      
      try {
        const statusResponse = await api.get<ApiEnvelope<DiscoverJobResponse>>(`/cameras/discover/${jobId}`)
        const statusData = unwrapEnvelope(statusResponse.data)
        
        if (statusData.status === 'completed') {
          onProgress?.('completed')
          return {
            discovered: statusData.discovered || { usb: [], ip: [], total: 0 },
            message: statusData.message || 'Discovery completed'
          }
        } else if (statusData.status === 'failed') {
          throw new Error(statusData.error || 'Discovery failed')
        } else {
          onProgress?.(statusData.status)
        }
      } catch (error) {
        console.error('Polling error:', error)
      }
    }
    
    throw new Error('Discovery timeout')
  },
}
