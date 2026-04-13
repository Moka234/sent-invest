<script setup>
import { computed, markRaw, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { getUserRecommendation, getUserTrend } from '../api'
import { useDataStore } from '../store'

const store = useDataStore()
const userId = ref('')
const loading = ref(false)
const queried = ref(false)
const notFound = ref(false)
const profile = ref(null)
const products = ref([])
const trendPoints = ref([])
const trendHistory = ref([])
const lineRef = ref(null)
const lineCardRef = ref(null)
let lineChart = null

const RISK_COLORS = { '保守型': '#94A3B8', '稳健型': '#D4AF37', '激进型': '#BE123C' }
const riskColor = (level) => RISK_COLORS[level] || '#D4AF37'

const riskSignalTone = (level) => {
  if (level === '保守型') {
    return {
      bg: '#94A3B8',
      shadow: '0 0 10px rgba(148,163,184,0.38)'
    }
  }
  if (level === '激进型') {
    return {
      bg: '#BE123C',
      shadow: '0 0 10px rgba(190,18,60,0.42)'
    }
  }
  return {
    bg: '#D4AF37',
    shadow: '0 0 10px rgba(212,175,55,0.45)'
  }
}

const normalizeTags = (tags) => {
  if (Array.isArray(tags)) return tags
  if (tags && typeof tags === 'object') return Object.values(tags)
  if (typeof tags === 'string' && tags) return [tags]
  return []
}

const formatMatchScore = (score) => `Score ${Number(score || 0).toFixed(1)}`

const matchScoreTone = (score) => {
  const value = Number(score || 0)
  if (value >= 9) {
    return {
      wrap: 'border-[#D4AF37]/45 bg-[#D4AF37]/14 text-[#F7E7AF] score-pill score-pill--high',
      dot: 'bg-[#F4D03F]',
      dotShadow: '0 0 12px rgba(244,208,63,0.88)',
      textShadow: '0 0 16px rgba(212,175,55,0.36)'
    }
  }
  if (value >= 7.5) {
    return {
      wrap: 'border-[#D4AF37]/25 bg-[#D4AF37]/9 text-[#E7D39A] score-pill score-pill--mid',
      dot: 'bg-[#D4AF37]',
      dotShadow: '0 0 10px rgba(212,175,55,0.52)',
      textShadow: '0 0 10px rgba(212,175,55,0.22)'
    }
  }
  return {
    wrap: 'border-slate-500/25 bg-slate-400/[0.08] text-slate-300 score-pill score-pill--low',
    dot: 'bg-slate-400',
    dotShadow: '0 0 8px rgba(148,163,184,0.30)',
    textShadow: '0 0 8px rgba(148,163,184,0.16)'
  }
}

const drawdownTone = (drawdown) => {
  const value = Number(drawdown || 0)
  if (value <= 1) {
    return {
      wrap: 'border-emerald-500/20 bg-emerald-500/[0.06]',
      label: 'text-emerald-300/80',
      value: 'text-emerald-200',
      dot: 'bg-emerald-400',
      dotShadow: '0 0 7px rgba(52,211,153,0.55)'
    }
  }
  if (value <= 10) {
    return {
      wrap: 'border-amber-500/20 bg-amber-500/[0.06]',
      label: 'text-amber-300/85',
      value: 'text-amber-200',
      dot: 'bg-amber-400',
      dotShadow: '0 0 7px rgba(251,191,36,0.5)'
    }
  }
  return {
    wrap: 'border-rose-500/20 bg-rose-500/[0.06]',
    label: 'text-rose-300/80',
    value: 'text-rose-200',
    dot: 'bg-rose-400',
    dotShadow: '0 0 7px rgba(251,113,133,0.5)'
  }
}

const sentimentTone = (score) => {
  const value = Number(score || 0)
  if (value >= 0.6) return 'text-[#D4AF37]'
  if (value >= 0.4) return 'text-neutral-200'
  return 'text-slate-300'
}

const volatilityTone = (volatility) => {
  const value = Number(volatility || 0)
  if (value > 0.15) return 'text-rose-300'
  if (value >= 0.1) return 'text-amber-300'
  return 'text-emerald-300'
}

const highlightReason = (reason) => {
  const text = String(reason || '')
  return text
    .replace(/(夏普比率为\s*\d+(?:\.\d+)?)/g, '<span class="ai-highlight ai-highlight--strong">$1</span>')
    .replace(/(最大回撤(?:仅)?为\s*\d+(?:\.\d+)?%)/g, '<span class="ai-highlight ai-highlight--strong">$1</span>')
    .replace(/(综合匹配得分为\s*\d+(?:\.\d+)?)/g, '<span class="ai-highlight ai-highlight--score">$1</span>')
    .replace(/(年化收益(?:达到)?\s*\d+(?:\.\d+)?%)/g, '<span class="ai-highlight ai-highlight--soft">$1</span>')
}

const generateMockTrend = (avg) => {
  const n = 6 + Math.floor(Math.random() * 3)
  return Array.from({ length: n }, () => Math.min(1, Math.max(0, avg + (Math.random() - 0.5) * 0.2)))
}

const initLineChart = () => {
  if (!lineRef.value) return
  if (lineChart) { lineChart.dispose(); lineChart = null }
  lineChart = markRaw(echarts.init(lineRef.value))
  let yData, xData
  if (trendHistory.value.length > 0) {
    xData = trendHistory.value.map(p => {
      const [datePart = '', timePart = ''] = String(p.time).split(' ')
      return `${datePart}\n${timePart.slice(0, 5)}`
    })
    yData = trendHistory.value.map(p => Number(p.score))
  } else if (trendPoints.value.length > 0) {
    xData = trendPoints.value.map(p => {
      const raw = String(p.analyze_time)
      return `${raw.slice(5, 10)}\n${raw.slice(11, 16)}`
    })
    yData = trendPoints.value.map(p => Number(p.sentiment_score || 0))
  } else {
    const avg = Number(profile.value?.avg_sentiment || 0.5)
    yData = generateMockTrend(avg)
    xData = yData.map((_, i) => `T-${yData.length - i}`)
  }
  try {
    lineChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis', backgroundColor: '#171717', borderColor: '#262626',
        textStyle: { color: '#fff', fontSize: 12 }, padding: [8, 12],
        extraCssText: 'border-radius:8px;'
      },
      grid: { left: 0, right: 0, top: 10, bottom: 20 },
      xAxis: {
        type: 'category', boundaryGap: false, data: xData,
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: '#525252', fontSize: 11, margin: 12 }
      },
      yAxis: {
        type: 'value', min: 0, max: 1, splitNumber: 2,
        splitLine: { lineStyle: { type: 'dashed', color: '#171717' } },
        axisLabel: { color: '#525252', fontSize: 11, formatter: v => v.toFixed(1) }
      },
      series: [{
        type: 'line', smooth: true, showSymbol: false, data: yData,
        lineStyle: { width: 2, color: '#D4AF37' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0.05, color: 'rgba(212,175,55,0.15)' },
            { offset: 0.95, color: 'rgba(212,175,55,0)' }
          ])
        }
      }]
    })
  } catch (e) { console.error('ECharts error:', e) }
}

