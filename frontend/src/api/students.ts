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
}
