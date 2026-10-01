<template>
  <section class="page" data-module="transplant">
    <header class="page-head">
      <div>
        <h2>苗木移植管理</h2>
        <p class="page-desc">维护移植记录，围绕移植编号、移植树种、移植数量、移出位置做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记移植记录</button>
        <button class="btn" type="button" @click="exportRows">导出苗木移植清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无苗木移植数据，可先登记移植记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条苗木移植记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type SurvivalOverview = {
  overallRate: string
  pendingQuantityBatches: number
  duplicateBatches: number
  statusCounts: Record<string, number>
}

const ENDPOINT = '/api/transplant'
const columns = ["移植编号", "移植树种", "移植数量", "移出位置", "移入位置", "移植日期", "成活率", "移植状态"]
const actions = ["安排移植", "登记移植", "记录成活"]
const statuses = ["待移植", "已移植", "已成活", "已死亡"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
// 卡片数值全部来自后端同一份成活算法（survival-overview），不在前端另算。
const stats = ref([
  { label: '整体成活率', value: '—' },
  { label: '已成活批次', value: 0 },
  { label: '数量待补录', value: 0 },
  { label: '重复登记拦截', value: 0 },
])

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/survival-overview`)
    if (!response.ok) {
      return
    }
    const overview = (await response.json()) as SurvivalOverview
    stats.value = [
      { label: '整体成活率', value: overview.overallRate },
      { label: '已成活批次', value: overview.statusCounts['已成活'] ?? 0 },
      { label: '数量待补录', value: overview.pendingQuantityBatches },
      { label: '重复批次（已去重）', value: overview.duplicateBatches },
    ]
  } catch {
    // 卡片读取失败不阻塞明细列表，保留占位值即可。
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '移植记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  const payload: Record<string, string | number> = { action }
  if (action === '记录成活') {
    const input = window.prompt(`请输入「${row['移植编号']}」的成活数量（移植数量：${row['移植数量']}）`)
    if (input === null) {
      return
    }
    const survived = Number(input)
    if (!Number.isInteger(survived) || survived < 0) {
      errorMessage.value = '成活数量必须是不小于 0 的整数'
      return
    }
    payload['成活数量'] = survived
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    const result = await response.json().catch(() => null) as { message?: string } | null
    if (!response.ok || result === null) {
      throw new Error(result?.message ?? '苗木移植动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '苗木移植操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('移植记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '苗木移植列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