watch(profile, (v) => { if (v) nextTick(() => nextTick(() => initLineChart())) })

const showAwaitingState = computed(() =>
  !loading.value && !queried.value && !profile.value && !notFound.value
)

watch(userId, (val) => {
  if (!val.trim()) {
    queried.value = false
    notFound.value = false
    profile.value = null
    products.value = []
    trendPoints.value = []
    trendHistory.value = []
  }
})

const openProductUrl = (url) => {
  console.log('准备跳转, URL:', url)
  if (url) window.open(url, '_blank')
  else console.warn('暂无购买链接')
}

const queryUser = async () => {
  const uid = userId.value.trim()
  if (!uid) { ElMessage.warning('请输入 user_id'); return }
  loading.value = true; queried.value = false; notFound.value = false
  try {
    const [r1, r2] = await Promise.all([
      getUserRecommendation(uid),
      getUserTrend(uid).catch(() => ({ code: 0, data: null })),
    ])
    if (r1.code === 404) { notFound.value = true; queried.value = true; return }
    if (r1.code !== 200 || !r1.data) throw new Error(r1.msg || '推荐信息获取失败')
    profile.value      = r1.data.profile
    products.value     = r1.data.products     || []
    trendHistory.value = r1.data.trend_history || []
    trendPoints.value  = r2.data?.points       || []
    store.setCurrentUserProfile(r1.data.profile)
    queried.value = true
  } catch (e) {
    profile.value = null; products.value = []; trendHistory.value = []
    ElMessage.error(e.message)
  } finally { loading.value = false }
}

