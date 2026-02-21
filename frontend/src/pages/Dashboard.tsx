import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  CircularProgress,
} from '@mui/material'
import {
  People as PeopleIcon,
  HowToReg as HowToRegIcon,
  Videocam as VideocamIcon,
  CheckCircle as CheckCircleIcon,
} from '@mui/icons-material'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { camerasApi } from '../api/cameras'
import { studentsApi } from '../api/students'
import { attendanceApi } from '../api/attendance'
import { useSocket } from '../contexts/SocketContext'
import dayjs from 'dayjs'

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ReactNode
  color: string
}

function StatCard({ title, value, icon, color }: StatCardProps) {
  return (
    <Card>
      <CardContent sx={{ display: 'flex', alignItems: 'center', p: 2 }}>
        <Box
          sx={{
            width: 56,
            height: 56,
            borderRadius: 2,
            bgcolor: `${color}15`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mr: 2,
            color: color,
          }}
        >
          {icon}
        </Box>
        <Box>
          <Typography variant="body2" color="text.secondary">
            {title}
          </Typography>
          <Typography variant="h4" fontWeight={600}>
            {value}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  )
}

export default function Dashboard() {
  const { onAttendance } = useSocket()

  const { data: camerasData, isLoading: camerasLoading } = useQuery({
    queryKey: ['cameras'],
    queryFn: camerasApi.getCameras,
  })

  const { data: studentsData, isLoading: studentsLoading } = useQuery({
    queryKey: ['students'],
    queryFn: studentsApi.getStudents,
  })

  const { data: attendanceData, isLoading: attendanceLoading } = useQuery({
    queryKey: ['attendance', dayjs().format('YYYY-MM-DD')],
    queryFn: () => attendanceApi.getReport(dayjs().format('YYYY-MM-DD')),
  })

  // Listen for real-time attendance
  useEffect(() => {
    const cleanup = onAttendance((data) => {
      console.log('New attendance:', data)
      // Update recent attendance list
    })
    return cleanup
  }, [onAttendance])

  // Generate chart data (mock for now)
  const chartData = Array.from({ length: 7 }, (_, i) => ({
    day: dayjs().subtract(6 - i, 'day').format('ddd'),
    attendance: Math.floor(Math.random() * 50) + 30,
  }))

  const activeCameras = camerasData?.cameras ? Object.values(camerasData.cameras).filter(c => c.connected).length : 0
  const totalStudents = studentsData?.students?.length || 0
  const todayAttendance = attendanceData?.count || 0

  if (camerasLoading || studentsLoading || attendanceLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h4" fontWeight={600} gutterBottom>
        Dashboard
      </Typography>

      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Total Students"
            value={totalStudents}
            icon={<PeopleIcon fontSize="large" />}
            color="#1976d2"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Today's Attendance"
            value={todayAttendance}
            icon={<HowToRegIcon fontSize="large" />}
            color="#2e7d32"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Active Cameras"
            value={activeCameras}
            icon={<VideocamIcon fontSize="large" />}
            color="#ed6c02"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="System Status"
            value="Healthy"
            icon={<CheckCircleIcon fontSize="large" />}
            color="#9c27b0"
          />
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Attendance Trend (Last 7 Days)
              </Typography>
              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="day" />
                    <YAxis />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="attendance"
                      stroke="#1976d2"
                      strokeWidth={2}
                      dot={{ fill: '#1976d2' }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Recent Activity
              </Typography>
              {attendanceData?.records?.slice(0, 5).map((record, index) => (
                <Box
                  key={index}
                  sx={{
                    py: 1,
                    borderBottom: index < 4 ? '1px solid #eee' : 'none',
                  }}
                >
                  <Typography variant="body2" fontWeight={500}>
                    {record.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {record.time} - {record.subject}
                  </Typography>
                </Box>
              ))}
              {(!attendanceData?.records || attendanceData.records.length === 0) && (
                <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                  No recent activity
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}
