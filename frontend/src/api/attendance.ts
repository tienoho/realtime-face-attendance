import api from './axios'

export interface AttendanceRecord {
  student_id: string
  name: string
  date: string
  time: string
  subject: string
  status: string
  confidence: number | null
}

export interface AttendanceReport {
  date: string
  subject: string | null
  count: number
  records: AttendanceRecord[]
}

export interface MarkAttendanceRequest {
  file: File
  subject: string
}

export const attendanceApi = {
  getReport: async (date: string, subject?: string): Promise<AttendanceReport> => {
    const params = new URLSearchParams()
    params.append('date', date)
    if (subject) params.append('subject', subject)

    const response = await api.get<AttendanceReport>(`/attendance/report?${params.toString()}`)
    return response.data
  },

  markAttendance: async (data: MarkAttendanceRequest): Promise<{
    message: string
    status: string
    student_id?: string
    name?: string
    subject?: string
    time?: string
    confidence?: number
  }> => {
    const formData = new FormData()
    formData.append('file', data.file)
    formData.append('subject', data.subject)

    const response = await api.post<{
      message: string
      status: string
      student_id?: string
      name?: string
      subject?: string
      time?: string
      confidence?: number
    }>('/attendance', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },

  getRecentAttendance: async (): Promise<{ records: AttendanceRecord[]; count: number }> => {
    const response = await api.get<{ records: AttendanceRecord[]; count: number }>('/attendance/recent')
    return response.data
  },
}
