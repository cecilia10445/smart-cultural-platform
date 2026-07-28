<template>
  <Teleport to="body">
    <dialog v-if="open" ref="dialog" class="text-skill-dialog" aria-label="文本 Skill 生成详情" @cancel.prevent="close" @click.self="close">
      <div class="dialog-shell">
        <header><div><p>文本 Skill 生成</p><h2>业务生成详情</h2></div><button type="button" class="dialog-close" aria-label="关闭文本 Skill 生成详情" @click="close">×</button></header>
        <div class="dialog-body">
          <section><h3>产品文案</h3><p>{{ detail.product_copy }}</p></section>
          <section><h3>文字版设计说明</h3><p>{{ detail.image_design_spec }}</p></section>
          <section><h3>RAG 来源</h3><ul><li v-for="sourceId in sourceIds" :key="sourceId">{{ sourceId }}</li></ul></section>
          <section><h3>Agent 工具轨迹</h3><p>{{ detail.tool_call_name }} · skill_id={{ detail.selected_skill_id }}</p></section>
          <dl>
            <div><dt>加载的文本 Skill</dt><dd>{{ detail.selected_skill_id }}<span v-if="detail.skill_version"> · {{ detail.skill_version }}</span></dd></div>
            <div><dt>Qwen 请求</dt><dd>{{ qwenCalls }}</dd></div>
            <div><dt>数据库记录 ID</dt><dd>{{ detail.log_id }}</dd></div>
            <div><dt>完整性</dt><dd>{{ detail.artifact_integrity }}</dd></div>
          </dl>
        </div>
      </div>
    </dialog>
  </Teleport>
</template>

<script>
export default {
  name: 'TextSkillGenerationDialog',
  props: { open: Boolean, detail: { type: Object, default: () => ({}) } },
  emits: ['close'],
  computed: {
    sourceIds() { return Array.isArray(this.detail.source_ids) ? this.detail.source_ids.filter((value) => typeof value === 'string') : [] },
    qwenCalls() { const value = this.detail.actual_calls?.qwen; return Number.isInteger(value) && value >= 0 ? value : '—' },
  },
  mounted() { if (this.open) this.openDialog() },
  watch: { open(value) { if (value) this.$nextTick(this.openDialog); else if (this.$refs.dialog?.open) this.$refs.dialog.close() } },
  methods: {
    openDialog() { const dialog = this.$refs.dialog; if (dialog && !dialog.open) dialog.showModal() },
    close() { this.$refs.dialog?.close(); this.$emit('close') },
  },
}
</script>

<style scoped>
.text-skill-dialog{border:1px solid #c9c3b6;background:#fbfaf5;color:#17221f;padding:0;width:min(92vw,900px);max-height:90vh}.text-skill-dialog::backdrop{background:rgba(23,34,31,.62)}.dialog-shell{max-height:90vh;display:flex;flex-direction:column}.dialog-shell header{display:flex;justify-content:space-between;align-items:center;padding:1rem 1.25rem;border-bottom:1px solid #d4cec2}.dialog-shell header p{margin:0;color:#657066;font-size:.78rem;letter-spacing:.08em;text-transform:uppercase}.dialog-shell h2{margin:.2rem 0 0;font-size:clamp(1.25rem,2vw,1.8rem)}.dialog-close{border:1px solid #245244;background:#fffdf5;color:#245244;cursor:pointer;min-width:44px;min-height:44px;font-size:1.6rem}.dialog-body{overflow:auto;padding:1.25rem}.dialog-body section{padding:1rem 0;border-bottom:1px solid #d4cec2}.dialog-body h3{margin:0 0 .4rem;color:#245244;font-size:1rem}.dialog-body p{margin:0;white-space:pre-wrap;line-height:1.7;overflow-wrap:anywhere}.dialog-body ul{margin:.25rem 0 0;padding-left:1.2rem;line-height:1.7}.dialog-body dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;margin:1rem 0 0}.dialog-body dt{color:#657066;font-size:.8rem}.dialog-body dd{margin:.3rem 0 0;overflow-wrap:anywhere}@media(max-width:620px){.dialog-body dl{grid-template-columns:1fr}}
</style>
