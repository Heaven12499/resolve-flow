<script setup lang="ts">
import { reactive } from 'vue'

const emit = defineEmits<{
  submit: [username: string, password: string]
}>()

defineProps<{ loading: boolean }>()

const form = reactive({ username: '', password: '' })

function submit() {
  emit('submit', form.username.trim(), form.password)
}
</script>

<template>
  <main class="login-shell">
    <section class="login-card">
      <span class="eyebrow">RESOLVEFLOW OPERATIONS</span>
      <h1>运营端登录</h1>
      <p>使用已配置的客服、主管或管理员账号继续。</p>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="账号"><el-input v-model="form.username" autocomplete="username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" @keyup.enter="submit" /></el-form-item>
        <el-button type="primary" :loading="loading" @click="submit">登录</el-button>
      </el-form>
    </section>
  </main>
</template>
