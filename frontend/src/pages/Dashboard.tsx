import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Skeleton,
  useTheme,
  alpha,
} from '@mui/material'
import {
  People as PeopleIcon,
  HowToReg as HowToRegIcon,
  Videocam as VideocamIcon,
  CheckCircle as CheckCircleIcon,
  TrendingUp as TrendingUpIcon,
  AccessTime as AccessTimeIcon,
} from '@mui/icons-material'
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'
import { camerasApi } from '../api/cameras'
import { staffsApi } from '../api/staffs'
import { attendanceApi } from '../api/attendance'
import { useSocket } from '../contexts/SocketContext'
import dayjs from 'dayjs'

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ReactNode
  gradient: string
  trend?: string
  isLoading?: boolean
}

function StatCard({ title, value, icon, gradient, trend, isLoading }: StatCardProps) {

  if (isLoading) {
    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Skeleton variant="rounded" width={56} height={56} />
            <Box sx={{ flexGrow: 1 }}>
              <Skeleton width="60%" height={20} />
              <Skeleton width="40%" height={36} />
            </Box>
          </Box>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card
      sx={{
        height: '100%',
        position: 'relative',
        overflow: 'hidden',
        transition: 'all 0.3s ease',
        cursor: 'pointer',
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
        },
      }}
    >
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: gradient,
          opacity: 0.85,
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          top: -20,
          right: -20,
          width: 100,
          height: 100,
          borderRadius: '50%',
          background: 'rgba(255,255,255,0.1)',
        }}
      />
      <CardContent sx={{ position: 'relative', zIndex: 1, color: 'white', p: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <Box>
            <Typography
              variant="body2"
              sx={{
                opacity: 0.9,
                fontWeight: 500,
                mb: 1,
                color: 'white',
              }}
            >
              {title}
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontWeight: 700,
                color: 'white',
                lineHeight: 1.2,
              }}
            >
              {value}
            </Typography>
            {trend && (
              <Box sx={{ display: 'flex', alignItems: 'center', mt: 1, gap: 0.5 }}>
                <TrendingUpIcon sx={{ fontSize: 16, opacity: 0.8 }} />
                <Typography variant="caption" sx={{ opacity: 0.9 }}>
                  {trend}
                </Typography>
              </Box>
            )}
          </Box>
          <Box
            sx={{
              width: 56,
              height: 56,
              borderRadius: 2,
              bgcolor: 'rgba(255,255,255,0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backdropFilter: 'blur(10px)',
            }}
          >
            {icon}
          </Box>
        </Box>
      </CardContent>
    </Card>
  )
}

function DashboardSkeleton() {
  return (
    <Box>
      <Skeleton width={200} height={40} sx={{ mb: 3 }} />
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {[1, 2, 3, 4].map((i) => (
          <Grid item xs={12} sm={6} md={3} key={i}>
            <StatCard title="" value="" icon={<></>} gradient="" isLoading />
          </Grid>
        ))}
      </Grid>
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Skeleton variant="rounded" height={350} />
        </Grid>
        <Grid item xs={12} md={4}>
          <Skeleton variant="rounded" height={350} />
        </Grid>
      </Grid>
    </Box>
  )
}

