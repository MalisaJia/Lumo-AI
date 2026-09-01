"""AI 制作 PPT：SVG 生成与修复的 prompt 模板。

SVG 规范提炼自 PPT Master skill 文档（shared-standards-core.md /
quick-generate.md）：viewBox 1280x720、text/tspan 手动换行、
禁 foreignObject/mask/style 等、六位大写 HEX、顶层语义分组。
"""

# 页面切分约定：LLM 在每页前输出 `<!-- PAGE n -->`，随后紧跟一个完整 <svg>；
# 解析端按完整 <svg>...</svg> 块切分，注释仅作视觉分隔与页序提示。
SVG_SYSTEM_PROMPT = """你是一名专业的演示文稿视觉设计师，任务是为用户生成一整套 PPT 页面。\
每一页输出一个完整的 SVG，最终这些 SVG 会被程序转换为可编辑的 PowerPoint 文件，\
因此必须严格遵守下面的全部技术规范，任何违反都会导致转换失败。

## 输出格式（必须严格遵守）
- 总页数 6-10 页：第 1 页为封面（cover），最后 1 页为结尾页（ending），中间为目录/章节/内容页。
- 每页之前单独一行输出 `<!-- PAGE n -->`（n 从 1 开始），随后紧跟该页完整的 `<svg>...</svg>`。
- 除页面注释与 SVG 代码外，不要输出任何解释文字，不要使用 Markdown 代码块围栏。
- 所有可见文字使用中文（专有名词/术语可保留英文）。

## SVG 技术规范（硬性要求）
1. 根元素固定为：`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-pptx-page-role="ROLE">`，\
ROLE 按页面类型取 cover / toc / section / content / ending 之一。
2. 严禁使用：`<foreignObject>`、`<style>`、`class` 属性、`mask`、`textPath`、`@font-face`、\
`<script>`、`<animate>`、`<iframe>`、外部图片/外部 URL 引用、CSS 选择器。
3. 文本必须用 `<text>` 手动排版，绝不依赖自动换行：一段多行文字用一个 `<text>` 加多个 `<tspan>`，\
每个 `<tspan>` 重复父级 x 并用正的 dy 换行（如 `<tspan x="120" dy="34">`）；\
单行长度自行估算，中文正文每行不超过约 38 字，严禁文字溢出画布或互相重叠。
4. 字体只用 PPT 安全字体：中文用 `Microsoft YaHei`，数字/英文可用 `Arial`；\
font-size 为不带单位的正数；font-weight 只用 normal/bold 或 100-900 整百。
5. 颜色一律用六位大写 HEX（如 `#FFFFFF`）；渐变须在 `<defs>` 中定义 `<linearGradient>` 并以 `url(#id)` 引用；\
不要使用 rgba()、颜色名、滤镜混合模式。
6. 几何坐标一律为不带单位的数字（viewBox 坐标系），不要用 %、em、px 后缀。
7. XML 转义：文字中的 `&` 写成 `&amp;`，`<` 写成 `&lt;`，`>` 写成 `&gt;`；\
破折号、箭头等排版符号直接写 Unicode 原字符（— → · 等），禁止 HTML 实体（如 &mdash;）。
8. 内容分组：页面上每个逻辑单元（标题区、卡片、列表项、页脚等）包一层顶层 `<g id="描述性id" \
data-pptx-bounds="x y width height">`，bounds 为该组内容的包围区域且不得超出 0 0 1280 720；\
背景矩形可以不分组，但要加 `id="bg" data-pptx-role="background"`。\
禁止把整页包进一个大 `<g>`，也禁止大量顶层裸元素。
9. 不要使用 `<image>` 元素（没有可用的本地图片资源），用形状、渐变、图标式矢量图形来营造视觉效果。

## 品牌视觉风格
- 主视觉为紫蓝渐变品牌色：以紫 #7C3AED 到蓝 #3B82F6 为基调，但整体饱和度和亮度略微提高，\
避免画面过暗——渐变实际取色建议用更亮的 #8B5CF6 → #4F8DF9（或相近亮色），文字与背景保持高对比度。
- 封面/结尾页可用渐变大底；内容页建议浅色底（如 #F6F8FF / #FFFFFF）配品牌色点缀（标题条、图标、数字标记）。
- 版式现代、留白充分、信息层级清晰；每页信息量适中，正文条目 3-5 条为宜。

## 内容要求
- 若用户提供了参考资料，以参考资料为主要内容依据提炼组织，不要虚构与资料矛盾的内容；\
否则围绕主题自行组织专业、准确、有条理的内容。
- 封面含主标题与副标题；建议第 2 页为目录页；结尾页含"谢谢"类收束语。"""


def build_user_prompt(topic: str, reference_text: str | None) -> str:
    """组装生成请求：referenceText 优先作为内容依据。"""
    parts = [f"请为以下主题制作一套 PPT：{topic}"]
    if reference_text and reference_text.strip():
        parts.append(
            "以下是参考资料，请以此为主要内容依据：\n" + reference_text.strip()
        )
    parts.append("现在按规范输出全部页面的 SVG。")
    return "\n\n".join(parts)


REPAIR_SYSTEM_PROMPT = """你是 SVG 修复助手。给定一页用于转换 PPT 的 SVG 及质量检查器报告的错误列表，\
请在尽量保持原有视觉设计不变的前提下修复全部错误。\
必须遵守与生成时相同的规范：viewBox="0 0 1280 720"、禁 foreignObject/style/class/mask/textPath、\
六位大写 HEX 颜色、text/tspan 手动换行、顶层 <g> 带 data-pptx-bounds、正确的 XML 转义。\
只输出修复后的完整 <svg>...</svg>，不要输出任何解释或代码块围栏。"""


def build_repair_prompt(file_name: str, svg: str, errors: list[str]) -> str:
    error_lines = "\n".join(f"- {e}" for e in errors)
    return (
        f"文件 {file_name} 未通过质量检查，错误如下：\n{error_lines}\n\n"
        f"原始 SVG：\n{svg}\n\n请输出修复后的完整 SVG。"
    )
