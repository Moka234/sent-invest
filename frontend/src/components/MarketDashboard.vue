<script setup>
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { getMarketDashboard, getMarketTrend24H } from '../api'
import { useDataStore } from '../store'

const formatCurrentTime = () => {
  const now = new Date()
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

const store = useDataStore()
const dashboard = ref({ global_avg_sentiment: 0, risk_level_distribution: [] })
const pieRef = ref(null)
const globalTrendRef = ref(null)
const currentTime = ref(formatCurrentTime())
let currentTimeTimer = null
let currentTimeAlignTimer = null
let pieChart = null
let globalTrendChart = null

const globalAvg = computed(() => Number(dashboard.value.global_avg_sentiment || 0))
const totalUsers = computed(() =>
  (dashboard.value.risk_level_distribution || []).reduce((s, x) => s + x.user_count, 0)
)
const pieData = computed(() =>
  (dashboard.value.risk_level_distribution || []).map((x) => ({ name: x.risk_level, value: x.user_count }))
)
const sentimentLabel = computed(() => {
  const v = globalAvg.value
  if (v >= 0.6) return '整体偏积极'
  if (v >= 0.4) return '中性偏悲观状态'
  return '整体偏悲观'
})
const rolling24hAvg = computed(() => {
  const values = global24hTrend.value.data || []
  if (!values.length) return 0
  return values.reduce((sum, value) => sum + Number(value || 0), 0) / values.length
})

// 风险等级对应颜色（黑金主题）
const RISK_COLORS = { '稳健型': '#D4AF37', '保守型': '#94A3B8', '激进型': '#991B1B' }
const riskColor = (name) => RISK_COLORS[name] || '#D4AF37'

const global24hTrend = ref({ labels: [], data: [], pointTypes: [] })

const initPie = () => {
  if (!pieRef.value) return
  if (pieChart) { pieChart.dispose(); pieChart = null }
  pieChart = echarts.init(pieRef.value)
  pieChart.setOption({
    backgroundColor: 'transparent',
    animation: true, animationDuration: 900, animationEasing: 'cubicOut',
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} 人 ({d}%)',
      backgroundColor: '#171717', borderColor: '#262626', borderWidth: 1,
      textStyle: { color: '#fff', fontSize: 13 },
      padding: [12, 16], extraCssText: 'border-radius:8px;'
    },
    series: [{
      type: 'pie',
      radius: ['68%', '90%'],
      center: ['50%', '52%'],
      minAngle: 5,
      itemStyle: { borderRadius: 4, borderColor: '#0A0A0A', borderWidth: 3 },
      label: { show: false },
      emphasis: { scale: true, scaleSize: 3 },
      animationType: 'scale', animationEasing: 'elasticOut',
      data: pieData.value.map(item => ({
        value: item.value,
        name: item.name,
        itemStyle: { color: riskColor(item.name) }
      }))
    }]
  })
}