const handleResize = () => lineChart?.resize()
onMounted(() => window.addEventListener('resize', handleResize))
onActivated(() => {
  window.addEventListener('resize', handleResize)
  nextTick(() => lineChart?.resize())
})
onDeactivated(() => {
  window.removeEventListener('resize', handleResize)
})
onBeforeUnmount(() => { window.removeEventListener('resize', handleResize); lineChart?.dispose(); lineChart = null })
</script>

<template>
  <section class="fade-in">
    <div class="mb-8">
      <h2 class="text-3xl font-light text-neutral-100 tracking-tight m-0">
        Personal <span class="font-semibold" style="color:#D4AF37">Intelligence</span>
      </h2>
      <p class="text-neutral-500 mt-2 text-sm">输入用户 ID，获取专属风险画像与理财产品推荐</p>
    </div>

    <div class="flex gap-4 max-w-2xl mb-10">
      <div class="relative flex-1 group">
        <div class="absolute inset-y-0 left-0 pl-5 flex items-center pointer-events-none">
          <svg class="h-4 w-4 text-neutral-500 group-focus-within:text-[#D4AF37] transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
        </div>
        <input
          v-model="userId"
          type="text"
          @keyup.enter="queryUser"
          class="gold-input block w-full pl-12 pr-4 py-4 rounded-xl text-neutral-200 placeholder-neutral-600 text-sm"
          placeholder="请输入用户 ID 进行解析..."
        />
      </div>
      <button
        @click="queryUser"
        :disabled="loading"
        class="cursor-pointer px-8 py-4 bg-neutral-100 hover:bg-white text-black font-semibold tracking-wide rounded-xl shadow-[0_0_20px_rgba(255,255,255,0.1)] hover:shadow-[0_0_24px_rgba(255,255,255,0.18)] transition-all duration-[var(--fx-duration)] ease-[var(--fx-ease)] flex items-center gap-2 text-sm disabled:opacity-50"
      >
        <span v-if="!loading">Analyze</span>
        <span v-else class="flex items-center gap-2">
          <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-black border-t-transparent"></span>
          分析中
        </span>
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
      </button>
    </div>

    <!-- Awaiting Target ID: 未检索待命空状态 -->
    <div v-if="showAwaitingState" class="flex flex-col items-center justify-center py-28 px-6 border border-neutral-800/80 border-dashed rounded-3xl bg-[#0A0A0A]/30 relative overflow-hidden group fade-in mt-6">
      <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] bg-[#D4AF37]/5 rounded-full blur-[80px] pointer-events-none transition-all duration-1000 group-hover:bg-[#D4AF37]/10"></div>

      <div class="relative w-24 h-24 mb-10 flex items-center justify-center">
        <div class="absolute inset-0 rounded-full border border-[#D4AF37]/20 animate-ping" style="animation-duration: 3s;"></div>
        <div class="absolute inset-2 rounded-full border border-[#D4AF37]/10 animate-ping" style="animation-duration: 2s; animation-delay: 0.5s;"></div>

        <div class="w-16 h-16 rounded-full bg-gradient-to-br from-[#1C1C1C] to-[#050505] border border-neutral-800 flex items-center justify-center relative z-10 shadow-[0_0_20px_rgba(212,175,55,0.05)]">
          <svg class="w-8 h-8 text-[#D4AF37]/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 7V6a3 3 0 0 1 3-3h1"/>
            <path d="M17 3h1a3 3 0 0 1 3 3v1"/>
            <path d="M21 17v1a3 3 0 0 1-3 3h-1"/>
            <path d="M7 21H6a3 3 0 0 1-3-3v-1"/>
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 9v-1"/>
            <path d="M12 16v-1"/>
            <path d="M15 12h1"/>
            <path d="M8 12H7"/>
          </svg>
        </div>
      </div>

      <h3 class="text-xl font-light text-neutral-200 tracking-widest uppercase mb-4">Awaiting Target ID</h3>
      <p class="text-sm text-neutral-500 max-w-md text-center leading-relaxed">
        系统核心引擎已就绪。请输入目标用户的唯一标识，算法将即刻调取其历史言论，执行情感多维度测算并生成专属资产配置方案。
      </p>

      <div class="mt-14 flex items-center gap-8 text-[10px] text-neutral-600 font-mono tracking-widest uppercase">
        <span class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500/50 shadow-[0_0_5px_rgba(16,185,129,0.5)]"></span> Engine Standby</span>
        <span class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-[#D4AF37]/50 shadow-[0_0_5px_rgba(212,175,55,0.5)]"></span> DB Connected</span>
      </div>
    </div>

    <div v-if="loading && !queried" class="space-y-4">
      <div v-for="n in 3" :key="n" class="h-20 rounded-2xl animate-pulse" style="background:#0A0A0A;border:1px solid #1a1a1a"></div>
    </div>

    <Transition name="fade-slide">
      <div v-if="queried && notFound" class="mt-10 flex flex-col items-center justify-center rounded-2xl py-16 text-center" style="background:#0A0A0A;border:1px solid #262626">
        <div class="mb-4 flex h-14 w-14 items-center justify-center rounded-full" style="background:#171717;border:1px solid #262626">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#D4AF37" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
        </div>
        <p class="text-base font-medium text-neutral-200">未找到该用户的投资发言记录</p>
        <p class="mt-1 text-sm text-neutral-500">请确认 user_id 是否正确，或该用户尚未生成风险画像</p>
      </div>
    </Transition>

    <Transition name="fade-slide">
      <div v-if="queried && !notFound && profile" class="grid grid-cols-1 lg:grid-cols-3 gap-8 items-stretch">
        <div class="space-y-6 flex flex-col h-full">
          <div class="card-glass-noise bg-[#0A0A0A] border border-neutral-800/80 rounded-2xl p-7 relative overflow-visible group hover:border-neutral-700 transition-colors">
            <div class="absolute top-0 right-0 w-32 h-32 bg-neutral-800/20 rounded-full blur-3xl -mr-10 -mt-10"></div>
            <div class="flex items-center gap-5 mb-8">
              <div class="profile-avatar-glow w-14 h-14 rounded-full bg-neutral-900 border border-neutral-800 flex items-center justify-center relative overflow-hidden">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#A1A1AA" stroke-width="1.7"><path d="M12 2a5 5 0 1 0 0 10A5 5 0 0 0 12 2zM2 20a10 10 0 0 1 20 0"/></svg>
              </div>
              <div>
                <h3 class="text-lg font-medium text-white m-0">{{ profile.user_id }}</h3>
                <span class="inline-flex items-center gap-2 mt-2">
                  <span
                    class="w-2 h-2 rounded-full"
                    :style="{ background: riskSignalTone(profile.risk_level).bg, boxShadow: riskSignalTone(profile.risk_level).shadow }"
                  ></span>
                  <span class="text-xs font-medium text-neutral-400 tracking-wide">{{ profile.risk_level }}</span>
                </span>
              </div>
            </div>
            <div class="grid grid-cols-3 gap-4 border-t border-neutral-900 pt-6">
              <div>
                <p class="text-[10px] text-neutral-500 tracking-wider uppercase mb-1.5">历史发言</p>
                <p class="text-2xl font-light font-mono tabular-nums text-white m-0">{{ profile.post_count }}</p>
              </div>
              <div>
                <div class="flex items-center gap-1.5 mb-1.5">
                  <p class="text-[10px] text-neutral-500 tracking-wider uppercase m-0">均值情绪</p>
                  <span class="tooltip-anchor group/info relative inline-flex">
                    <svg class="w-3.5 h-3.5 text-[#D4AF37]/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 10v5"/><path d="M12 7h.01"/></svg>
                    <span class="tooltip-panel tooltip-panel-center top-full z-30 mt-2 w-52">情感极化得分 (0~1)。&lt;0.45 为保守避险，0.45~0.52 为震荡稳健，&gt;=0.52 为激进看多。</span>
                  </span>
                </div>
                <p :class="['text-2xl font-light font-mono tabular-nums m-0', sentimentTone(profile.avg_sentiment)]">{{ Number(profile.avg_sentiment).toFixed(4) }}</p>
              </div>
              <div>
                <div class="flex items-center gap-1.5 mb-1.5">
                  <p class="text-[10px] text-neutral-500 tracking-wider uppercase m-0">情绪波动</p>
                  <span class="tooltip-anchor group/info relative inline-flex">
                    <svg class="w-3.5 h-3.5 text-[#D4AF37]/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 10v5"/><path d="M12 7h.01"/></svg>
                    <span class="tooltip-panel tooltip-panel-right top-full z-30 mt-2 w-52">基于发言情感的标准差。&gt;0.25 代表情绪极度不稳定，系统将自动触发风控降级机制。</span>
                  </span>
                </div>
                <p :class="['text-2xl font-light font-mono tabular-nums m-0', volatilityTone(profile.volatility)]">{{ Number(profile.volatility).toFixed(4) }}</p>
              </div>
            </div>
          </div>

          <div ref="lineCardRef" class="ai-insight-panel bg-[#0A0A0A] border border-neutral-800/80 rounded-2xl p-7 relative overflow-hidden flex-1 flex flex-col min-h-[320px]">
            <div class="flex items-center justify-between mb-8">
              <h3 class="text-xs font-semibold tracking-wider text-neutral-500 uppercase m-0">Sentiment Trend</h3>
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="#D4AF37" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            </div>
            <div class="flex-1 w-full min-h-[220px]">
              <div ref="lineRef" class="w-full h-full"></div>
            </div>
          </div>
        </div>

        <div class="lg:col-span-2">
          <div class="flex items-end justify-between mb-6">
            <div>
              <h3 class="text-lg font-medium text-white flex items-center gap-2 tracking-wide m-0">
                Selected Assets
                <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-[#D4AF37]/10 text-[#D4AF37] border border-[#D4AF37]/20 uppercase">Top 3</span>
              </h3>
              <p class="text-xs text-neutral-500 mt-2">基于您的风险承受能力与市场情绪波动算法精选</p>
            </div>
          </div>

          <div v-if="!products.length" class="rounded-2xl py-12 text-center text-neutral-600" style="background:#0A0A0A;border:1px solid #262626">暂无匹配产品</div>

          <div v-else class="space-y-4">
            <div
              v-for="(item, index) in products"
              :key="item.product_id"
              @click="openProductUrl(item.purchase_url)"
              class="group card-glass-noise bg-[#0A0A0A] border border-neutral-800/80 hover:border-[#D4AF37]/50 rounded-2xl p-6 transition-all duration-[var(--fx-duration)] ease-[var(--fx-ease)] hover:bg-[#111] hover:-translate-y-0.5 hover:shadow-[0_14px_32px_rgba(0,0,0,0.36)] cursor-pointer relative overflow-hidden"
            >
              <div class="absolute right-6 top-1/2 -translate-y-1/2 text-8xl font-black text-neutral-900/50 group-hover:text-[#D4AF37]/10 transition-colors pointer-events-none select-none">
                {{ String(index + 1).padStart(2, '0') }}
              </div>

              <div class="relative z-10 flex flex-col gap-5">
                <div class="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                  <div class="flex items-start gap-5 min-w-0">
                    <div class="w-11 h-11 rounded-full bg-neutral-900 border border-neutral-800 flex items-center justify-center group-hover:bg-[#D4AF37]/10 group-hover:border-[#D4AF37]/30 transition-all duration-[var(--fx-duration)] ease-[var(--fx-ease)] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] group-hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_0_14px_rgba(212,175,55,0.26)] shrink-0">
                      <span class="text-xs font-mono text-neutral-500 group-hover:text-[#D4AF37]">{{ String(index + 1).padStart(2, '0') }}</span>
                    </div>

                    <div class="min-w-0 flex-1">
                      <div class="flex flex-wrap items-center gap-3 mb-1.5">
                        <h4 class="text-base font-medium text-neutral-200 group-hover:text-white transition-colors tracking-wide m-0 truncate max-w-full">{{ item.product_name }}</h4>
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-neutral-900 border border-neutral-800 text-neutral-400">{{ item.product_id }}</span>
                        <span
                          :class="['inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-[10px] uppercase tracking-[0.22em] font-mono tabular-nums score-pill-hover', matchScoreTone(item.recommendation_score).wrap]"
                          :style="{ textShadow: matchScoreTone(item.recommendation_score).textShadow }"
                        >
                          <span class="inline-block h-1.5 w-1.5 rounded-full" :class="matchScoreTone(item.recommendation_score).dot" :style="{ boxShadow: matchScoreTone(item.recommendation_score).dotShadow }"></span>
                          {{ formatMatchScore(item.recommendation_score) }}
                        </span>
                      </div>

                      <div class="flex flex-wrap items-center gap-2.5 text-xs text-neutral-500">
                        <span>{{ item.product_type }}</span>
                        <span class="text-neutral-700">•</span>
                        <span class="inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)] border-[#D4AF37]/15 bg-[#D4AF37]/[0.04]">
                          <span class="text-[10px] uppercase tracking-[0.22em] text-[#D4AF37]/80">夏普</span>
                          <span class="tooltip-anchor group/info relative inline-flex">
                            <svg class="w-3.5 h-3.5 text-[#D4AF37]/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 10v5"/><path d="M12 7h.01"/></svg>
                            <span class="tooltip-panel tooltip-panel-center top-full z-30 mt-2 w-52">衡量承受每单位风险所获取的超额回报。数值越大，代表产品性价比越高。</span>
                          </span>
                          <span class="text-[11px] font-mono tabular-nums text-[#E7D39A]">{{ Number(item.sharpe_ratio).toFixed(2) }}</span>
                        </span>
                        <span :class="['inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]', drawdownTone(item.max_drawdown).wrap]">
                          <span :class="['text-[10px] uppercase tracking-[0.22em]', drawdownTone(item.max_drawdown).label]">回撤</span>
                          <span class="tooltip-anchor group/info relative inline-flex">
                            <svg class="w-3.5 h-3.5 text-[#D4AF37]/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 10v5"/><path d="M12 7h.01"/></svg>
                            <span class="tooltip-panel tooltip-panel-center top-full z-30 mt-2 w-52">产品在选定周期内的最大亏损幅度。用于衡量极端情况下的抗风险能力。</span>
                          </span>
                          <span class="inline-flex items-center gap-1.5">
                            <span class="w-1.5 h-1.5 rounded-full" :class="drawdownTone(item.max_drawdown).dot" :style="{ boxShadow: drawdownTone(item.max_drawdown).dotShadow }"></span>
                            <span :class="['text-[11px] font-mono tabular-nums', drawdownTone(item.max_drawdown).value]">{{ Number(item.max_drawdown).toFixed(2) }}%</span>
                          </span>
                        </span>
                      </div>
                    </div>
                  </div>

                  <div class="flex items-start justify-between sm:justify-end gap-4 border-t sm:border-t-0 border-neutral-900 pt-4 sm:pt-0 w-full sm:w-auto sm:pl-6">
                    <div class="text-left sm:text-right">
                      <p class="text-[10px] text-neutral-500 uppercase tracking-[0.24em] mb-1">Est. APY</p>
                      <div class="text-2xl font-light font-mono tabular-nums tracking-tight m-0" style="color:#D4AF37">{{ item.annual_yield }}%</div>
                    </div>

                    <div class="w-8 h-8 rounded-full border border-neutral-800 flex items-center justify-center group-hover:bg-[#D4AF37] group-hover:border-[#D4AF37] group-hover:text-black group-hover:shadow-[0_0_16px_rgba(212,175,55,0.34)] transition-colors duration-[var(--fx-duration)] ease-[var(--fx-ease)] text-neutral-500 shrink-0 mt-1">
                      <svg class="w-4 h-4 transition-transform duration-300 group-hover:translate-x-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                    </div>
                  </div>
                </div>

                <div class="ai-insight-panel rounded-xl border border-[#D4AF37]/10 bg-[#D4AF37]/[0.05] pl-0 pr-4 py-3 relative overflow-hidden shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
                  <div class="absolute left-0 top-0 h-full w-px bg-gradient-to-b from-[#D4AF37] via-[#D4AF37]/70 to-transparent"></div>
                  <div class="pl-4">
                    <div class="flex items-center gap-2 mb-2.5">
                      <svg class="w-3.5 h-3.5 text-[#D4AF37] drop-shadow-[0_0_8px_rgba(212,175,55,0.45)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M12 3l1.9 3.9L18 9l-3 2.9.7 4.1L12 14l-3.7 2 .7-4.1L6 9l4.1-2.1L12 3z"/>
                        <path d="M19 3v4"/>
                        <path d="M21 5h-4"/>
                      </svg>
                      <span class="text-[10px] uppercase tracking-[0.28em] text-[#D4AF37]/85">AI Insights</span>
                      <span class="h-px flex-1 bg-gradient-to-r from-[#D4AF37]/20 to-transparent"></span>
                    </div>
                    <p class="m-0 text-xs leading-6 text-neutral-400 italic font-light" v-html="highlightReason(item.recommend_reason)"></p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </section>
</template>

<style scoped>
.gold-input {
  background: #0A0A0A;
  border: 1px solid #262626;
  transition: border-color .25s ease, box-shadow .25s ease, background-color .25s ease;
}
.gold-input:focus {
  border-color: #D4AF37;
  box-shadow: 0 0 0 1px #D4AF37, 0 0 24px rgba(212,175,55,0.18);
  background: #0c0c0c;
}

.tooltip-anchor {
  position: relative;
  z-index: 40;
}

.tooltip-panel {
  position: absolute;
  opacity: 0;
  pointer-events: none;
  padding: .68rem .78rem;
  border-radius: .8rem;
  background: rgba(5, 5, 5, 0.90);
  border: 1px solid rgba(212, 175, 55, 0.30);
  backdrop-filter: blur(12px);
  color: #A3A3A3;
  font-size: 11px;
  line-height: 1.55;
  box-shadow: 0 18px 32px rgba(0, 0, 0, 0.42), 0 0 0 1px rgba(212,175,55,0.05);
  transition: opacity .18s ease, transform .18s ease;
  transform: translateY(6px);
  max-width: min(16rem, calc(100vw - 2rem));
  white-space: normal;
}

.tooltip-panel::before {
  content: '';
  position: absolute;
  top: -5px;
  width: 9px;
  height: 9px;
  background: rgba(5, 5, 5, 0.94);
  border-left: 1px solid rgba(212, 175, 55, 0.30);
  border-top: 1px solid rgba(212, 175, 55, 0.30);
  transform: rotate(45deg);
}

.tooltip-panel-center {
  left: 50%;
  transform: translateX(-50%) translateY(6px);
}

.tooltip-panel-center::before {
  left: calc(50% - 4.5px);
}

.tooltip-panel-right {
  right: 0;
  transform: translateY(6px);
}

.tooltip-panel-right::before {
  right: 10px;
}

.group\/info:hover .tooltip-panel {
  opacity: 1;
}

.group\/info:hover .tooltip-panel-center {
  transform: translateX(-50%) translateY(0);
}

.group\/info:hover .tooltip-panel-right {
  transform: translateY(0);
}

.profile-avatar-glow::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  background: radial-gradient(circle at 30% 25%, rgba(212,175,55,0.18) 0%, rgba(212,175,55,0.05) 32%, transparent 70%);
  opacity: .8;
  pointer-events: none;
}

.profile-avatar-glow::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.05), 0 0 14px rgba(212,175,55,0.06);
  animation: avatar-breathe 5.8s ease-in-out infinite;
  pointer-events: none;
}

