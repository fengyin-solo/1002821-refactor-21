<template>
  <section class="page" data-module="seedling">
    <header class="page-head">
      <div>
        <h2>苗木基地管理</h2>
        <p class="page-desc">维护苗圃，围绕苗圃编号、苗圃名称、苗圃面积、培育品种做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记苗圃</button>
        <button class="btn" type="button" @click="exportRows">导出苗木基地清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <header class="page-head" style="margin-top: 16px;">
      <div>
        <h3>出圃苗木移植成活情况</h3>
        <p class="page-desc">按归一后的移入位置汇总，率值与苗木移植管理页、运营概览看板是同一份算法。</p>
      </div>
    </header>
    <table class="data-table">
      <thead>
        <tr><th>移入位置（已归一）</th><th>成活率</th></tr>
      </thead>
      <tbody>
        <tr v-for="item in transplantLocations" :key="item['移入位置']">
          <td>{{ item['移入位置'] }}</td>
          <td>{{ item['成活率'] }}</td>
        </tr>
        <tr v-if="!transplantLocations.length">
          <td colspan="2" class="empty-state">暂无可重算的移植成活明细</td>
        </tr>
      </tbody>
    </table>

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
          <td :colspan="columns.length + 1" class="empty-state">暂无苗木基地数据，可先登记苗圃</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条苗木基地记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/seedling'
const columns = ["苗圃编号", "苗圃名称", "苗圃面积", "培育品种", "出圃周期", "在圃数量", "管护人员", "苗圃状态"]
const actions = ["登记出圃", "休整轮作", "废弃苗圃"]
const statuses = ["正常", "出圃中", "休整中", "已废弃"]
const stats = [{"label": "正常苗圃", "value": 0}, {"label": "出圃苗圃", "value": 0}, {"label": "休整苗圃", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
// 直接取苗木移植的统一成活口径，本页不另算，保证和移植页看到的是同一个数。
const transplantLocations = ref<{ '移入位置': string; '成活率': string }[]>([])

async function loadTransplantSurvival() {
  try {
    const response = await request('/api/transplant/survival-overview')
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    transplantLocations.value = payload.locations ?? []
  } catch {
    // 成活情况读取失败不影响苗圃台账本身。
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
  errorMessage.value = '苗圃登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('苗木基地动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '苗木基地操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('苗圃列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '苗木基地列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadTransplantSurvival()
})
</script>
