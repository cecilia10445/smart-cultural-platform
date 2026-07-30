<template>
  <section v-if="decision" class="decision-card">
    <p class="eyebrow">需要你的确认</p><h3>{{ decision.title }}</h3><p>{{ decision.copy }}</p>
    <p v-if="status === 'waiting_text_feedback'" class="revision">已修改 {{ revisionCount }} / 4 次，还可修改 {{ Math.max(0, 4 - revisionCount) }} 次。</p>
    <button type="button" class="primary-button" :disabled="busy" @click="$emit('decide', decision.action)">{{ busy ? '正在提交' : decision.button }}</button>
  </section>
</template>
<script>
export default { name: 'AgentDecisionCard', props: { status: String, revisionCount: { type: Number, default: 0 }, busy: Boolean }, emits: ['decide'], computed: { decision() { return { waiting_brief_confirmation: { title: '确认需求方案', copy: '也可以直接在下方输入框补充或要求全部重新理解。', button: '确认需求方案', action: 'confirm_brief' }, waiting_text_feedback: { title: '确认产品设计方案', copy: '如需调整材质、配色或整体方向，请继续用自然语言描述。', button: '确认产品设计方案', action: 'confirm_product_text' }, waiting_image_confirmation: { title: '确认视觉方向', copy: '确认后将生成最终图片；第一版暂不支持修改图片或重新生成图片。', button: '确认生成图片', action: 'confirm_image_generation' } }[this.status] || null } } }
</script>
<style scoped>
.decision-card{border:1px solid #b9c9bc;background:#f4f7f0;padding:1.1rem;margin-top:1rem}.decision-card h3{margin:.15rem 0 .35rem;color:#245244}.decision-card p{margin:.2rem 0 .9rem;line-height:1.65;color:#475148}.eyebrow{font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;color:#728075!important}.revision{font-size:.86rem}.primary-button{min-height:42px}
</style>
