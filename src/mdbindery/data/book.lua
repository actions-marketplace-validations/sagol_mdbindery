--[[
mdbindery filter for pandoc, used in two phases (env MDBINDERY_PHASE).

file  (one Markdown file, gfm -> json)
  * raw HTML at any depth: anchors -> spans, <div class> markers -> Divs, HTML
    blocks parsed by pandoc's HTML reader, inline tags converted (<br>, <sup>,
    <b>, <img>, <a> ...) or removed with a report, comments dropped
  * images: paths resolved against the file's folder ("/" = repository root);
    image alone in a paragraph with a title -> figure with caption; title
    starting with "full-page" -> full-page figure; missing, remote, and
    outside images reported and replaced by a text placeholder
  * citations: reference links whose label is a citation label -> [n] links
    to the generated reference list
  * optional: wide tables -> cards
  * every identifier prefixed with the file key
  * internal links -> mdbindery://<key>/<fragment>; other local files -> source_url
  * JSON report to ctx.report

links (merged book, json -> json)
  * mdbindery:// links resolved against existing identifiers; report written

File access goes through pandoc.system and pandoc.path (Unicode-safe on Windows).
]]

local json = pandoc.json
local utils = pandoc.utils
local env = pandoc.system.environment()
local phase = env.MDBINDERY_PHASE

local ctx = json.decode(pandoc.system.read_file(env.MDBINDERY_CTX))

local function write_report(t)
  pandoc.system.write_file(ctx.report, json.encode(t))
end

local function url_decode(s)
  return (s:gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end))
end

local function url_encode_path(s)
  return (s:gsub("[^%w%-%._~/]", function(c) return string.format("%%%02X", string.byte(c)) end))
end

local function set_of(list)
  local t = {}
  for _, v in ipairs(list or {}) do t[v] = true end
  return t
end

local function exists(p) return pandoc.path.exists(p) end

local function is_file(p)
  if not pandoc.path.exists(p) then return false end
  return not pcall(pandoc.system.list_directory, p)
end

local function is_url(s) return s:match("^%a[%w+.-]*:") ~= nil and not s:match("^%a:[/\\]") end

