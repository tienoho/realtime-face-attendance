import api from './axios'
import { ApiEnvelope, unwrapEnvelope, unwrapEnvelopeWithMessage } from './dto'

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

export interface MarkAttendanceResponse {
  message: string
  status: string
  student_id?: string
  name?: string
  subject?: string
  time?: string
  confidence?: number
}

export const attendanceApi = {
  getReport: async (date: string, subject?: string): Promise<AttendanceReport> => {
    const params = new URLSearchParams()
    params.append('date', date)
    if (subject) params.append('subject', subject)

    const response = await api.get<ApiEnvelope<AttendanceReport>>(`/attendance/report?${params.toString()}`)
    return unwrapEnvelope(response.data)
  },

  markAttendance: async (data: MarkAttendanceRequest): Promise<MarkAttendanceResponse> => {
    const formData = new FormData()
    formData.append('file', data.file)
    formData.append('subject', data.subject)

    const response = await api.post<ApiEnvelope<{
      status: string
      student_id?: string
      name?: string
      subject?: string
      time?: string
      confidence?: number
    }>>('/attendance', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return unwrapEnvelopeWithMessage(response.data)
  },

  getRecentAttendance: async (): Promise<{ records: AttendanceRecord[]; count: number }> => {
    const response = await api.get<ApiEnvelope<{ records: AttendanceRecord[]; count: number }>>('/attendance/recent')
    return unwrapEnvelope(response.data)
  },
}