.card-glass-noise::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  border-radius: inherit;
  opacity: .12;
  background-image:
    radial-gradient(circle at 22% 18%, rgba(255,255,255,0.045) 0, transparent 24%),
    radial-gradient(circle at 78% 72%, rgba(212,175,55,0.035) 0, transparent 22%),
    linear-gradient(120deg, rgba(255,255,255,0.025) 0%, rgba(255,255,255,0) 32%, rgba(255,255,255,0.018) 100%);
  mix-blend-mode: screen;
}

.score-pill {
  transition: border-color .35s ease, background-color .35s ease, box-shadow .35s ease, color .35s ease, transform .35s ease;
}
.score-pill-hover {
  will-change: transform, box-shadow;
}
.group:hover .score-pill-hover.score-pill--high {
  transform: translateY(-1px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), 0 0 0 1px rgba(212,175,55,0.14), 0 0 24px rgba(212,175,55,0.26), 0 0 44px rgba(212,175,55,0.10);
}
.group:hover .score-pill-hover.score-pill--mid {
  transform: translateY(-1px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.07), 0 0 0 1px rgba(212,175,55,0.09), 0 0 18px rgba(212,175,55,0.16), 0 0 34px rgba(212,175,55,0.06);
}
.group:hover .score-pill-hover.score-pill--low {
  transform: translateY(-1px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.05), 0 0 0 1px rgba(148,163,184,0.08), 0 0 14px rgba(148,163,184,0.12), 0 0 28px rgba(148,163,184,0.05);
}
.score-pill--high {
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 0 0 1px rgba(212,175,55,0.10), 0 0 18px rgba(212,175,55,0.20);
}
.score-pill--mid {
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.05), 0 0 0 1px rgba(212,175,55,0.06), 0 0 12px rgba(212,175,55,0.12);
}
.score-pill--low {
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 0 0 1px rgba(148,163,184,0.05), 0 0 10px rgba(148,163,184,0.08);
}

