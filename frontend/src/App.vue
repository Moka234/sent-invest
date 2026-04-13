<script setup>
import { ref } from 'vue'
import MarketDashboard from './components/MarketDashboard.vue'
import UserRecommendation from './components/UserRecommendation.vue'

const activeTab = ref('global')
</script>

<template>
  <div class="min-h-screen flex flex-col" style="background:#050505">

    <!-- 顶部导航栏 黑金版 -->
    <header class="sticky top-0 z-50 backdrop-blur-xl border-b border-neutral-900" style="background:rgba(5,5,5,0.80)">
      <div class="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between w-full">

        <div class="flex items-center gap-4">
          <!-- 曜石金 Logo -->
          <div class="group relative w-12 h-12 rounded-xl flex items-center justify-center overflow-hidden"
            style="background:linear-gradient(to bottom,#1C1C1C,#050505);border:1px solid #2A2A2A;box-shadow:0 4px 15px rgba(0,0,0,0.8),inset 0 1px 0 rgba(255,255,255,0.1)">
            <div class="absolute -bottom-4 w-10 h-10 rounded-full transition-all duration-500 group-hover:scale-125"
              style="background:rgba(212,175,55,0.20);filter:blur(16px)"></div>
            <div class="absolute inset-0 bg-gradient-to-tr from-transparent via-white/5 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000 ease-in-out"></div>
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-[26px] h-[26px] relative z-10" style="filter:drop-shadow(0 0 8px rgba(212,175,55,0.3))">
              <defs>
                <linearGradient id="gold-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#FFF7D6"/>
                  <stop offset="35%" stop-color="#D4AF37"/>
                  <stop offset="100%" stop-color="#8C660A"/>
                </linearGradient>
              </defs>
              <path d="M12 2L4 7v10l8 5 8-5V7l-8-5z" stroke="url(#gold-grad)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M12 2v20" stroke="url(#gold-grad)" stroke-width="1.5" stroke-opacity="0.3" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M4 7l16 10" stroke="url(#gold-grad)" stroke-width="1.5" stroke-opacity="0.3" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M20 7L4 17" stroke="url(#gold-grad)" stroke-width="1.5" stroke-opacity="0.3" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="12" cy="12" r="2.5" fill="url(#gold-grad)"/>
            </svg>
          </div>

          <div>
            <h1 class="text-xl font-bold tracking-widest uppercase m-0"
              style="background:linear-gradient(to right,#f5f5f5,#737373);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">
              SentInvest
            </h1>
            <p class="text-[11px] text-neutral-500 tracking-wider uppercase mt-0.5 m-0">Private Wealth AI Engine</p>
          </div>
        </div>

        <!-- System Active 呼吸灯 -->
        <div class="flex items-center gap-3 px-4 py-2 rounded-full border border-neutral-800/80" style="background:rgba(23,23,23,0.5)">
          <div class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style="background:#D4AF37"></span>
            <span class="relative inline-flex rounded-full h-2 w-2" style="background:#D4AF37"></span>
          </div>
          <span class="text-xs font-medium text-neutral-400 tracking-wide uppercase">System Active</span>
        </div>
      </div>
    </header>

    <!-- Main -->
    <main class="max-w-7xl mx-auto px-6 py-10 w-full flex-1">
      <div class="flex space-x-6 border-b border-neutral-900 mb-10 w-full">
        <button
          @click="activeTab = 'global'"
          :class="['pb-4 text-sm font-medium tracking-wide transition-all duration-300 relative cursor-pointer', activeTab === 'global' ? 'text-[#D4AF37]' : 'text-neutral-500 hover:text-neutral-300']"
        >
          全站情绪大盘
          <div v-if="activeTab === 'global'" class="absolute bottom-0 left-0 w-full h-[2px] bg-gradient-to-r from-[#D4AF37] to-amber-700"></div>
        </button>
        <button
          @click="activeTab = 'personal'"
          :class="['pb-4 text-sm font-medium tracking-wide transition-all duration-300 relative cursor-pointer', activeTab === 'personal' ? 'text-[#D4AF37]' : 'text-neutral-500 hover:text-neutral-300']"
        >
          个人智能推荐中心
          <div v-if="activeTab === 'personal'" class="absolute bottom-0 left-0 w-full h-[2px] bg-gradient-to-r from-[#D4AF37] to-amber-700"></div>
        </button>
      </div>

      <KeepAlive>
        <component :is="activeTab === 'global' ? MarketDashboard : UserRecommendation" />
      </KeepAlive>
    </main>
  </div>
</template>
