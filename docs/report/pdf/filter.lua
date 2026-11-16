-- Pandoc filter for the PDF (docs/report/build_pdf.sh).
-- 1. A paragraph that holds only an image is centred, and the image keeps its alt text out of the
--    page (the chapters give the caption in the text under the figure).
-- 2. Every level-1 heading after the first starts a new page.
local seen_h1 = false

function Header(h)
  if h.level == 1 then
    if seen_h1 then
      return { pandoc.RawBlock('latex', '\\clearpage'), h }
    end
    seen_h1 = true
  end
end

function Para(p)
  if #p.content == 1 and p.content[1].t == 'Image' then
    local img = p.content[1]
    img.caption = {}
    return {
      pandoc.RawBlock('latex', '\\begin{center}'),
      pandoc.Para({ img }),
      pandoc.RawBlock('latex', '\\end{center}'),
    }
  end
end

-- 3. Code blocks wrap long lines (prompts and configs in the appendix).
function CodeBlock(cb)
  return pandoc.RawBlock('latex',
    '\\begin{Verbatim}[breaklines=true,breakanywhere=true,fontsize=\\scriptsize]\n'
    .. cb.text .. '\n\\end{Verbatim}')
end

-- 4. Inline code may break after "/", "_", "." and "-" (long paths in the text).
local esc = {
  ['\\'] = '\\textbackslash{}', ['{'] = '\\{', ['}'] = '\\}', ['#'] = '\\#',
  ['$'] = '\\$', ['%'] = '\\%', ['&'] = '\\&', ['_'] = '\\_\\allowbreak{}',
  ['^'] = '\\^{}', ['~'] = '\\~{}', ['/'] = '/\\allowbreak{}',
  ['.'] = '.\\allowbreak{}', ['-'] = '-\\allowbreak{}',
}
function Code(c)
  if FORMAT:match('latex') then
    local s = c.text:gsub('[\\{}#$%%&_^~/.%-]', function(ch) return esc[ch] end)
    return pandoc.RawInline('latex', '\\texttt{' .. s .. '}')
  end
end