.ai-insight-panel::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  background: linear-gradient(90deg, transparent 0%, rgba(212,175,55,0.00) 28%, rgba(212,175,55,0.10) 50%, rgba(212,175,55,0.00) 72%, transparent 100%);
  transform: translateX(-100%);
  animation: ai-flow 6.8s ease-in-out infinite;
  opacity: .55;
}

.ai-insight-panel::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  box-shadow: inset 0 0 0 1px rgba(212,175,55,0.05), 0 0 14px rgba(212,175,55,0.04);
  animation: ai-breathe 4.8s ease-in-out infinite;
}

:deep(.ai-highlight) {
  color: #D4AF37;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, Courier New, monospace;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

:deep(.ai-highlight--strong) {
  text-shadow: 0 0 10px rgba(212,175,55,0.16);
}

:deep(.ai-highlight--score) {
  color: #F0D77A;
  text-shadow: 0 0 12px rgba(212,175,55,0.22);
}

:deep(.ai-highlight--soft) {
  color: #E7D39A;
  text-shadow: 0 0 8px rgba(212,175,55,0.12);
}

@keyframes ai-flow {
  0%, 100% {
    transform: translateX(-100%);
    opacity: .18;
  }
  50% {
    transform: translateX(100%);
    opacity: .55;
  }
}

@keyframes ai-breathe {
  0%, 100% {
    box-shadow: inset 0 0 0 1px rgba(212,175,55,0.04), 0 0 10px rgba(212,175,55,0.03);
  }
  50% {
    box-shadow: inset 0 0 0 1px rgba(212,175,55,0.08), 0 0 18px rgba(212,175,55,0.06);
  }
}

@keyframes avatar-breathe {
  0%, 100% {
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.05), 0 0 10px rgba(212,175,55,0.04);
  }
  50% {
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.07), 0 0 16px rgba(212,175,55,0.09);
  }
}

.fade-slide-enter-active, .fade-slide-leave-active { transition: all var(--fx-duration) var(--fx-ease); }
.fade-slide-enter-from { opacity: 0; transform: translateY(10px); }
.fade-slide-leave-to   { opacity: 0; transform: translateY(-6px); }
</style>

