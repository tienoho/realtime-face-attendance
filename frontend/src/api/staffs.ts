import api from './axios'
import { ApiEnvelope, unwrapEnvelope, unwrapEnvelopeWithMessage } from './dto'

export interface Staff {
  staff_id: string
  name: string
  department?: string
  position?: string
  is_active: boolean
  created_at: string
}

export interface RegisterStaffRequest {
  staff_id: string
  name: string
  department?: string
  position?: string
  subject?: string
  file: File
}

export interface TrainingResult {
  status: string
  message: string
  images_trained: number
  unique_labels?: number
}

export interface RegisterStaffResponse {
  message: string
  staff_id: string
  name: string
  images_saved: number
  model_trained: boolean
  training_details?: TrainingResult
}

// Phase 2: Multi-image registration types
export interface RegisterStaffMultiRequest {
  staff_id: string
  name: string
  department?: string
  position?: string
  images: File[]
  apply_augmentation?: boolean
}

export interface RegisterStaffMultiResponse {
  message: string
  staff_id: string
  name: string
  images_uploaded: number
  faces_detected: number
  images_saved: number
  augmentation_applied: boolean
  faiss_registration: {
    status: string
    message?: string
    images_processed?: number
  }
  lbph_training: TrainingResult
}

// Capture single frame from webcam
export interface CaptureFaceRequest {
  staff_id: string
  name: string
  department?: string
  position?: string
  image_data: string  // base64
}

export interface CaptureFaceResponse {
  message: string
  staff_id: string
  name: string
  image_path: string
  faiss_registration: {
    status: string
    message?: string
  }
}

export const staffsApi = {
  getStaffs: async (): Promise<{ staffs: Staff[] }> => {
    const response = await api.get<ApiEnvelope<{ staffs: Staff[] }>>('/staffs')
    return unwrapEnvelope(response.data)
  },

  registerStaff: async (data: RegisterStaffRequest): Promise<RegisterStaffResponse> => {
    const formData = new FormData()
    formData.append('staff_id', data.staff_id)
    formData.append('name', data.name)
    if (data.department) formData.append('department', data.department)
    if (data.position) formData.append('position', data.position)
    if (data.subject) formData.append('subject', data.subject)
    formData.append('file', data.file)

    const response = await api.post<ApiEnvelope<Omit<RegisterStaffResponse, 'message'>>>(
      '/register-staff',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return unwrapEnvelopeWithMessage(response.data)
  },

  // Phase 2: Multi-image registration
  registerStaffMulti: async (data: RegisterStaffMultiRequest): Promise<RegisterStaffMultiResponse> => {
    const formData = new FormData()
    formData.append('staff_id', data.staff_id)
    formData.append('name', data.name)
    if (data.department) formData.append('department', data.department)
    if (data.position) formData.append('position', data.position)
    formData.append('apply_augmentation', data.apply_augmentation !== false ? 'true' : 'false')
    
    // Append multiple images
    data.images.forEach((file) => {
      formData.append('images', file)
    })

    const response = await api.post<ApiEnvelope<Omit<RegisterStaffMultiResponse, 'message'>>>(
      '/register-staff-multi',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return unwrapEnvelopeWithMessage(response.data)
  },

  // Capture face from webcam
  captureFace: async (data: CaptureFaceRequest): Promise<CaptureFaceResponse> => {
    const response = await api.post<ApiEnvelope<Omit<CaptureFaceResponse, 'message'>>>(
      '/register-face-capture',
      data
    )
    return unwrapEnvelopeWithMessage(response.data)
  },
}
