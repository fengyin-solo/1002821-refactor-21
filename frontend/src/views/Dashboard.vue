<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <header class="page-head" style="margin-top: 24px;">
      <div>
        <h3>苗木移植成活情况</h3>
        <p class="page-desc">成活率随移植明细重算，与苗木移植页、苗木基地页取同一份数据。</p>
      </div>
    </header>
    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">整体成活率</span>
        <strong class="stat-value">{{ transplant.overallRate ?? '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">已成活批次</span>
        <strong class="stat-value">{{ transplant.statusCounts?.['已成活'] ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">数量待补录</span>
        <strong class="stat-value">{{ transplant.pendingQuantityBatches ?? 0 }}</strong>
      </article>
    </div>
    <table class="data-table">
      <thead>
        <tr><th>移入位置（已归一）</th><th>成活率</th></tr>
      </thead>
      <tbody>
        <tr v-for="item in transplant.locations ?? []" :key="item['移入位置']">
          <td>{{ item['移入位置'] }}</td>
          <td>{{ item['成活率'] }}</td>
        </tr>
        <tr v-if="!(transplant.locations ?? []).length">
          <td colspan="2" class="empty-state">暂无可重算的成活明细</td>
        </tr>
      </tbody>
    </table>

    <table class="data-table" style="margin-top: 24px;">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type TransplantSurvival = {
  overallRate: string
  pendingQuantityBatches: number
  statusCounts: Record<string, number>
  locations: { '移入位置': string; '成活率': string }[]
}

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
  transplantSurvival?: TransplantSurvival
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const transplant = ref<Partial<TransplantSurvival>>({})

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    transplant.value = payload.transplantSurvival ?? {}
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = []
  }
})
</script>
