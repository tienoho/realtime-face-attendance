import api from './axios'

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
  stream_url?: string
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

export const camerasApi = {
  getCameras: async (): Promise<CameraStatus> => {
    const response = await api.get<CameraStatus>('/cameras')
    return response.data
  },

  addCamera: async (data: AddCameraRequest): Promise<{ message: string; camera_id: string }> => {
    const response = await api.post<{ message: string; camera_id: string }>('/cameras', data)
    return response.data
  },

  removeCamera: async (cameraId: string): Promise<{ message: string }> => {
    const response = await api.delete<{ message: string }>(`/cameras/${cameraId}`)
    return response.data
  },

  startCamera: async (cameraId: string): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>(`/cameras/${cameraId}/start`)
    return response.data
  },

  stopCamera: async (cameraId: string): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>(`/cameras/${cameraId}/stop`)
    return response.data
  },

  getFrame: async (cameraId: string): Promise<{ frame: string; timestamp: number }> => {
    const response = await api.get<{ frame: string; timestamp: number }>(`/cameras/${cameraId}/frame`)
    return response.data
  },

  getStreamingConfig: async (): Promise<StreamingConfig> => {
    const response = await api.get<StreamingConfig>('/streaming/config')
    return response.data
  },

  updateStreamingConfig: async (config: Partial<StreamingConfig>): Promise<StreamingConfig> => {
    const response = await api.post<StreamingConfig>('/streaming/config', config)
    return response.data
  },
}
