export const threeViewDemo = {
  productType: '清代山水册页意象折叠阅读灯',
  sourceType: 'artifact',
  sourceName: 'Landscape（Met 65625）',
  era: '清代（1644–1911）',
  creator: '大都会艺术博物馆馆藏记录',
  useCase: '书房夜读与旅行阅读',
  audience: '年轻阅读者与博物馆文创消费者',
  material: '竹木折叠灯架配半透明纸质扩散罩，展开稳定、收拢便携。',
  facts: [
    '馆藏题名为 Landscape。',
    '该作品为册页。',
    '馆藏记录标示其为中国清代（1644–1911）。',
    '媒材为纸本水墨设色。',
  ],
  supplement: '避免人物与未核实题跋。',
  front: '正面以山水留白组织核心识别图案与产品名称，阅读灯展开状态清晰可辨。',
  back: '背面保留来源说明区与低饱和辅助纹样，留出操作提示且不重复正面主体。',
  side: '侧面交代折叠厚度、竹木连接和连续边饰，体现收拢后的便携结构。',
}

export async function fillThreeViewBrief(page, brief = threeViewDemo) {
  await page.getByLabel('产品类型').fill(brief.productType)
  await page.getByLabel('产品展示方式').selectOption({ label: '三视图' })
  await page.waitForSelector('text=三视图设计要求')
  await page.getByLabel('来源类型').selectOption(brief.sourceType)
  await page.getByLabel('文化原型或灵感来源').fill(brief.sourceName)
  await page.getByLabel('已知时代（可选）').fill(brief.era)
  await page.getByLabel('已知作者或机构（可选）').fill(brief.creator)
  await page.getByLabel('使用场景').fill(brief.useCase)
  await page.getByLabel('目标受众（可选）').fill(brief.audience)
  await page.getByLabel('造型与材质').fill(brief.material)
  await page.getByLabel('确认事实（每行一条）').fill(brief.facts.join('\n'))
  await page.getByRole('button', { name: '水墨写意' }).click()
  await page.getByLabel('补充画面要求（可选）').fill(brief.supplement)
  await page.getByLabel('正面设计要求').fill(brief.front)
  await page.getByLabel('背面设计要求').fill(brief.back)
  await page.getByLabel('侧面设计要求').fill(brief.side)
}

export async function assertAllVisibleEditableFieldsFilled(page) {
  const empty = await page.locator('.creation-form input:visible, .creation-form textarea:visible, .creation-form select:visible').evaluateAll((elements) => elements
    .filter((element) => !element.disabled && !String(element.value || '').trim())
    .map((element) => element.getAttribute('aria-label') || element.id || element.outerHTML.slice(0, 80)))
  if (empty.length) throw new Error(`演示 Brief 存在空的可编辑控件: ${empty.join(', ')}`)
}
