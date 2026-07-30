<template>
  <section class="agent-timeline" aria-label="协作过程">
    <h3>协作过程</h3>
    <ol v-if="steps.length"><li v-for="step in steps" :key="step.id" :class="`is-${step.status}`">
      <span class="step-dot" aria-hidden="true"></span><div><strong>{{ labels[step.stage] || step.stage }}</strong><small>{{ statusLabels[step.status] || step.status }}</small><p>{{ step.summary || '正在整理此阶段内容。' }}</p><em v-if="step.tool">{{ step.tool }}</em><p v-if="step.error?.message" class="step-error">{{ step.error.message }}</p></div>
    </li></ol>
    <p v-else class="muted">你的协作轨迹会显示在这里。</p>
  </section>
</template>
<script>
export default { name: 'AgentDialogueTimeline', props: { steps: { type: Array, default: () => [] } }, data: () => ({ labels: { extracting_brief: '理解需求', generating_product_text: '生成产品设计', building_visual_prompt: '整理视觉方向' }, statusLabels: { pending: '等待中', running: '进行中', completed: '已完成', failed: '未完成' } }) }
</script>
<style scoped>
.agent-timeline{border-top:1px solid #d4cec2;padding-top:1rem}.agent-timeline h3{margin:0 0 .65rem;color:#245244;font-size:1rem}.agent-timeline ol{list-style:none;margin:0;padding:0;display:grid;gap:.75rem}.agent-timeline li{display:grid;grid-template-columns:14px 1fr;gap:.65rem}.step-dot{width:10px;height:10px;border:1px solid #89948a;border-radius:50%;margin-top:.25rem;background:#fffdf5}.is-completed .step-dot{background:#245244;border-color:#245244}.is-running .step-dot{background:#d9a441;border-color:#d9a441}.is-failed .step-dot{background:#b74b3c;border-color:#b74b3c}.agent-timeline strong{font-size:.9rem}.agent-timeline small,.agent-timeline em{margin-left:.45rem;color:#657066;font-style:normal;font-size:.76rem}.agent-timeline p{margin:.18rem 0 0;color:#475148;font-size:.86rem;line-height:1.55}.agent-timeline .step-error{color:#9a372d}.muted{color:#657066;font-size:.88rem}
</style>
