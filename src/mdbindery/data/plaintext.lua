-- mdbindery word count: raw HTML becomes the text a reader sees (tags, comments, scripts removed,
-- alt text kept); everything else is left to pandoc's plain-text writer.
local function strip(s)
  s = s:gsub("<!%-%-.-%-%->", " ")
  s = s:gsub("<[Ss][Cc][Rr][Ii][Pp][Tt].-</[Ss][Cc][Rr][Ii][Pp][Tt]%s*>", " ")
  s = s:gsub("<[Ss][Tt][Yy][Ll][Ee].-</[Ss][Tt][Yy][Ll][Ee]%s*>", " ")
  s = s:gsub('<[Ii][Mm][Gg]%s[^>]-[Aa][Ll][Tt]%s*=%s*"([^"]*)"[^>]*>', " %1 ")
  s = s:gsub("<[^>]*>", " ")
  s = s:gsub("&#?%w+;", " ")
  return s
end

function RawInline(r)
  if r.format:match("html") then return pandoc.Str(strip(r.text)) end
end

function RawBlock(r)
  if r.format:match("html") then return pandoc.Plain{ pandoc.Str(strip(r.text)) } end
end
