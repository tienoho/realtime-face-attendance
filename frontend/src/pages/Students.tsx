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
} from '@mui/material'
import { Add as AddIcon } from '@mui/icons-material'
import { studentsApi, Student } from '../api/students'

export default function Students() {
  const [open, setOpen] = useState(false)
  const [studentId, setStudentId] = useState('')
  const [name, setName] = useState('')
  const [subject, setSubject] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['students'],
    queryFn: studentsApi.getStudents,
  })

  const registerMutation = useMutation({
    mutationFn: studentsApi.registerStudent,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['students'] })
      setOpen(false)
      setStudentId('')
      setName('')
      setSubject('')
      setFile(null)
      
      // Show success message with training info
      if (data.model_trained) {
        alert(`Student registered and model trained successfully!\nImages trained: ${data.training_details?.images_trained || 0}`)
      } else {
        alert(`Student registered but model training failed: ${data.training_details?.message || 'Unknown error'}`)
      }
    },
  })

  const handleSubmit = () => {
    if (!studentId || !name || !file) return
    registerMutation.mutate({
      student_id: studentId,
      name,
      subject: subject || undefined,
      file,
    })
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

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Register New Student</DialogTitle>
        <DialogContent>
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
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" gutterBottom>
              Upload Photo
            </Typography>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setFile((e.target as HTMLInputElement).files?.[0] || null)}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={!studentId || !name || !file || registerMutation.isPending}
          >
            {registerMutation.isPending ? <CircularProgress size={20} /> : 'Register'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
