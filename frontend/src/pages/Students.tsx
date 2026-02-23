import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Card,
  Typography,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Avatar,
  Chip,
  CircularProgress,
  ToggleButton,
  ToggleButtonGroup,
  FormControlLabel,
  Switch,
  Alert,
} from '@mui/material'
import {
  Add as AddIcon,
  CameraAlt,
  Upload as UploadIcon,
} from '@mui/icons-material'
import { studentsApi, Student } from '../api/students'
import FaceCapture from '../components/FaceCapture'

type RegistrationMode = 'upload' | 'capture'

export default function Students() {
  const [open, setOpen] = useState(false)
  const [showCapture, setShowCapture] = useState(false)
  const [studentId, setStudentId] = useState('')
  const [name, setName] = useState('')
  const [subject, setSubject] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [capturedImages, setCapturedImages] = useState<string[]>([])
  const [registrationMode, setRegistrationMode] = useState<RegistrationMode>('capture')
  const [applyAugmentation, setApplyAugmentation] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['students'],
    queryFn: studentsApi.getStudents,
  })

  const registerMutation = useMutation({
    mutationFn: async () => {
      if (registrationMode === 'capture' && capturedImages.length > 0) {
        // Convert base64 to File objects
        const files: File[] = await Promise.all(
          capturedImages.map(async (base64, index) => {
            const response = await fetch(base64)
            const blob = await response.blob()
            return new File([blob], `capture_${index}.jpg`, { type: 'image/jpeg' })
          })
        )
        return studentsApi.registerStudentMulti({
          student_id: studentId,
          name,
          images: files,
          apply_augmentation: applyAugmentation,
        })
      } else if (file) {
        return studentsApi.registerStudent({
          student_id: studentId,
          name,
          subject: subject || undefined,
          file,
        })
      }
      throw new Error('No images to register')
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['students'] })
      setSuccess(
        `Đăng ký thành công! ` +
        `Ảnh: ${(data as any).images_saved || 1}, ` +
        `FAISS: ${(data as any).faiss_registration?.status || 'N/A'}`
      )
      setTimeout(() => {
        handleClose()
      }, 2000)
    },
    onError: (error: any) => {
      setError(error.response?.data?.message || error.message || 'Registration failed')
    },
  })

  const handleClose = () => {
    setOpen(false)
    setShowCapture(false)
    setStudentId('')
    setName('')
    setSubject('')
    setFile(null)
    setCapturedImages([])
    setError(null)
    setSuccess(null)
  }

  const handleCaptureComplete = (images: string[]) => {
    setCapturedImages(images)
    setShowCapture(false)
  }

  const handleSubmit = () => {
    if (!studentId || !name) return
    
    if (registrationMode === 'capture' && capturedImages.length === 0) {
      setError('Vui lòng chụp ít nhất 1 ảnh khuôn mặt')
      return
    }
    
    if (registrationMode === 'upload' && !file) {
      setError('Vui lòng tải lên ảnh khuôn mặt')
      return
    }
    
    setError(null)
    registerMutation.mutate()
  }

  const students: Student[] = data?.students || []

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" fontWeight={600}>
          Students
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setOpen(true)}
        >
          Add Student
        </Button>
      </Box>

      <Card>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Avatar</TableCell>
                <TableCell>Student ID</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {students.map((student) => (
                <TableRow key={student.student_id}>
                  <TableCell>
                    <Avatar sx={{ bgcolor: 'primary.main' }}>
                      {student.name.charAt(0).toUpperCase()}
                    </Avatar>
                  </TableCell>
                  <TableCell>{student.student_id}</TableCell>
                  <TableCell>{student.name}</TableCell>
                  <TableCell>
                    <Chip
                      label={student.is_active ? 'Active' : 'Inactive'}
                      color={student.is_active ? 'success' : 'default'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>
                    {student.created_at ? new Date(student.created_at).toLocaleDateString() : '-'}
                  </TableCell>
                </TableRow>
              ))}
              {students.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} align="center">
                    <Typography color="text.secondary">No students found</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      {/* Face Capture Modal */}
      {showCapture && (
        <FaceCapture
          onCapture={handleCaptureComplete}
          onClose={() => setShowCapture(false)}
          targetCount={10}
        />
      )}

      {/* Registration Dialog */}
      <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
        <DialogTitle>Register New Student</DialogTitle>
        <DialogContent>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          
          {success && (
            <Alert severity="success" sx={{ mb: 2 }}>
              {success}
            </Alert>
          )}

          <TextField
            autoFocus
            margin="dense"
            label="Student ID"
            fullWidth
            value={studentId}
            onChange={(e) => setStudentId(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Name"
            fullWidth
            value={name}
            onChange={(e) => setName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Subject (Optional)"
            fullWidth
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            sx={{ mb: 2 }}
          />

          {/* Mode Selection */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle2" gutterBottom>
              Registration Mode
            </Typography>
            <ToggleButtonGroup
              value={registrationMode}
              exclusive
              onChange={(_, value) => value && setRegistrationMode(value)}
              fullWidth
            >
              <ToggleButton value="capture">
                <CameraAlt sx={{ mr: 1 }} />
                Chụp ảnh ({capturedImages.length})
              </ToggleButton>
              <ToggleButton value="upload">
                <UploadIcon sx={{ mr: 1 }} />
                Tải lên
              </ToggleButton>
            </ToggleButtonGroup>
          </Box>

          {/* Capture Mode */}
          {registrationMode === 'capture' && (
            <Box sx={{ mb: 2 }}>
              <Button
                variant="outlined"
                onClick={() => setShowCapture(true)}
                startIcon={<CameraAlt />}
                fullWidth
                sx={{ py: 2 }}
              >
                {capturedImages.length > 0
                  ? `Đã chụp ${capturedImages.length} ảnh - Nhấn để thay đổi`
                  : 'Nhấn để chụp ảnh khuôn mặt'}
              </Button>
              
              <FormControlLabel
                control={
                  <Switch
                    checked={applyAugmentation}
                    onChange={(e) => setApplyAugmentation(e.target.checked)}
                  />
                }
                label="Tăng cường dữ liệu (xoay, lật, sáng/tối)"
                sx={{ mt: 1 }}
              />
              <Typography variant="caption" display="block" color="text.secondary">
                Khuyến nghị: Bật để cải thiện độ chính xác nhận dạng
              </Typography>
            </Box>
          )}

          {/* Upload Mode */}
          {registrationMode === 'upload' && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" gutterBottom>
                Upload Photo
              </Typography>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setFile((e.target as HTMLInputElement).files?.[0] || null)}
              />
              {file && (
                <Typography variant="caption" display="block" color="primary">
                  Đã chọn: {file.name}
                </Typography>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={
              !studentId ||
              !name ||
              registerMutation.isPending ||
              (registrationMode === 'capture' && capturedImages.length === 0) ||
              (registrationMode === 'upload' && !file)
            }
          >
            {registerMutation.isPending ? <CircularProgress size={20} /> : 'Register'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
