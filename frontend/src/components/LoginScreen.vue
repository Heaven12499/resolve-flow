<script setup lang="ts">
import { reactive } from 'vue'

const emit = defineEmits<{
  submit: [username: string, password: string]
}>()

defineProps<{ loading: boolean }>()

const form = reactive({ username: '', password: '' })

const roles = [
  { username: 'agent', title: '客服工作台', description: '处理物流查询与标准优惠券审批' },
  { username: 'supervisor', title: '主管复核台', description: '处理退款、高风险售后与升级工单' },
  { username: 'admin', title: '管理员后台', description: '维护知识库与全局运营配置' },
]

function selectRole(username: string) {
  form.username = username
  form.password = ''
}

function submit() {
  emit('submit', form.username.trim(), form.password)
}
</script>

<template>
  <main class="login-shell">
    <section class="login-card">
      <span class="eyebrow">RESOLVEFLOW OPERATIONS</span>
      <h1>运营端登录</h1>
      <p>选择一个工作台，再输入该账号的演示密码。</p>
      <div class="role-selector" aria-label="选择登录角色">
        <button
          v-for="role in roles"
          :key="role.username"
          type="button"
          class="role-option"
          :class="{ selected: form.username === role.username }"
          @click="selectRole(role.username)"
        >
          <strong>{{ role.title }}</strong>
          <span>{{ role.description }}</span>
        </button>
      </div>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="账号"><el-input v-model="form.username" autocomplete="username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" @keyup.enter="submit" /></el-form-item>
        <el-button type="primary" :loading="loading" @click="submit">登录</el-button>
      </el-form>
    </section>
  </main>
</template>