-- normalize a/b/../c and ./ segments; keep a leading "/", "//" (UNC), or drive letter;
-- a relative path that climbs above its start keeps its leading "../" segments
local function normalize(path)
  path = path:gsub("\\", "/")
  local prefix = path:match("^%a:/") or path:match("^//") or (path:sub(1, 1) == "/" and "/" or "")
  local parts, up = {}, 0
  for seg in path:sub(#prefix + 1):gmatch("[^/]+") do
    if seg == ".." then
      if #parts > 0 then
        table.remove(parts)
      elseif prefix == "" then
        up = up + 1
      end
    elseif seg ~= "." then
      table.insert(parts, seg)
    end
  end
  for _ = 1, up do table.insert(parts, 1, "..") end
  return prefix .. table.concat(parts, "/")
end

local function join(a, b)
  if a == nil or a == "" then return b end
  return a .. "/" .. b
end

local function under(path, root)
  if root == nil or root == "" then return true end
  local p, r = normalize(path), normalize(root)
  if p:match("^%a:/") then p, r = p:lower(), r:lower() end
  return p == r or p:sub(1, #r + 1) == r .. "/"
end

-- ------------------------------------------------------------ report state
local report = {
  ids = {}, h1 = nil, wide_tables = {}, external = {}, images = {},
  html_removed = {}, html_blocks = 0, h1_fix = "", moved_before_h1 = 0,
  cited = {}, math = {}, html_links = 0,
}
local function note_removed(tag)
  report.html_removed[tag] = (report.html_removed[tag] or 0) + 1
end

-- ---------------------------------------------------------------- raw HTML
local ENTITIES = { amp = "&", lt = "<", gt = ">", quot = '"', apos = "'", nbsp = "\u{a0}" }
local function decode_entities(s)
  s = s:gsub("&#[xX](%x+);", function(h) return utf8.char(tonumber(h, 16)) end)
  s = s:gsub("&#(%d+);", function(d) return utf8.char(tonumber(d)) end)
  return (s:gsub("&(%a+);", function(n) return ENTITIES[n] or ("&" .. n .. ";") end))
end

local function parse_tag(raw)
  local close, name, attrs, selfclose = raw:match("^%s*<%s*(/?)%s*([%a][%w%-]*)(.-)(/?)%s*>%s*$")
  if not name then return nil end
  local a = {}
  for k, v in attrs:gmatch('([%w_:%-]+)%s*=%s*"([^"]*)"') do a[k:lower()] = decode_entities(v) end
  for k, v in attrs:gmatch("([%w_:%-]+)%s*=%s*'([^']*)'") do a[k:lower()] = decode_entities(v) end
  for k, v in attrs:gmatch("([%w_:%-]+)%s*=%s*([^%s\"'>]+)") do
    if a[k:lower()] == nil then a[k:lower()] = decode_entities(v) end
  end
  return { close = close == "/", name = name:lower(), attrs = a, selfclose = selfclose == "/" }
end

local VOID = set_of{ "br", "img", "wbr", "hr", "input", "meta", "link", "source", "col" }
local WRAP = {
  sup = function(c) return pandoc.Superscript(c) end,
  sub = function(c) return pandoc.Subscript(c) end,
  b = function(c) return pandoc.Strong(c) end,
  strong = function(c) return pandoc.Strong(c) end,
  i = function(c) return pandoc.Emph(c) end,
  em = function(c) return pandoc.Emph(c) end,
  u = function(c) return pandoc.Underline(c) end,
  ins = function(c) return pandoc.Underline(c) end,
  s = function(c) return pandoc.Strikeout(c) end,
  del = function(c) return pandoc.Strikeout(c) end,
  strike = function(c) return pandoc.Strikeout(c) end,
  kbd = function(c) return pandoc.Code(utils.stringify(c)) end,
  code = function(c) return pandoc.Code(utils.stringify(c)) end,
  q = function(c) return pandoc.Quoted("DoubleQuote", c) end,
  small = function(c) return pandoc.Span(c, pandoc.Attr("", { "small" })) end,
  mark = function(c) return pandoc.Span(c, pandoc.Attr("", { "mark" })) end,
}
-- tags whose markup is dropped silently while the content stays
local TRANSPARENT = set_of{ "span", "font", "center", "p", "div", "abbr", "cite", "dfn", "time", "var", "samp",
                            "details", "summary", "picture", "figure", "figcaption", "big", "tt" }
-- block tags pandoc's HTML reader turns into document structure
local STRUCTURAL = set_of{ "table", "tr", "td", "th", "thead", "tbody", "tfoot", "caption", "colgroup", "ul", "ol",
                           "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "dl", "dt", "dd", "a", "img" }

-- HTML alt semantics: no alt attribute = missing alt text; alt="" = decorative image
local function image_from_attrs(a)
  local alt = a.alt and pandoc.Inlines(a.alt) or pandoc.Inlines{}
  local img = pandoc.Image(alt, a.src or "", a.title or "")
  if a.alt == nil then
    img.attributes["data-mdbindery-alt"] = "missing"
  elseif a.alt == "" then
    img.attributes["data-mdbindery-alt"] = "decorative"
  end
  return img
end

local function convert_inlines(inls)
  local out = pandoc.Inlines{}
  local i = 1
  while i <= #inls do
    local el = inls[i]
    if el.t == "RawInline" and el.format:match("html") then
      local text = el.text
      if text:match("^%s*<!%-%-") then
        i = i + 1  -- comment
      else
        local tag = parse_tag(text)
        if not tag then
          note_removed("unparsed"); i = i + 1
        elseif tag.name == "a" and not tag.close and (tag.attrs.id or tag.attrs.name) and not tag.attrs.href then
          out:insert(pandoc.Span({}, pandoc.Attr(tag.attrs.id or tag.attrs.name)))
          i = i + 1
          if inls[i] and inls[i].t == "RawInline" and inls[i].text:match("^%s*</a>%s*$") then i = i + 1 end
        elseif tag.name == "br" then
          out:insert(pandoc.LineBreak()); i = i + 1
        elseif tag.name == "img" then
          out:insert(image_from_attrs(tag.attrs)); i = i + 1
        elseif VOID[tag.name] then
          note_removed(tag.name); i = i + 1
        elseif not tag.close and (WRAP[tag.name] or tag.name == "a") then
          -- find the matching close tag in this inline list
          local depth, j = 1, i + 1
          while j <= #inls do
            local e = inls[j]
            if e.t == "RawInline" and e.format:match("html") then
              local t2 = parse_tag(e.text)
              if t2 and t2.name == tag.name then
                depth = depth + (t2.close and -1 or 1)
                if depth == 0 then break end
              end
            end
            j = j + 1
          end
          if j <= #inls then
            local inner = convert_inlines(pandoc.Inlines({ table.unpack(inls, i + 1, j - 1) }))
            if tag.name == "a" then
              out:insert(pandoc.Link(inner, tag.attrs.href or "", tag.attrs.title or ""))
            else
              out:insert(WRAP[tag.name](inner))
            end
            i = j + 1
          else
            note_removed(tag.name); i = i + 1
          end
        else
          if not TRANSPARENT[tag.name] and not tag.close then note_removed(tag.name) end
          i = i + 1
        end
      end
    else
      out:insert(el); i = i + 1
    end
  end
  return out
end

-- one list of blocks; applied to every list in the document (top level, quotes, list items, divs)
local function convert_blocks(blocks)
  local out = pandoc.Blocks{}
  local stack = {}
  local changed = false
  local function current() return #stack > 0 and stack[#stack].content or out end
  for _, b in ipairs(blocks) do
    if b.t == "RawBlock" and b.format:match("html") then
      changed = true
      local text = b.text
      local cls = text:match('^%s*<div%s+class%s*=%s*"([^"]*)"%s*>%s*$')
      if cls then
        table.insert(stack, { classes = cls, content = pandoc.Blocks{} })
      elseif text:match("^%s*</div>%s*$") and #stack > 0 then
        local top = table.remove(stack)
        local classes = {}
        for c in top.classes:gmatch("%S+") do table.insert(classes, c) end
        current():insert(pandoc.Div(top.content, pandoc.Attr("", classes)))
      elseif text:match("^%s*<!%-%-.-%-%->%s*$") then
        -- comment: drop
      else
        local id = text:match('^%s*<a%s[^>]-id%s*=%s*"([^"]+)"[^>]*>%s*</a>%s*$')
                   or text:match('^%s*<a%s[^>]-name%s*=%s*"([^"]+)"[^>]*>%s*</a>%s*$')
        if id then
          current():insert(pandoc.Plain{ pandoc.Span({}, pandoc.Attr(id)) })
        else
          -- any other HTML block: let pandoc's HTML reader turn it into document structure
          report.html_blocks = report.html_blocks + 1
          local ok, doc = pcall(pandoc.read, text, "html")
          if ok then
            for tag in text:gmatch("<%s*([%a][%w%-]*)") do
              local t = tag:lower()
              if not (TRANSPARENT[t] or WRAP[t] or VOID[t] or STRUCTURAL[t]) then note_removed(t) end
            end
            -- <img alt> semantics, as for inline <img>
            local has_alt = text:match("<[Ii][Mm][Gg][^>]-%s[Aa][Ll][Tt]%s*=") ~= nil
            doc = doc:walk{ Image = function(im)
              if not has_alt then
                im.attributes["data-mdbindery-alt"] = "missing"
              elseif utils.stringify(im.caption) == "" then
                im.attributes["data-mdbindery-alt"] = "decorative"
              end
              return im
            end }
            current():extend(doc.blocks)
          else
            note_removed("unparsed-block")
          end
        end
      end
    else
      current():insert(b)
    end
  end
  if not changed then return nil end
  while #stack > 0 do
    local top = table.remove(stack)
    current():extend(top.content)
  end
  return out
end

-- ------------------------------------------------------------------ images
local function only_image(para)
  local img = nil
  for _, el in ipairs(para.content) do
    if el.t == "Image" then
      if img then return nil end
      img = el
    elseif el.t ~= "Space" and el.t ~= "SoftBreak" and el.t ~= "LineBreak" then
      return nil
    end
  end
  return img
end

-- https://github.com/OWNER/REPO/blob|raw/BRANCH/path and raw.githubusercontent.com/OWNER/REPO/BRANCH/path
local function same_repo_path(url)
  if not ctx.github or ctx.github == "" then return nil end
  local u = url:gsub("[?#].*$", "")
  local owner_repo, rest = u:match("^https?://github%.com/([^/]+/[^/]+)/blob/[^/]+/(.+)$")
  if not owner_repo then owner_repo, rest = u:match("^https?://github%.com/([^/]+/[^/]+)/raw/[^/]+/(.+)$") end
  if not owner_repo then
    owner_repo, rest = u:match("^https?://raw%.githubusercontent%.com/([^/]+/[^/]+)/[^/]+/(.+)$")
  end
  if owner_repo and owner_repo:lower() == ctx.github:lower() then return url_decode(rest) end
  return nil
end

local function resolve_image(img, kind)
  local src = img.src
  local alt_mark = img.attributes["data-mdbindery-alt"]
  img.attributes["data-mdbindery-alt"] = nil
  local has_alt = alt_mark == "decorative" or (alt_mark == nil and utils.stringify(img.caption) ~= "")
  local entry = { src = src, kind = kind, alt = has_alt }
  local abs
  if src == "" then
    entry.status = "empty"
  elseif is_url(src) and not src:match("^[Ff][Ii][Ll][Ee]:") then
    local rel = same_repo_path(src)
    if rel then
      abs = normalize(ctx.repo_root .. "/" .. rel)
      entry.local_copy = rel
    else
      entry.status = "remote"
    end
  else
    -- file:///abs/path is a path on this machine; file:rel and file://rel are relative
    local rel, machine = src, false
    if rel:match("^[Ff][Ii][Ll][Ee]:") then
      rel = rel:sub(6)
      if rel:match("^///") then
        rel, machine = rel:sub(3), true
      elseif rel:match("^//") then
        rel = rel:sub(3)
      end
      rel = rel:gsub("^/(%a:)", "%1")
    end
    rel = url_decode((rel:gsub("[?#].*$", "")))
    if ctx.work_dir and under(rel, ctx.work_dir) then
      abs = rel                                            -- a rendered chart
    elseif machine or rel:match("^%a:[/\\]") or rel:match("^[/\\][/\\]") then
      abs = normalize(rel)                                 -- absolute path on this machine
    elseif rel:match("^/") then
      abs = normalize(ctx.repo_root .. rel)                -- GitHub: "/" is the repository root
    else
      abs = normalize(ctx.file_dir .. "/" .. rel)
    end
  end
  if abs then
    if ctx.image_root and ctx.image_root ~= "" and not under(abs, ctx.image_root)
       and not (ctx.work_dir and under(abs, ctx.work_dir)) then
      entry.status = "outside"
    elseif is_file(abs) then
      img.src = abs
      entry.status = "ok"
      entry.path = abs
    else
      entry.status = entry.local_copy and "remote" or "missing"
    end
  end
  table.insert(report.images, entry)
  return img, entry.status == "ok"
end

-- text shown where an image cannot be used (the images gate fails the build)
local function image_placeholder(img)
  local alt = utils.stringify(img.caption)
  return pandoc.Span(pandoc.Inlines("[image: " .. (alt ~= "" and alt or img.src) .. "]"),
                     pandoc.Attr("", { "missing-image" }))
end

local function figures(blocks)
  local function handle(p)
      local img = only_image(p)
      if not img then return nil end
      if img.title == "" then  -- image alone in a paragraph: block figure without caption
        local ok
        img, ok = resolve_image(img, "block")
        if not ok then return pandoc.Para{ image_placeholder(img) } end
        img.attributes["data-mdbindery"] = "done"
        return pandoc.Figure({ pandoc.Plain{ img } }, {})
      end
      local title = img.title
      local full = pandoc.text.lower(title):match("^full%-?page") ~= nil
      local caption = full and title:gsub("^%a+%-?%a+%s*[:%-]?%s*", "", 1) or title
      img.title = ""
      local ok
      img, ok = resolve_image(img, full and "full-page" or "figure")
      if not ok then return pandoc.Para{ image_placeholder(img) } end
      img.attributes["data-mdbindery"] = "done"
      local cap = caption ~= "" and { pandoc.Plain(pandoc.Inlines(caption)) } or {}
      local fig = pandoc.Figure({ pandoc.Plain{ img } }, cap)
      if full then
        return pandoc.Div({ fig }, pandoc.Attr("", { "full-page" }))
      end
      return fig
  end
  -- HTML <figure> blocks come from pandoc's HTML reader as Figures already: their images are figures too
  blocks = blocks:walk{ Figure = function(f)
    return f:walk{ Image = function(img)
      if img.attributes["data-mdbindery"] then return nil end
      local ok
      img, ok = resolve_image(img, "figure")
      if not ok then return image_placeholder(img) end
      img.attributes["data-mdbindery"] = "done"
      return img
    end }
  end }
  blocks = blocks:walk{ Para = handle }
  -- an image alone in a plain block counts only at the top level or directly inside a wrapper Div
  -- (HTML <img> lines); in table cells and tight lists it stays inline
  local function top(list)
    local out = pandoc.Blocks{}
    for _, b in ipairs(list) do
      if b.t == "Plain" then
        out:insert(handle(b) or b)
      elseif b.t == "Div" and not b.classes:includes("card") then
        b.content = top(b.content)
        out:insert(b)
      else
        out:insert(b)
      end
    end
    return out
  end
  return top(blocks)
end

-- ------------------------------------------------------------------ tables
local function first_cell_ids(inlines)
  local ids = {}
  local cleaned = inlines:walk{
    Span = function(s)
      if s.identifier ~= "" and #s.content == 0 then
        table.insert(ids, s.identifier)
        return {}
      end
    end
  }
  return ids, cleaned
end

local function table_to_cards(tbl)
  local headers = {}
  if tbl.head and tbl.head.rows[1] then
    for j, cell in ipairs(tbl.head.rows[1].cells) do
      headers[j] = utils.blocks_to_inlines(cell.contents)
    end
  end
  local title_cols = math.max(1, tonumber(ctx.card_title_columns or 1))
  local cards = pandoc.Blocks{}
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.body) do
      local ids, cleaned = first_cell_ids(utils.blocks_to_inlines(row.cells[1].contents))
      for j = 2, math.min(title_cols, #row.cells) do
        local more = utils.blocks_to_inlines(row.cells[j].contents)
        if #more > 0 then cleaned:insert(pandoc.Str(":")); cleaned:insert(pandoc.Space()); cleaned:extend(more) end
      end
      -- one field per line: "Label: value"; values with several blocks (lists) keep their structure
      local blocks = pandoc.Blocks{ pandoc.Para{ pandoc.Strong(cleaned) } }
      for j = title_cols + 1, #row.cells do
        local value = row.cells[j].contents
        if #value > 0 and utils.stringify(value) ~= "" then
          local label = pandoc.Inlines(headers[j] or pandoc.Inlines{ pandoc.Str("Column " .. j) })
          local head = pandoc.Strong(label .. pandoc.Inlines{ pandoc.Str(":") })
          if #value == 1 and (value[1].t == "Plain" or value[1].t == "Para") then
            blocks:insert(pandoc.Para(pandoc.Inlines{ head, pandoc.Space() } .. value[1].content))
          else
            blocks:insert(pandoc.Para{ head })
            blocks:extend(value)
          end
        end
      end
      for k = #ids, 2, -1 do  -- extra anchors of the row stay reachable
        blocks[1].content:insert(1, pandoc.Span({}, pandoc.Attr(ids[k])))
      end
      cards:insert(pandoc.Div(blocks, pandoc.Attr(ids[1] or "", { "card" })))
    end
  end
  local out = pandoc.Blocks{}
  if tbl.caption and tbl.caption.long and #tbl.caption.long > 0 then out:extend(tbl.caption.long) end
  out:insert(pandoc.Div(cards, pandoc.Attr("", { "cards" })))
  return out
end

-- ---------------------------------------------------------------- headings
local function slug(inlines)
  return (pandoc.text.lower(utils.stringify(inlines)):gsub("[%s%p]+", "-"):gsub("^-+", ""):gsub("-+$", ""))
end

-- a block with no visible content: anchors, empty paragraphs
local function invisible(b)
  if b.t == "Plain" or b.t == "Para" then
    for _, el in ipairs(b.content) do
      if not ((el.t == "Span" and #el.content == 0) or el.t == "Space" or el.t == "SoftBreak"
              or el.t == "LineBreak") then
        return false
      end
    end
    return true
  end
  return false
end

local function unique_id(doc, id)
  local used = {}
  doc:walk{
    Header = function(h) used[h.identifier] = true end,
    Span = function(s) used[s.identifier] = true end,
    Div = function(d) used[d.identifier] = true end,
  }
  if id == "" then id = "section" end
  if not used[id] then return id end
  local n = 1
  while used[id .. "-" .. n] do n = n + 1 end
  return id .. "-" .. n
end

-- every chapter needs exactly one leading level-1 heading, or pandoc merges it into the previous chapter
local function fix_title(doc)
  local h1_index = nil
  for i, b in ipairs(doc.blocks) do
    if b.t == "Header" and b.level == 1 then h1_index = i; break end
  end
  local has_title = ctx.title and ctx.title ~= ""
  if not h1_index then
    local first = nil
    for i, b in ipairs(doc.blocks) do
      if b.t == "Header" then first = i; break end
    end
    local clear = first ~= nil
    for i = 1, (first or 1) - 1 do
      if not invisible(doc.blocks[i]) then clear = false end
    end
    if has_title then
      local inl = pandoc.Inlines(ctx.title)
      doc.blocks:insert(1, pandoc.Header(1, inl, pandoc.Attr(unique_id(doc, slug(inl)))))
      report.h1_fix = "title"
    elseif clear then
      -- promote the opening heading and shift the file's other headings with it (### -> ##); they stay
      -- below the title (a closing "## Summary" is not a new chapter); anchors above it move below it
      local shift = doc.blocks[first].level - 1
      doc = doc:walk{ Header = function(hd) hd.level = math.max(2, hd.level - shift); return hd end }
      local h = doc.blocks[first]
      h.level = 1
      local rest = pandoc.Blocks{ h }
      for i = 1, first - 1 do rest:insert(doc.blocks[i]) end
      for i = first + 1, #doc.blocks do rest:insert(doc.blocks[i]) end
      doc.blocks = rest
      report.h1_fix = "promoted"
    else
      local name = ctx.fallback_title or ""
      if name == "" then
        name = ctx.file:gsub("^.*/", ""):gsub("%.[Mm][Dd]$", ""):gsub("^[%d%s._-]+", ""):gsub("[-_]+", " ")
        if name == "" then name = ctx.file end
        name = name:sub(1, 1):upper() .. name:sub(2)
      end
      local inl = pandoc.Inlines(name)
      doc.blocks:insert(1, pandoc.Header(1, inl, pandoc.Attr(unique_id(doc, slug(inl)))))
      report.h1_fix = "filename"
    end
    h1_index = 1
  elseif h1_index > 1 then
    -- content before the title (badges, logos, stray text) moves below it
    local before = pandoc.Blocks{}
    local visible = 0
    for i = 1, h1_index - 1 do
      before:insert(doc.blocks[i])
      if not invisible(doc.blocks[i]) then visible = visible + 1 end
    end
    local rest = pandoc.Blocks{ doc.blocks[h1_index] }
    rest:extend(before)
    for i = h1_index + 1, #doc.blocks do rest:insert(doc.blocks[i]) end
    doc.blocks = rest
    report.moved_before_h1 = visible
    h1_index = 1
  end
  if has_title and report.h1_fix ~= "title" then
    -- the identifier stays, so old links keep working; anchors inside the old heading stay too
    local anchors = pandoc.Inlines{}
    doc.blocks[h1_index].content:walk{ Span = function(sp)
      if sp.identifier ~= "" and #sp.content == 0 then anchors:insert(sp) end
    end }
    doc.blocks[h1_index].content = pandoc.Inlines(ctx.title) .. anchors
  end
  return doc
end

-- anchors inside a heading move to just below it (navigation entries must be text only)
local function heading_anchors(blocks)
  local out = pandoc.Blocks{}
  local changed = false
  for _, b in ipairs(blocks) do
    if b.t == "Header" then
      local ids = {}
      b.content = b.content:walk{
        Span = function(s)
          if s.identifier ~= "" and #s.content == 0 then table.insert(ids, s.identifier); return {} end
        end
      }
      while #b.content > 0 and (b.content[#b.content].t == "Space" or b.content[#b.content].t == "SoftBreak") do
        b.content:remove(#b.content)
      end
      out:insert(b)
      if #ids > 0 then
        changed = true
        local spans = pandoc.Inlines{}
        for _, id in ipairs(ids) do spans:insert(pandoc.Span({}, pandoc.Attr(id))) end
        out:insert(pandoc.Plain(spans))
      end
    else
      out:insert(b)
    end
  end
  if changed then return out end
end

-- --------------------------------------------------------------- citations
local function label_key(s) return (pandoc.text.lower(s):gsub("%s+", " "):gsub("^ ", ""):gsub(" $", "")) end

local citations = {}
for _, c in ipairs(ctx.citations or {}) do citations[label_key(c.label)] = c end

local function as_citation(l)
  if next(citations) == nil then return nil end
  local c = citations[label_key(utils.stringify(l.content))]
  if c and url_decode(l.target) == url_decode(c.url) then
    report.cited[c.label] = true
    return pandoc.Link({ pandoc.Str("[" .. c.label .. "]") }, "#" .. c.id, "", pandoc.Attr("", { "citation" }))
  end
  return nil
end

-- ---------------------------------------------------------------- links
-- a path relative to the book folder (may start with ../) as a URL: resolved against source_url,
-- the online copy of the book folder (a GitHub blob URL or the published website)
local function outside_url(target)
  local base = ctx.source_url
  if not base or base == "" then return nil end
  local host, path = base:match("^(%a[%w+.-]*://[^/]*)(/?.*)$")
  if not host then return nil end
  local dir = path:gsub("[^/]*$", "")
  if dir == "" then dir = "/" end
  if not base:match("^%a+://[^/]*github%.com/") then
    -- a published website serves chapter.md as chapter.html and a folder's README.md as index.html
    target = target:gsub("[Rr][Ee][Aa][Dd][Mm][Ee]%.[Mm][Dd]$", "index.html"):gsub("%.[Mm][Dd]$", ".html")
  end
  return host .. normalize(dir .. url_encode_path(target))
end

-- characters EPUBCheck rejects in a URL (an autolinked "https://x/a[1]" has them)
local function clean_url(t)
  if t:match("^%a[%w+.-]*://%[") then return t end  -- IPv6 host
  return (t:gsub('[%[%]"<>\\^`{|} ]', function(ch) return string.format("%%%02X", ch:byte()) end))
end

local function rewrite_link(l, key, files)
  local c = as_citation(l)
  if c then l = c end
  local t = l.target
  if is_url(t) then
    l.target = clean_url(t)
    return l
  end
  local path, frag = t:match("^([^#]*)#?(.*)$")
  path = url_decode(path):gsub("\\", "/"):gsub("%?.*$", "")
  frag = url_decode(frag or "")
  local tkey
  if path == "" then
    tkey = key
  else
    local target
    if path:sub(1, 1) == "/" then
      -- GitHub: "/" is the repository root; the result is relative to the book folder
      local from_root = normalize(path:sub(2))
      local sp = ctx.source_prefix or ""
      if sp == "" then
        target = from_root
      elseif from_root:sub(1, #sp + 1) == sp .. "/" then
        target = from_root:sub(#sp + 2)
      else
        target = normalize(join(ctx.root_prefix, from_root))
      end
    else
      target = normalize(join(ctx.file_rel_dir, path))
    end
    tkey = files[target]
    if not tkey and target:match("%.[Hh][Tt][Mm][Ll]?$") then
      -- mdBook and web-style links: chapter.html for chapter.md
      local md = target:gsub("%.[Hh][Tt][Mm][Ll]?$", ".md")
      if files[md] then
        tkey = files[md]
        report.html_links = report.html_links + 1
      end
    end
    if not tkey and (target:match("index%.[Hh][Tt][Mm][Ll]?$") or path:sub(-1) == "/") then
      -- a folder's index page (mdBook builds README.md as index.html)
      local dir = target:gsub("/?index%.[Hh][Tt][Mm][Ll]?$", "")
      for _, name in ipairs({ "README.md", "readme.md", "index.md" }) do
        if files[join(dir, name)] then
          tkey = files[join(dir, name)]
          report.html_links = report.html_links + 1
          break
        end
      end
    end
    if not tkey then
      local found = exists(ctx.source_root .. "/" .. target)
      local url = outside_url(target)
      if url then
        l.target = url .. (frag ~= "" and ("#" .. frag) or "")
        table.insert(report.external, { path = target, mode = "source_url", exists = found })
        return l
      end
      -- no online copy to point to: keep the text, drop the link (a dead link fails EPUBCheck)
      table.insert(report.external, { path = target, mode = "unlinked", exists = found })
      return pandoc.Span(l.content)
    end
  end
  l.target = "mdbindery://" .. tkey .. "/" .. frag .. "\31from=" .. key
  return l
end

-- -------------------------------------------------------------- file phase
local function file_phase(doc)
  local key = ctx.key
  doc = doc:walk{ Blocks = convert_blocks }
  doc = doc:walk{ Inlines = convert_inlines }
  doc.blocks = figures(doc.blocks)
  doc = doc:walk{
    Image = function(img)
      if img.attributes["data-mdbindery"] then
        img.attributes["data-mdbindery"] = nil
        return img
      end
      img.classes:insert("inline")
      local ok
      img, ok = resolve_image(img, "inline")
      if not ok then return image_placeholder(img) end
      return img
    end,
    Math = function(m)
      if m.mathtype == "InlineMath" then table.insert(report.math, m.text:sub(1, 120)) end
    end,
  }

  doc = fix_title(doc)
  doc = doc:walk{ Blocks = heading_anchors }

  local min_cols = tonumber(ctx.card_min_columns or 9)
  local warn_cols = tonumber(ctx.wide_table_warn or 9)
  doc = doc:walk{
    Table = function(t)
      local n = #t.colspecs
      if ctx.cards and n >= min_cols then return table_to_cards(t) end
      if n >= warn_cols then table.insert(report.wide_tables, n) end
    end
  }

  local function prefix(id) return (id ~= "" and (key .. "-" .. id) or id) end
  local seen_h1 = false
  local function add(id) table.insert(report.ids, id) end
  doc = doc:walk{
    Header = function(h)
      if h.identifier == "" then h.identifier = slug(h.content) end
      h.identifier = prefix(h.identifier)
      if h.level == 1 and not seen_h1 then report.h1 = h.identifier; seen_h1 = true end
      add(h.identifier)
      return h
    end,
    Span = function(s) if s.identifier ~= "" then s.identifier = prefix(s.identifier); add(s.identifier); return s end end,
    Div = function(d) if d.identifier ~= "" then d.identifier = prefix(d.identifier); add(d.identifier); return d end end,
    CodeBlock = function(c) if c.identifier ~= "" then c.identifier = prefix(c.identifier); return c end end,
    Table = function(t) if t.identifier ~= "" then t.identifier = prefix(t.identifier); return t end end,
    Figure = function(f) if f.identifier ~= "" then f.identifier = prefix(f.identifier); add(f.identifier); return f end end,
    Image = function(im) if im.identifier ~= "" then im.identifier = prefix(im.identifier); return im end end,
  }
  if not report.h1 then
    doc.blocks:insert(1, pandoc.Plain{ pandoc.Span({}, pandoc.Attr(key)) })
    report.h1 = key
    add(key)
  end

  local files = ctx.files or {}
  doc = doc:walk{ Link = function(l) return rewrite_link(l, key, files) end }

  local removed = {}
  for k, v in pairs(report.html_removed) do table.insert(removed, { tag = k, count = v }) end
  report.html_removed = removed
  local cited = {}
  for k in pairs(report.cited) do table.insert(cited, k) end
  report.cited = cited
  write_report(report)
  return doc
end

-- ------------------------------------------------------------- links phase
-- compare anchors ignoring ASCII punctuation and spaces; letters of every script are kept
local function squash(s) return (pandoc.text.lower(s):gsub("[%p%s]", "")) end

local function links_phase(doc)
  local ids, by_key = {}, {}
  local function add(id)
    if id and id ~= "" then
      ids[id] = true
      local k = id:match("^([^-]+)%-")
      if k then by_key[k] = by_key[k] or {}; table.insert(by_key[k], id) end
    end
  end
  doc:walk{
    Header = function(h) add(h.identifier) end,
    Span = function(s) add(s.identifier) end,
    Div = function(d) add(d.identifier) end,
    Table = function(t) add(t.identifier) end,
    Figure = function(f) add(f.identifier) end,
  }
  for _, h in pairs(ctx.h1 or {}) do ids[h] = true end

  local unresolved, fuzzy = {}, {}
  doc = doc:walk{
    Link = function(l)
      local key, frag, from = l.target:match("^mdbindery://([^/]+)/(.-)\31from=(.*)$")
      if not key then return nil end
      local h1 = (ctx.h1 or {})[key]
      if frag == "" then l.target = "#" .. (h1 or key); return l end
      local want = key .. "-" .. frag
      if ids[want] then l.target = "#" .. want; return l end
      local lower = key .. "-" .. pandoc.text.lower(frag)
      if ids[lower] then l.target = "#" .. lower; return l end   -- GitHub matches anchors case-insensitively
      local sq, hit, hits = squash(want), nil, 0
      for _, id in ipairs(by_key[key] or {}) do
        if squash(id) == sq then hit = id; hits = hits + 1 end
      end
      if hits == 1 then
        table.insert(fuzzy, { from = want, to = hit, key = key, fragment = frag, source = from })
        l.target = "#" .. hit
      else
        table.insert(unresolved, { key = key, fragment = frag, text = utils.stringify(l.content), source = from })
        l.target = "#" .. (h1 or key)
      end
      return l
    end
  }
  write_report({ unresolved = unresolved, fuzzy = fuzzy })
  return doc
end

function Pandoc(doc)
  if phase == "file" then return file_phase(doc) end
  if phase == "links" then return links_phase(doc) end
  error("MDBINDERY_PHASE must be 'file' or 'links'")
end
