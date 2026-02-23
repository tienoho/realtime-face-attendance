import api from './axios'

export interface Student {
  student_id: string
  name: string
  is_active: boolean
  created_at: string
}

export interface RegisterStudentRequest {
  student_id: string
  name: string
  subject?: string
  file: File
}

export interface TrainingResult {
  status: string
  message: string
  images_trained: number
  unique_labels?: number
}

export interface RegisterStudentResponse {
  message: string
  student_id: string
  name: string
  images_saved: number
  model_trained: boolean
  training_details?: TrainingResult
}

// Phase 2: Multi-image registration types
export interface RegisterStudentMultiRequest {
  student_id: string
  name: string
  images: File[]
  apply_augmentation?: boolean
}

export interface RegisterStudentMultiResponse {
  message: string
  student_id: string
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
  student_id: string
  name: string
  image_data: string  // base64
}

export interface CaptureFaceResponse {
  message: string
  student_id: string
  name: string
  image_path: string
  faiss_registration: {
    status: string
    message?: string
  }
}

export const studentsApi = {
  getStudents: async (): Promise<{ students: Student[] }> => {
    const response = await api.get<{ students: Student[] }>('/students')
    return response.data
  },

  registerStudent: async (data: RegisterStudentRequest): Promise<RegisterStudentResponse> => {
    const formData = new FormData()
    formData.append('student_id', data.student_id)
    formData.append('name', data.name)
    if (data.subject) formData.append('subject', data.subject)
    formData.append('file', data.file)

    const response = await api.post<RegisterStudentResponse>(
      '/register-student',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data
  },

  // Phase 2: Multi-image registration
  registerStudentMulti: async (data: RegisterStudentMultiRequest): Promise<RegisterStudentMultiResponse> => {
    const formData = new FormData()
    formData.append('student_id', data.student_id)
    formData.append('name', data.name)
    formData.append('apply_augmentation', data.apply_augmentation !== false ? 'true' : 'false')
    
    // Append multiple images
    data.images.forEach((file, index) => {
      formData.append('images', file)
    })

    const response = await api.post<RegisterStudentMultiResponse>(
      '/register-student-multi',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data
  },

  // Capture face from webcam
  captureFace: async (data: CaptureFaceRequest): Promise<CaptureFaceResponse> => {
    const response = await api.post<CaptureFaceResponse>(
      '/register-face-capture',
      data
    )
    return response.data
  },
}