const initGlobalTrend = () => {
  if (!globalTrendRef.value) return
  if (globalTrendChart) { globalTrendChart.dispose(); globalTrendChart = null }
  globalTrendChart = echarts.init(globalTrendRef.value)

  const xData = global24hTrend.value.labels
  const yData = global24hTrend.value.data
  const pointTypes = global24hTrend.value.pointTypes
  const realPointData = xData
    .map((label, idx) => pointTypes[idx] === 'real' ? [label, yData[idx]] : null)
    .filter(Boolean)
  const interpolatedPointData = xData
    .map((label, idx) => pointTypes[idx] !== 'real' ? [label, yData[idx]] : null)
    .filter(Boolean)
  const currentHourLabel = xData[xData.length - 1]

  globalTrendChart.setOption({
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 1000,
    animationEasing: 'cubicOut',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#171717',
      borderColor: '#262626',
      borderWidth: 1,
      textStyle: { color: '#fff', fontSize: 12 },
      padding: [10, 14],
      extraCssText: 'border-radius:8px;',
      formatter: (params) => {
        const point = Array.isArray(params) ? params.find(item => item.seriesName === 'Global Sentiment') || params[0] : params
        if (!point) return ''
        const idx = point.dataIndex
        const pointType = global24hTrend.value.pointTypes[idx] === 'real'
          ? '真实点'
          : global24hTrend.value.pointTypes[idx] === 'interpolated'
            ? '插值点'
            : '边界锚点'
        const deviation = (Number(point.value) - globalAvg.value).toFixed(4)
        const sign = Number(deviation) >= 0 ? '+' : ''
        return `${point.axisValue}<br/>该小时均值 (Hourly Avg): <span style="color:#F7E7AF">${Number(point.value).toFixed(4)}</span><br/>数据类型: ${pointType}<br/>相对全局均值: ${sign}${deviation}`
      }
    },
    grid: { left: 12, right: 18, top: 20, bottom: 26, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: xData,
      axisLine: { lineStyle: { color: '#202020' } },
      axisTick: { show: false },
      axisLabel: { color: '#666', fontSize: 11, interval: 2 },
      axisPointer: currentHourLabel ? {
        show: true,
        value: currentHourLabel,
        snap: true,
        lineStyle: { color: 'rgba(212,175,55,0.22)', width: 1.2, type: 'dashed' },
        label: { show: false }
      } : { show: false }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      splitNumber: 4,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#666', fontSize: 11, formatter: (v) => Number(v).toFixed(2) },
      splitLine: { lineStyle: { type: 'dashed', color: '#1A1A1A' } }
    },
    series: [{
      name: 'Global Sentiment',
      type: 'line',
      smooth: 0.35,
      showSymbol: false,
      data: yData,
      lineStyle: { width: 2.2, color: '#D4AF37' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0.04, color: 'rgba(212,175,55,0.22)' },
          { offset: 0.55, color: 'rgba(212,175,55,0.06)' },
          { offset: 1, color: 'rgba(212,175,55,0.00)' }
        ])
      },
      markPoint: xData.length ? {
        symbol: 'circle',
        symbolSize: 12,
        itemStyle: {
          color: '#D4AF37',
          borderColor: '#0A0A0A',
          borderWidth: 3,
          shadowBlur: 18,
          shadowColor: 'rgba(212,175,55,0.55)'
        },
        label: {
          show: true,
          formatter: () => `LIVE ${currentTime.value}`,
          position: 'top',
          offset: [-18, -6],
          color: '#F7E7AF',
          fontSize: 10,
          fontWeight: 700,
          padding: [4, 8],
          backgroundColor: 'rgba(10,10,10,0.92)',
          borderRadius: 10,
          borderColor: 'rgba(212,175,55,0.32)',
          borderWidth: 1,
          shadowBlur: 12,
          shadowColor: 'rgba(212,175,55,0.18)'
        },
        data: [{ coord: [xData[xData.length - 1], yData[yData.length - 1]] }]
      } : undefined,
      markLine: {
        symbol: 'none',
        label: { show: false },
        lineStyle: { color: 'rgba(148,163,184,0.35)', type: 'dashed' },
        data: [{ yAxis: Number(globalAvg.value.toFixed(2)) }]
      }
    }, {
      name: 'Real Points',
      type: 'scatter',
      data: realPointData,
      symbolSize: 7,
      itemStyle: {
        color: '#F7E7AF',
        borderColor: '#D4AF37',
        borderWidth: 1.5,
        shadowBlur: 10,
        shadowColor: 'rgba(212,175,55,0.45)'
      },
      tooltip: { show: false },
      z: 5
    }, {
      name: 'Interpolated Points',
      type: 'scatter',
      data: interpolatedPointData,
      symbolSize: 4,
      itemStyle: {
        color: 'rgba(148,163,184,0.65)',
        borderColor: 'rgba(148,163,184,0.18)',
        borderWidth: 1
      },
      tooltip: { show: false },
      z: 4
    }]
  })
}

