<template>
  <Teleport to="body">
    <dialog v-if="open" ref="dialog" class="product-dialog" aria-label="产品详情" @cancel.prevent="close" @click.self="close" aria-labelledby="product-dialog-title">
      <div class="product-dialog-shell">
        <header class="product-dialog-header"><h2 id="product-dialog-title">{{ detail.product_name || '产品详情' }}</h2><button type="button" class="dialog-close" aria-label="关闭产品详情" @click="close">×</button></header>
        <div class="product-dialog-body">
          <div class="product-dialog-image">
            <button v-if="detail.image_url && !imageError" type="button" class="image-preview-trigger" aria-label="放大产品图片" @click="previewOpen = true"><img :src="detail.image_url" :alt="detail.product_name || '产品展示图'" @error="imageError = true"></button>
            <div v-else class="image-unavailable" role="status"><p>图片暂时无法加载</p></div>
          </div>
          <div class="product-dialog-copy">
            <section v-for="field in textFields" :key="field.key" class="detail-field"><h3>{{ field.label }}</h3><p>{{ safeText(detail[field.key]) || '—' }}</p></section>
            <section class="detail-field"><h3>核心卖点</h3><ul v-if="detail.selling_points?.length"><li v-for="point in detail.selling_points" :key="point">{{ point }}</li></ul><p v-else>—</p></section>
            <section class="detail-field"><h3>文化资料与来源</h3><p>{{ factualText || '—' }}</p><ul v-if="safeCitations.length" class="citation-list"><li v-for="citation in safeCitations" :key="citation.source_id"><a :href="citation.source_url" target="_blank" rel="noopener noreferrer">{{ citation.title || citation.source_id }}</a></li></ul><p v-else-if="evidenceStatus === 'insufficient_evidence'">当前资料不足</p><p v-else>暂无可展示引用</p></section>
            <dl class="detail-meta"><div><dt>展示方式</dt><dd>{{ modeLabel }}</dd></div><div><dt>生成时间</dt><dd>{{ detail.generation_time || '—' }}</dd></div><div><dt>记录编号</dt><dd>{{ detail.log_id || '—' }}</dd></div></dl>
          </div>
        </div>
      </div>
    </dialog>
    <dialog v-if="previewOpen" ref="previewDialog" class="image-preview-dialog" @cancel.prevent="previewOpen = false" @click.self="previewOpen = false" aria-labelledby="image-preview-title">
      <h2 id="image-preview-title" class="sr-only">产品图片预览</h2><button type="button" class="dialog-close preview-close" aria-label="关闭图片预览" @click="previewOpen = false">×</button><img v-if="detail.image_url && !imageError" :src="detail.image_url" :alt="detail.product_name || '产品展示图'"><div v-else class="image-unavailable" role="status"><p>图片暂时无法加载</p></div>
    </dialog>
  </Teleport>
</template>
<script>
export default {
  name: 'ProductDetailDialog',
  props: { open: Boolean, detail: { type: Object, default: () => ({}) } },
  emits: ['close'],
  data: () => ({ previewOpen: false, imageError: false }),
  mounted() { if (this.open) this.$nextTick(() => { const d = this.$refs.dialog; if (d && !d.open) d.showModal() }) },
  computed: {
    modeLabel() { return ({ flat_front_back: '正反面', three_view: '三视图', single_hero: '单品主视图' })[this.detail.presentation_mode] || '—' },
    textFields() { return [{ key: 'creative_origin', label: '创意来源' }, { key: 'design_concept', label: '设计思路' }, { key: 'cultural_meaning', label: '文化意义' }] },
    evidenceStatus() { return ['grounded', 'insufficient_evidence'].includes(this.detail?.evidence_status) ? this.detail.evidence_status : 'insufficient_evidence' },
    factualText() { const v = this.detail?.factual_background; return typeof v === 'string' ? v : (v && typeof v === 'object' && !Array.isArray(v) && typeof v.text === 'string' ? v.text : '') },
    safeCitations() { if (this.evidenceStatus !== 'grounded') return []; const v = this.detail?.factual_background; const raw = Array.isArray(this.detail?.citations) ? this.detail.citations : (v && typeof v === 'object' && Array.isArray(v.citations) ? v.citations : []); return raw.filter((x) => x && typeof x === 'object' && typeof x.source_id === 'string' && typeof x.source_url === 'string').map((x) => ({ source_id: x.source_id, title: typeof x.title === 'string' ? x.title : '', source_url: x.source_url, license: typeof x.license === 'string' ? x.license : '' })) },
  },
  watch: { open(v) { this.imageError = false; this.previewOpen = false; if (v) this.$nextTick(() => { const d = this.$refs.dialog; if (d && !d.open) d.showModal() }) }, previewOpen(v) { this.$nextTick(() => { const d = this.$refs.previewDialog; if (v && d && !d.open) d.showModal(); else if (!v && d?.open) d.close() }) } },
  methods: { safeText(v) { return typeof v === 'string' ? v : '' }, close() { this.previewOpen = false; this.$refs.dialog?.close(); this.$emit('close') } },
}
</script>
<style scoped>
.product-dialog,.image-preview-dialog{border:1px solid #c9c3b6;background:#f9f7f0;color:#17221f;padding:0;width:min(94vw,1120px);max-height:90vh}.product-dialog::backdrop,.image-preview-dialog::backdrop{background:rgba(23,34,31,.62)}.product-dialog-shell{display:flex;flex-direction:column;max-height:90vh}.product-dialog-header{display:flex;justify-content:space-between;align-items:center;padding:1rem 1.25rem;border-bottom:1px solid #d4cec2}.product-dialog-header h2{margin:0;font-size:clamp(1.25rem,2vw,1.8rem)}.dialog-close{border:1px solid #245244;background:#fffdf5;color:#245244;cursor:pointer;min-width:44px;min-height:44px;font-size:1.6rem}.product-dialog-body{display:grid;grid-template-columns:minmax(300px,1fr) minmax(320px,1fr);min-height:0}.product-dialog-image{display:grid;place-items:center;padding:1.5rem;background:#fff;border-right:1px solid #d4cec2;min-height:420px}.image-preview-trigger{border:0;background:#fff;cursor:zoom-in;width:100%;height:100%;min-height:380px}.image-preview-trigger img,.image-preview-dialog img{width:100%;height:100%;object-fit:contain}.product-dialog-copy{overflow:auto;padding:1.25rem;min-width:0}.detail-field{margin-bottom:1.1rem}.detail-field h3{margin:0 0 .35rem;font-size:1rem;color:#245244}.detail-field p{margin:0;line-height:1.7;overflow-wrap:anywhere}.detail-field ul{margin:.3rem 0 0;padding-left:1.2rem;line-height:1.7}.citation-list a{overflow-wrap:anywhere;color:#245244}.detail-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.7rem;border-top:1px solid #d4cec2;padding-top:1rem}.detail-meta dt{font-size:.78rem;color:#657066}.detail-meta dd{margin:.2rem 0;overflow-wrap:anywhere}.image-preview-dialog{width:96vw;height:94vh;background:#17221f;display:grid;place-items:center}.image-preview-dialog img{max-width:94vw;max-height:88vh}.preview-close{position:absolute;right:1rem;top:1rem;background:#fffdf5}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:700px){.product-dialog{width:96vw}.product-dialog-body{grid-template-columns:1fr}.product-dialog-image{min-height:240px;border-right:0;border-bottom:1px solid #d4cec2}.image-preview-trigger{min-height:220px}.detail-meta{grid-template-columns:1fr 1fr}.product-dialog-copy{max-height:48vh}}
</style>