export default function Dashboard() {
  const theme = useTheme()
  const { onAttendance } = useSocket()

  const { data: camerasData, isLoading: camerasLoading } = useQuery({
    queryKey: ['cameras'],
    queryFn: camerasApi.getCameras,
  })

  const { data: staffsData, isLoading: staffsLoading } = useQuery({
    queryKey: ['staffs'],
    queryFn: staffsApi.getStaffs,
  })

  const { data: attendanceData, isLoading: attendanceLoading } = useQuery({
    queryKey: ['attendance', dayjs().format('YYYY-MM-DD')],
    queryFn: () => attendanceApi.getReport(dayjs().format('YYYY-MM-DD')),
  })

  // Listen for real-time attendance
  useEffect(() => {
    const cleanup = onAttendance((data) => {
      console.log('New attendance:', data)
    })
    return cleanup
  }, [onAttendance])

  // Generate chart data (mock for now)
  const chartData = Array.from({ length: 7 }, (_, i) => ({
    day: dayjs().subtract(6 - i, 'day').format('ddd'),
    attendance: Math.floor(Math.random() * 50) + 30,
    previous: Math.floor(Math.random() * 40) + 20,
  }))

  const activeCameras = camerasData?.cameras ? Object.values(camerasData.cameras).filter(c => c.connected).length : 0
  const totalStaffs = staffsData?.staffs?.length || 0
  const todayAttendance = attendanceData?.count || 0

  const isLoading = camerasLoading || staffsLoading || attendanceLoading

  if (isLoading) {
    return <DashboardSkeleton />
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={700} gutterBottom>
          Dashboard
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Welcome back! Here's what's happening with your attendance system today.
        </Typography>
      </Box>

      {/* Stats Grid */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Total Staffs"
            value={totalStaffs}
            icon={<PeopleIcon sx={{ fontSize: 28, color: 'white' }} />}
            gradient="linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%)"
            trend="+12% from last month"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Today's Attendance"
            value={todayAttendance}
            icon={<HowToRegIcon sx={{ fontSize: 28, color: 'white' }} />}
            gradient="linear-gradient(135deg, #10B981 0%, #059669 100%)"
            trend="+8% from yesterday"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Active Cameras"
            value={activeCameras}
            icon={<VideocamIcon sx={{ fontSize: 28, color: 'white' }} />}
            gradient="linear-gradient(135deg, #F59E0B 0%, #D97706 100%)"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="System Status"
            value="Healthy"
            icon={<CheckCircleIcon sx={{ fontSize: 28, color: 'white' }} />}
            gradient="linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)"
          />
        </Grid>
      </Grid>

      {/* Charts Row */}
      <Grid container spacing={3}>
        {/* Attendance Trend Chart */}
        <Grid item xs={12} md={8}>
          <Card
            sx={{
              height: '100%',
              transition: 'all 0.3s ease',
              '&:hover': {
                boxShadow: '0 10px 40px rgba(0,0,0,0.1)',
              },
            }}
          >
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                <Box>
                  <Typography variant="h6" fontWeight={600}>
                    Attendance Trend
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Last 7 days
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', gap: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: '#3B82F6' }} />
                    <Typography variant="caption">This Week</Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: '#E2E8F0' }} />
                    <Typography variant="caption">Last Week</Typography>
                  </Box>
                </Box>
              </Box>
              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorAttendance" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
                    <XAxis
                      dataKey="day"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: theme.palette.text.secondary, fontSize: 12 }}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: theme.palette.text.secondary, fontSize: 12 }}
                    />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 12,
                        border: 'none',
                        boxShadow: '0 4px 20px rgba(0,0,0,0.1)',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="attendance"
                      stroke="#3B82F6"
                      strokeWidth={3}
                      fill="url(#colorAttendance)"
                      dot={{ fill: '#3B82F6', strokeWidth: 0, r: 4 }}
                      activeDot={{ r: 6, strokeWidth: 0 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Recent Activity */}
        <Grid item xs={12} md={4}>
          <Card
            sx={{
              height: '100%',
              transition: 'all 0.3s ease',
              '&:hover': {
                boxShadow: '0 10px 40px rgba(0,0,0,0.1)',
              },
            }}
          >
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                Recent Activity
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Latest attendance records
              </Typography>
              
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {attendanceData?.records?.slice(0, 5).map((record, index) => (
                  <Box
                    key={index}
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 2,
                      p: 1.5,
                      borderRadius: 2,
                      transition: 'all 0.2s ease',
                      '&:hover': {
                        bgcolor: alpha(theme.palette.primary.main, 0.05),
                      },
                    }}
                  >
                    <Box
                      sx={{
                        width: 40,
                        height: 40,
                        borderRadius: '50%',
                        bgcolor: alpha(theme.palette.success.main, 0.1),
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <HowToRegIcon sx={{ color: 'success.main', fontSize: 20 }} />
                    </Box>
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Typography variant="body2" fontWeight={600} noWrap>
                        {record.name}
                      </Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <AccessTimeIcon sx={{ fontSize: 12, color: 'text.secondary' }} />
                        <Typography variant="caption" color="text.secondary">
                          {record.time}
                        </Typography>
                      </Box>
                    </Box>
                    <Typography
                      variant="caption"
                      sx={{
                        px: 1,
                        py: 0.5,
                        borderRadius: 1,
                        bgcolor: alpha(theme.palette.success.main, 0.1),
                        color: 'success.main',
                        fontWeight: 500,
                      }}
                    >
                      {record.subject || 'General'}
                    </Typography>
                  </Box>
                ))}
                {(!attendanceData?.records || attendanceData.records.length === 0) && (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <Typography variant="body2" color="text.secondary">
                      No recent activity
                    </Typography>
                  </Box>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}
