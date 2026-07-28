export const ordinaryUserImageDemo = {
  productType: '山水册页意象纸质书签',
  sourceType: 'artifact',
  sourceName: 'Landscape（Met 65625）',
  era: '清代（1644–1911）',
  creator: '大都会艺术博物馆馆藏记录',
  useCase: '博物馆文创商店与日常阅读',
  audience: '年轻阅读者与博物馆文创消费者',
  material: '窄幅竹纤维纸书签配棉绳流苏，边缘压纹，便于夹入书页。',
  facts: [
    '馆藏题名为 Landscape。',
    '馆藏记录标示其为中国清代（1644–1911）。',
    '馆藏记录描述其为纸本水墨设色册页。',
  ],
  supplement: '单品主视图，避免人物、文字水印和未核实题跋。',
}

export async function fillOrdinaryUserImageBrief(page, brief = ordinaryUserImageDemo) {
  await page.getByLabel('产品类型').fill(brief.productType)
  await page.getByLabel('产品展示方式').selectOption({ label: '单品主视图' })
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
}

export async function assertAllVisibleEditableFieldsFilled(page) {
  const empty = await page.locator('.creation-form input:visible, .creation-form textarea:visible, .creation-form select:visible').evaluateAll((elements) => elements
    .filter((element) => !element.disabled && !String(element.value || '').trim())
    .map((element) => element.getAttribute('aria-label') || element.id || element.outerHTML.slice(0, 80)))
  if (empty.length) throw new Error(`演示 Brief 存在空的可编辑控件: ${empty.join(', ')}`)
}
