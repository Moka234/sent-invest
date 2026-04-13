import axios from 'axios'
import NProgress from 'nprogress'

const request = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  timeout: 10000,
})

request.interceptors.request.use((config) => {
  NProgress.start()
  return config
})

request.interceptors.response.use(
  (response) => {
    NProgress.done()
    return response.data
  },
  (error) => {
    NProgress.done()
    const msg = error?.response?.data?.msg || error.message || '网络请求失败'
    return Promise.reject(new Error(msg))
  },
)

export const getMarketDashboard    = () => request.get('/api/market/dashboard')
export const getMarketTrend24H     = () => request.get('/api/sentiment/trend/24h')
export const getUserRecommendation = (userId) => request.get(`/api/users/${encodeURIComponent(userId)}/recommendation`)
export const getUserTrend          = (userId) => request.get(`/api/users/${encodeURIComponent(userId)}/trend`)

export default request
