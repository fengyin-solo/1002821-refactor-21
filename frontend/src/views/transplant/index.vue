<template>
  <section class="page" data-module="transplant">
    <header class="page-head">
      <div>
        <h2>苗木移植管理</h2>
        <p class="page-desc">维护移植记录，围绕移植编号、移植树种、移植数量、移入位置做登记、筛选与状态流转，成活率按统一算法计算。</p>
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
              v-for="action in availableActions(row)"
              :key="action.name"
              class="link"
              :class="{ negative: action.negative }"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action.name }}
            </button>
            <button class="link" type="button" @click="doHandleLocation(row)">移入位置处理</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无苗木移植数据，可先登记移植记录</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">各移入位置成活情况</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in locationColumns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in locationStats" :key="item['移入位置'] || '空'">
          <td v-for="column in locationColumns" :key="column">{{ item[column] ?? '—' }}</td>
        </tr>
        <tr v-if="!locationStats.length">
          <td :colspan="locationColumns.length" class="empty-state">暂无移入位置成活数据</td>
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
type LocationStat = Record<string, string | number>
type ActionDef = { name: string; negative?: boolean }

const ENDPOINT = '/api/transplant'
const columns = ["移植编号", "移植树种", "移植数量", "移出位置", "移入位置", "移植日期", "成活数量", "成活率", "移植状态"]
const locationColumns = ["移入位置", "记录数", "移植数量", "成活数量", "待补录数量", "成活率"]
const statusFlow: Record<string, ActionDef[]> = {
  '待移植': [{ name: '安排移植' }],
  '已移植': [{ name: '成活上报' }, { name: '标记死亡', negative: true }],
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const stats = ref<{ label: string; value: string | number }[]>([])
const locationStats = ref<LocationStat[]>([])

function availableActions(row: Row): ActionDef[] {
  return statusFlow[String(row.status ?? '')] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function openCreate() {
  errorMessage.value = ''
  const code = window.prompt('移植编号（同一批苗重复登记只记一次）')?.trim()
  if (!code) return
  const species = window.prompt('移植树种')?.trim()
  if (!species) {
    errorMessage.value = '缺少移植树种，登记未提交'
    return
  }
  const quantity = window.prompt('移植数量（可不填，按待补录处理）')?.trim() ?? ''
  const moveIn = window.prompt('移入位置（可不填）')?.trim() ?? ''
  const moveOut = window.prompt('移出位置（可不填）')?.trim() ?? ''
  const values: Record<string, string> = { '移植编号': code, '移植树种': species }
  if (quantity) values['移植数量'] = quantity
  if (moveIn) values['移入位置'] = moveIn
  if (moveOut) values['移出位置'] = moveOut
  await submit(`${ENDPOINT}`, '移植记录登记失败', { method: 'POST', body: JSON.stringify({ values }) }, true)
}

async function runAction(action: ActionDef, row: Row) {
  errorMessage.value = ''
  const values: Record<string, string> = { action: action.name }
  if (action.name === '成活上报') {
    const input = window.prompt(`请输入「${row['移植编号']}」的成活数量（移植数量 ${row['移植数量']}）`)
    if (input === null) return
    values['成活数量'] = input.trim()
  }
  if (action.name === '安排移植') {
    const moveIn = window.prompt('移入位置（如已填写可直接留空确认）', String(row['移入位置'] ?? ''))
    if (moveIn === null) return
    values['移入位置'] = moveIn
  }
  if (action.name === '标记死亡' && !window.confirm(`确认把「${row['移植编号']}」标记为死亡？成活数量将按 0 计入。`)) {
    return
  }
  await submit(
    `${ENDPOINT}/${row.id}/actions`,
    '苗木移植动作未生效，请稍后重试',
    { method: 'POST', body: JSON.stringify({ values }) },
    true,
  )
}

async function doHandleLocation(row: Row) {
  errorMessage.value = ''
  const moveIn = window.prompt('归一处理移入位置（留空则保持原值）', String(row['移入位置'] ?? ''))
  if (moveIn === null) return
  const quantity = window.prompt('移植数量（数量缺失时在此补录，留空保持原值）', String(row['移植数量'] ?? ''))
  if (quantity === null) return
  const values: Record<string, string> = {}
  if (moveIn.trim()) values['移入位置'] = moveIn
  if (quantity.trim()) values['移植数量'] = quantity
  await submit(
    `${ENDPOINT}/${row.id}/location`,
    '移入位置处理失败，请稍后重试',
    { method: 'PUT', body: JSON.stringify({ values }) },
    true,
  )
}

async function submit(url: string, fallback: string, init: RequestInit, reloadAfter: boolean) {
  try {
    const response = await request(url, init)
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || fallback)
    }
    if (reloadAfter) await Promise.all([reload(), reloadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : fallback
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      throw new Error('移植统计读取失败')
    }
    const payload = await response.json()
    const byStatus = payload.by_status ?? {}
    stats.value = [
      { label: '移植总记录', value: payload.total ?? 0 },
      { label: '待移植苗木', value: byStatus['待移植'] ?? 0 },
      { label: '已成活苗木', value: byStatus['已成活'] ?? 0 },
      { label: '死亡苗木', value: byStatus['已死亡'] ?? 0 },
      { label: '综合成活率', value: payload.survival_rate ?? '—' },
    ]
    locationStats.value = payload.locations ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '移植统计读取失败'
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
  void reloadStats()
})
</script>
