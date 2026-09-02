import { createApp } from 'vue'
import { ElBadge } from 'element-plus/es/components/badge/index'
import { ElButton } from 'element-plus/es/components/button/index'
import { ElDialog } from 'element-plus/es/components/dialog/index'
import { ElEmpty } from 'element-plus/es/components/empty/index'
import { ElForm, ElFormItem } from 'element-plus/es/components/form/index'
import { ElInput } from 'element-plus/es/components/input/index'
import { ElOption, ElSelect } from 'element-plus/es/components/select/index'
import { ElSwitch } from 'element-plus/es/components/switch/index'
import { ElTable, ElTableColumn } from 'element-plus/es/components/table/index'
import { ElTag } from 'element-plus/es/components/tag/index'
import 'element-plus/es/components/badge/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/switch/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/tag/style/css'

import App from './App.vue'
import './style.css'

const app = createApp(App)

app
  .component('ElBadge', ElBadge)
  .component('ElButton', ElButton)
  .component('ElDialog', ElDialog)
  .component('ElEmpty', ElEmpty)
  .component('ElForm', ElForm)
  .component('ElFormItem', ElFormItem)
  .component('ElInput', ElInput)
  .component('ElOption', ElOption)
  .component('ElSelect', ElSelect)
  .component('ElSwitch', ElSwitch)
  .component('ElTable', ElTable)
  .component('ElTableColumn', ElTableColumn)
  .component('ElTag', ElTag)
  .mount('#app')
