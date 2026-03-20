import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  CircularProgress,
} from '@mui/material'
import { Download as DownloadIcon } from '@mui/icons-material'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { attendanceApi, AttendanceRecord } from '../api/attendance'
import dayjs from 'dayjs'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042']

export default function Reports() {
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'))
  const [subject, setSubject] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['attendance', date, subject],
    queryFn: () => attendanceApi.getReport(date, subject || undefined),
  })

  const records: AttendanceRecord[] = data?.records || []

  // Calculate stats
  const total = records.length
  const present = records.filter(r => r.status === 'Present').length
  const absent = total - present

  // Data for charts
  const barChartData = [
    { name: 'Present', value: present },
    { name: 'Absent', value: absent },
  ]

  const exportCSV = () => {
    if (!records.length) return
    
    const headers = ['Staff ID', 'Name', 'Date', 'Time', 'Subject', 'Status', 'Confidence']
    const rows = records.map(r => [
      r.staff_id,
      r.name,
      r.date,
      r.time,
      r.subject,
      r.status,
      r.confidence?.toString() || ''
    ])
    
    const csv = [headers, ...rows].map(row => row.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `attendance_${date}.csv`
    a.click()
  }

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h4" fontWeight={600} gutterBottom>
        Reports
      </Typography>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="Date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="Subject (Optional)"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <Button
                variant="contained"
                startIcon={<DownloadIcon />}
                onClick={exportCSV}
                disabled={!records.length}
              >
                Export CSV
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" align="center" color="success.main">
                Present
              </Typography>
              <Typography variant="h3" align="center" fontWeight={600}>
                {present}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" align="center" color="error.main">
                Absent
              </Typography>
              <Typography variant="h3" align="center" fontWeight={600}>
                {absent}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" align="center">
                Total
              </Typography>
              <Typography variant="h3" align="center" fontWeight={600}>
                {total}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Attendance Overview
              </Typography>
              <Box sx={{ height: 250 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="value" fill="#1976d2" />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Attendance Rate
              </Typography>
              <Box sx={{ height: 250 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={barChartData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={80}
                      fill="#8884d8"
                      paddingAngle={5}
                      dataKey="value"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      {barChartData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Staff ID</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Time</TableCell>
                <TableCell>Subject</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Confidence</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {records.map((record, index) => (
                <TableRow key={index}>
                  <TableCell>{record.staff_id}</TableCell>
                  <TableCell>{record.name}</TableCell>
                  <TableCell>{record.time}</TableCell>
                  <TableCell>{record.subject}</TableCell>
                  <TableCell>{record.status}</TableCell>
                  <TableCell>{record.confidence?.toFixed(1) || '-'}</TableCell>
                </TableRow>
              ))}
              {records.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    <Typography color="text.secondary">No records found</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
    </Box>
  )
}
