export const SUPPLEMENT_MAX_LENGTH = 32

export const DIMENSION_OPTIONS = {
  culturalContext: [
    { id: 'song', name: '宋代审美', promptText: '宋代审美' },
    { id: 'dunhuang', name: '敦煌壁画', promptText: '敦煌壁画' },
    { id: 'ink', name: '文人写意', promptText: '文人写意' },
    { id: 'blueWhite', name: '青花瓷', promptText: '青花瓷' },
    { id: 'woodblock', name: '传统版画', promptText: '传统版画' },
    { id: 'contemporary', name: '东方当代', promptText: '东方当代' },
  ],
  medium: [
    { id: 'gongbi', name: '工笔设色', promptText: '工笔设色' },
    { id: 'mineral', name: '矿物重彩', promptText: '矿物重彩' },
    { id: 'inkWash', name: '宣纸水墨', promptText: '宣纸水墨' },
    { id: 'blueWhite', name: '釉下青花', promptText: '釉下青花' },
    { id: 'woodblock', name: '木版套色', promptText: '木版套色' },
    { id: 'graphic', name: '现代平面', promptText: '现代平面' },
  ],
  palette: [
    { id: 'qingGreen', name: '青绿矿彩', promptText: '青绿矿彩' },
    { id: 'dunhuang', name: '朱砂石青鎏金', promptText: '朱砂石青鎏金' },
    { id: 'ink', name: '墨色层次', promptText: '墨色层次' },
    { id: 'blueWhite', name: '靛青瓷白', promptText: '靛青瓷白' },
    { id: 'woodblock', name: '朱红靛蓝', promptText: '朱红靛蓝' },
    { id: 'muted', name: '低饱和中性色', promptText: '低饱和中性色' },
  ],
  composition: [
    { id: 'openSpace', name: '疏朗留白', promptText: '疏朗留白' },
    { id: 'narrative', name: '平面叙事', promptText: '平面叙事' },
    { id: 'expressive', name: '大面积留白', promptText: '大面积留白' },
    { id: 'pattern', name: '中心纹样', promptText: '中心纹样' },
    { id: 'silhouette', name: '简化轮廓', promptText: '简化轮廓' },
    { id: 'geometry', name: '几何秩序', promptText: '几何秩序' },
  ],
}

export const VISUAL_DIRECTIONS = [
  {
    id: 'song-qinglu',
    name: '宋韵青绿',
    summary: '以宋代审美和青绿矿彩呈现含蓄、清雅的画面。',
    dimensions: { culturalContext: 'song', medium: 'gongbi', palette: 'qingGreen', composition: 'openSpace' },
  },
  {
    id: 'dunhuang-rich-color',
    name: '敦煌重彩',
    summary: '以壁画矿物重彩、朱砂石青和装饰性叙事组织画面。',
    dimensions: { culturalContext: 'dunhuang', medium: 'mineral', palette: 'dunhuang', composition: 'narrative' },
  },
  {
    id: 'ink-expression',
    name: '水墨写意',
    summary: '以宣纸水墨、墨色层次和留白表达意境，不追求摄影写实。',
    dimensions: { culturalContext: 'ink', medium: 'inkWash', palette: 'ink', composition: 'expressive' },
  },
  {
    id: 'blue-white-pattern',
    name: '青花纹样',
    summary: '以靛青瓷白和中心纹样组织，适合包装与文创图案。',
    dimensions: { culturalContext: 'blueWhite', medium: 'blueWhite', palette: 'blueWhite', composition: 'pattern' },
  },
  {
    id: 'woodblock-overprint',
    name: '木版套色',
    summary: '保留刀痕与套色层次，以简化轮廓完成海报或插画画面。',
    dimensions: { culturalContext: 'woodblock', medium: 'woodblock', palette: 'woodblock', composition: 'silhouette' },
  },
  {
    id: 'contemporary-east',
    name: '当代东方',
    summary: '将传统元素转译为现代平面语言，适合品牌视觉和数字媒介。',
    dimensions: { culturalContext: 'contemporary', medium: 'graphic', palette: 'muted', composition: 'geometry' },
  },
]

function optionPrompt(dimension, optionId) {
  return DIMENSION_OPTIONS[dimension].find((option) => option.id === optionId)?.promptText || ''
}

export function buildStylePrompt(dimensions, supplement = '') {
  const parts = [
    optionPrompt('culturalContext', dimensions.culturalContext),
    optionPrompt('medium', dimensions.medium),
    optionPrompt('palette', dimensions.palette),
    optionPrompt('composition', dimensions.composition),
  ]
  const normalizedSupplement = supplement.trim()

  if (normalizedSupplement) {
    parts.push(`补充：${normalizedSupplement}`)
  }

  return parts.filter(Boolean).join('；')
}

for (const direction of VISUAL_DIRECTIONS) {
  direction.promptText = buildStylePrompt(direction.dimensions)
}

export const DEFAULT_DIRECTION_ID = VISUAL_DIRECTIONS[0].id