const fetch24HTrendData = async () => {
  try {
    const res = await getMarketTrend24H()
    if (res.code !== 200 || !res.data) throw new Error(res.msg || '24H 情绪走势获取失败')
    global24hTrend.value = {
      labels: res.data.labels || [],
      data: res.data.data || [],
      pointTypes: res.data.point_types || []
    }
  } catch (e) {
    ElMessage.error(e.message)
    global24hTrend.value = { labels: [], data: [], pointTypes: [] }
  }
}

const fetchDashboard = async () => {
  if (store.dashboardData) {
    dashboard.value = store.dashboardData
    await nextTick()
    initPie()
    return
  }
  try {
    const res = await getMarketDashboard()
    if (res.code !== 200 || !res.data) throw new Error(res.msg || '大盘数据获取失败')
    dashboard.value = res.data
    store.setDashboard(res.data)
    await nextTick()
    initPie()
  } catch (e) { ElMessage.error(e.message) }
}

const handleResize = () => {
  pieChart?.resize()
  globalTrendChart?.resize()
}

const startCurrentTimeHeartbeat = () => {
  currentTime.value = formatCurrentTime()

  if (currentTimeTimer) {
    clearInterval(currentTimeTimer)
    currentTimeTimer = null
  }
  if (currentTimeAlignTimer) {
    clearTimeout(currentTimeAlignTimer)
    currentTimeAlignTimer = null
  }

  const now = new Date()
  const delay = (60 - now.getSeconds()) * 1000 - now.getMilliseconds()

  currentTimeAlignTimer = setTimeout(() => {
    currentTime.value = formatCurrentTime()
    if (globalTrendChart) initGlobalTrend()

    currentTimeTimer = setInterval(() => {
      currentTime.value = formatCurrentTime()
      if (globalTrendChart) initGlobalTrend()
    }, 60000)
  }, delay)
}

onMounted(async () => {
  startCurrentTimeHeartbeat()
  await Promise.all([fetchDashboard(), fetch24HTrendData()])
  await nextTick()
  initGlobalTrend()
  window.addEventListener('resize', handleResize)
})
onActivated(() => {
  startCurrentTimeHeartbeat()
  window.addEventListener('resize', handleResize)
  nextTick(() => {
    pieChart?.resize()
    globalTrendChart?.resize()
  })
})
onDeactivated(() => {
  window.removeEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  pieChart?.dispose(); pieChart = null
  globalTrendChart?.dispose(); globalTrendChart = null
})
onUnmounted(() => {
  if (currentTimeTimer) {
    clearInterval(currentTimeTimer)
    currentTimeTimer = null
  }
  if (currentTimeAlignTimer) {
    clearTimeout(currentTimeAlignTimer)
    currentTimeAlignTimer = null
  }
})
</script>

<template>
  <section class="fade-in">
    <div class="mb-8">
      <h2 class="text-3xl font-light text-neutral-100 tracking-tight m-0">
        Market <span class="font-semibold" style="color:#D4AF37">Sentiment</span>
      </h2>
      <p class="text-neutral-500 mt-2 text-sm">基于全量用户 FinBERT 情感得分的实时聚合概览</p>
    </div>

    <!-- KPI 三卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">

      <!-- 情绪指数 -->
      <div class="bg-[#0A0A0A] border border-neutral-800/80 rounded-2xl p-7 relative overflow-hidden group hover:border-[#D4AF37]/40 transition-all duration-[var(--fx-duration)] ease-[var(--fx-ease)] hover:-translate-y-0.5 hover:shadow-[0_14px_32px_rgba(0,0,0,0.36)]">
        <div class="absolute top-0 right-0 p-6 opacity-5 group-hover:opacity-10 transition-opacity">
          <svg class="w-32 h-32 text-[#D4AF37]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        </div>
        <div class="relative z-10">
          <h3 class="text-neutral-500 text-xs font-semibold tracking-wider uppercase mb-3 flex items-center gap-2">
            Global Index
            <span class="tooltip-anchor group/info relative inline-flex">
              <svg class="w-3.5 h-3.5 text-[#D4AF37]/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 10v5"/><path d="M12 7h.01"/></svg>
              <span class="tooltip-panel tooltip-panel-center top-full z-30 mt-2 w-56 normal-case tracking-normal">全站历史总均值。基于数据库累积的全量发帖情感得分聚合计算，反映中长期大盘底座情绪。</span>
            </span>
          </h3>
          <div class="flex items-baseline gap-1">
            <span class="text-5xl font-light text-white tracking-tight">
              {{ globalAvg.toFixed(2) }}<span class="text-neutral-500">{{ globalAvg.toFixed(4).slice(-2) }}</span>
            </span>
          </div>
          <p class="text-sm text-neutral-400 mt-4 flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-neutral-600"></span>
            {{ sentimentLabel }}
          </p>
        </div>
      </div>

      <!-- 用户数 -->
      <div class="bg-[#0A0A0A] border border-neutral-800/80 rounded-2xl p-7 relative overflow-hidden group hover:border-neutral-600 transition-all duration-[var(--fx-duration)] ease-[var(--fx-ease)] hover:-translate-y-0.5 hover:shadow-[0_14px_32px_rgba(0,0,0,0.36)]">
        <div class="absolute top-0 right-0 p-6 opacity-5 group-hover:opacity-10 transition-opacity">
          <svg class="w-32 h-32 text-neutral-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2a5 5 0 1 0 0 10A5 5 0 0 0 12 2zM2 20a10 10 0 0 1 20 0"/></svg>
        </div>
        <div class="relative z-10">
          <h3 class="text-neutral-500 text-xs font-semibold tracking-wider uppercase mb-3">Profiled Users</h3>
          <div class="flex items-baseline gap-1">
            <span class="text-5xl font-light text-white tracking-tight">{{ totalUsers.toLocaleString() }}</span>
          </div>
          <p class="text-sm mt-4 flex items-center gap-2" style="color:#D4AF37">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
            已完成风险等级评定
          </p>
        </div>
      </div>

      <!-- 风险分布 -->
      <div class="bg-[#0A0A0A] border border-neutral-800/80 rounded-2xl p-7 flex flex-col justify-between transition-all duration-[var(--fx-duration)] ease-[var(--fx-ease)] hover:-translate-y-0.5 hover:border-neutral-700 hover:shadow-[0_14px_32px_rgba(0,0,0,0.36)]">
        <h3 class="text-neutral-500 text-xs font-semibold tracking-wider uppercase mb-6">Risk Distribution</h3>
        <div class="space-y-5">
          <div v-for="item in dashboard.risk_level_distribution" :key="item.risk_level"
            class="flex items-center justify-between group">
            <div class="flex items-center gap-3">
              <div class="w-1.5 h-4 rounded-sm" :style="{backgroundColor: riskColor(item.risk_level)}"></div>
              <span class="text-sm text-neutral-300 group-hover:text-white transition-colors">{{ item.risk_level }}</span>
            </div>
            <span class="text-sm font-mono text-neutral-400">{{ item.user_count.toLocaleString() }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 下半区：饼图 + 24H走势 -->
    <div class="grid grid-cols-1 lg:grid-cols-5 gap-6 mt-6 items-stretch">
      <div class="lg:col-span-2 bg-[#0A0A0A] border border-neutral-800/80 rounded-2xl p-8 relative overflow-hidden flex flex-col min-h-[480px]">
        <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[360px] h-[360px] rounded-full pointer-events-none"
          style="background:rgba(212,175,55,0.05);filter:blur(90px)"></div>

        <div class="w-full flex flex-wrap justify-between items-center gap-4 mb-6 relative z-10">
          <h3 class="text-base font-medium text-neutral-200 tracking-wide m-0">用户风险偏好全景分布</h3>
          <div class="flex flex-wrap gap-4">
            <div v-for="item in dashboard.risk_level_distribution" :key="item.risk_level"
              class="flex items-center gap-2 text-[11px] font-medium tracking-wide text-neutral-400 uppercase">
              <span class="w-2 h-2 rounded-full" :style="{backgroundColor: riskColor(item.risk_level), boxShadow: `0 0 10px ${riskColor(item.risk_level)}40`}" ></span>
              {{ item.risk_level }}
            </div>
          </div>
        </div>

        <div class="relative z-10 flex-1 min-h-[360px]">
          <div ref="pieRef" class="w-full h-full"></div>
          <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span class="text-neutral-500 text-xs tracking-widest uppercase mb-2">Total Users</span>
            <span class="text-5xl font-light font-mono tabular-nums text-white tracking-tighter leading-none">{{ totalUsers.toLocaleString() }}</span>
          </div>
        </div>
      </div>

      <div class="lg:col-span-3 ai-insight-panel bg-[#0A0A0A] border border-neutral-800/80 rounded-2xl p-8 relative overflow-hidden flex flex-col min-h-[480px]">
        <div class="flex items-center justify-between gap-4 mb-6 relative z-10">
          <div>
            <h3 class="text-base font-medium text-neutral-200 tracking-wide m-0">全站 24 小时情绪走势</h3>
            <p class="text-xs text-neutral-500 mt-2">Global 24H Sentiment Trend · 基于当前大盘情绪中枢生成的实时监控视图</p>
          </div>
          <div class="flex flex-col items-end gap-2 text-[11px] uppercase tracking-[0.24em] text-neutral-500">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-[#D4AF37] shadow-[0_0_10px_rgba(212,175,55,0.5)]"></span>
              Live Monitor
            </div>
            <div class="flex items-center gap-3 text-[10px] tracking-[0.18em] normal-case">
              <span class="inline-flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-[#F7E7AF] border border-[#D4AF37]"></span>真实点</span>
              <span class="inline-flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-slate-400/70 border border-slate-400/20"></span>插值点</span>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4 mb-6 relative z-10">
          <div class="rounded-xl border border-neutral-800 bg-neutral-950/70 px-4 py-3">
            <p class="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1">Current Bias</p>
            <p class="text-sm text-neutral-200 m-0">{{ sentimentLabel }}</p>
          </div>
          <div class="rounded-xl border border-neutral-800 bg-neutral-950/70 px-4 py-3 text-right">
            <div class="flex items-center justify-end gap-1.5 mb-1">
              <p class="text-[10px] uppercase tracking-[0.22em] text-neutral-500 m-0">24H Mean</p>
              <span class="tooltip-anchor group/info relative inline-flex">
                <svg class="w-3.5 h-3.5 text-[#D4AF37]/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 10v5"/><path d="M12 7h.01"/></svg>
                <span class="tooltip-panel tooltip-panel-right top-full z-30 mt-2 w-56 text-left normal-case tracking-normal">近24小时滚动均值。仅计算过去24小时内的新增发言情绪，反映短期大盘情绪的最新异动。</span>
              </span>
            </div>
            <p class="text-lg font-mono tabular-nums text-[#D4AF37] m-0">{{ rolling24hAvg.toFixed(4) }}</p>
          </div>
        </div>

        <div class="relative z-10 flex-1 min-h-[320px]">
          <div ref="globalTrendRef" class="w-full h-full"></div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
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
  background: rgba(5, 5, 5, 0.92);
  border: 1px solid rgba(212, 175, 55, 0.28);
  backdrop-filter: blur(12px);
  color: #A3A3A3;
  font-size: 11px;
  line-height: 1.55;
  box-shadow: 0 18px 32px rgba(0, 0, 0, 0.42), 0 0 0 1px rgba(212,175,55,0.04);
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
  border-left: 1px solid rgba(212, 175, 55, 0.28);
  border-top: 1px solid rgba(212, 175, 55, 0.28);
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
</style>
