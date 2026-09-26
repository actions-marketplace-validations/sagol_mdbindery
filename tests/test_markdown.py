from mdbindery.markdown import (code_span_ranges, drop_sections, expand_includes, headings, hide_rust_lines,
                                iter_text_lines, label_ids, mermaid_alt, mermaid_source, parse_definitions,
                                prepass, split_blocks, title_markdown)

OPTS = {'citations': 'refdefs', 'reference_headings': ['References'], 'reference_heading_new': 'References',
        'mermaid': 'png', 'mermaid_alt_prefix': 'Chart'}


def test_definitions_become_visible_list():
    src = ('# T\n\nClaim [1] and [2].\n\n## References\n\n'
           '[1]: https://a.example/x "Author, Title, 2020"\n[2]: https://b.example/y\n')
    out, stats = prepass(src, {}, OPTS)
    assert 'Claim [1] and [2].' in out  # the text is untouched: the filter links citations on the AST
    assert '<a id="ref-1"></a>\\[1\\] Author, Title, 2020. <https://a.example/x>' in out
    assert '<a id="ref-2"></a>\\[2\\] <https://b.example/y>' in out
    assert stats['references'] == 2
    assert stats['citations'] == [{'label': '1', 'url': 'https://a.example/x', 'id': 'ref-1'},
                                  {'label': '2', 'url': 'https://b.example/y', 'id': 'ref-2'}]


def test_code_and_blank_lines_are_never_rewritten():
    src = ('# T\n\n```python\ndef a():\n    pass\n\n\ndef b():\n    x = arr[1]\n```\n\n'
           '    indented[1] = 0\n\nReal [1].\n\n[1]: https://x.example\n')
    out, _ = prepass(src, {}, OPTS)
    assert 'def a():\n    pass\n\n\ndef b():\n    x = arr[1]' in out  # PEP 8 spacing kept
    assert '    indented[1] = 0' in out and 'Real [1].' in out


def test_named_labels_are_citations_only_when_configured():
    src = '# T\n\n[gfm] and [1]\n\n[gfm]: https://github.github.com/gfm/ "GFM"\n[1]: https://x.example\n'
    _, stats = prepass(src, {}, OPTS)
    assert [c['label'] for c in stats['citations']] == ['1']
    _, stats = prepass(src, {}, dict(OPTS, citation_labels='all'))
    assert [c['label'] for c in stats['citations']] == ['1', 'gfm']


def test_references_heading_added_when_missing():
    out, _ = prepass('# T\n\nA [1].\n\n[1]: https://x.example\n', {}, OPTS)
    assert '## References' in out


def test_setext_references_heading_keeps_its_underline():
    out, _ = prepass('# T\n\nA [1].\n\nReferences\n----------\n\n[1]: https://x.example\n', {}, OPTS)
    assert 'References\n----------\n\n<div class="references">' in out


def test_commented_definitions_are_ignored():
    src = '# T\n\nA [1].\n\n<!--\n[2]: https://old.example "Old"\n-->\n\n[1]: https://x.example\n'
    _, stats = prepass(src, {}, OPTS)
    assert [c['label'] for c in stats['citations']] == ['1']


def test_urls_inside_titles_stay_clean():
    assert title_markdown('see https://web.archive.org/web/2020id_/x_y') == \
        'see <https://web.archive.org/web/2020id_/x_y>'


def test_drop_sections_and_lines():
    src = '# T\n\n## Keep\n\nA\n\n## Drop\n\nB\n\n### Sub\n\nC\n\n## After\n\n*Last reviewed: x*\n\nD\n'
    out, stats = prepass(src, {'drop_sections': ['Drop']}, dict(OPTS, drop_lines=[r'^\*Last reviewed']))
    assert 'B' not in out and 'C' not in out and 'D' in out and 'Last reviewed' not in out
    assert stats['dropped_sections'] == ['Drop'] and stats['dropped_lines'] == 1


def test_duplicate_definitions_detected():
    defs, dups = parse_definitions(['[1]: https://a', '[1]: https://b', '[2]: https://c'])
    assert dups == [('1', 1)] and set(defs) == {'1', '2'}


def test_headings_ignore_code_and_comments():
    hs = headings(['# A', '```', '# not a heading', '```', '<!--', '# old', '-->', '## B'])
    assert [(l, t) for _, l, t in hs] == [(1, 'A'), (2, 'B')]


def test_heading_text_keeps_a_trailing_hash():
    assert [t for _, _, t in headings(['# Learning C#', '', '## Notes ##', '', '#hashtag'])] == ['Learning C#', 'Notes']


def test_block_kinds():
    lines = ['Text', '', '    code', '', '- item', '', '    continuation', '', '<!-- note -->',
             '1. step', '', '    ```bash', '    <YOUR_NAME>', '    ```', '', '> ```', '> quoted', '> ```',
             '```inline``` code then text', 'after']
    kinds = [(k, s) for k, _, s, _ in split_blocks(lines)]
    assert ('icode', 2) in kinds                     # indented code after a paragraph
    assert ('comment', 8) in kinds
    assert ('code', 11) in kinds and ('code', 15) in kinds  # fences in lists and quotes
    text = {i for i, _ in iter_text_lines(lines)}
    assert 6 in text                                 # list continuation is text, not code
    assert 18 in text and 19 in text                 # ```inline``` is not a fence


def test_code_spans_scan_is_linear():
    assert code_span_ranges('a `b` ``c`d`` e') == [(2, 5), (6, 13)]
    assert code_span_ranges('`' * 5000) == []


def test_mermaid_today_marker_off_and_alt_text():
    block = ['```mermaid', 'gantt', '    title Plan', '    A :2030-01, 2030-06', '```']
    assert 'todayMarker off' in mermaid_source(block)
    assert mermaid_alt(block, 'Chart') == 'Chart: Plan'
    flow = ['```mermaid', 'flowchart LR', '  A[Idea] --> B[Draft]', '```']
    assert mermaid_alt(flow, 'Chart') == 'Chart: Idea, Draft'
    assert mermaid_source(['```mermaid', 'graph LR', '  A-->B']).strip().endswith('A-->B')  # unclosed fence


def test_label_ids_are_unique_and_keep_letters():
    ids = label_ids(['11', 'Milchin 2014', 'Иванов', 'Петров', 'C++', 'C#'])
    assert ids['11'] == 'ref-11' and ids['Milchin 2014'] == 'ref-milchin-2014'
    assert ids['Иванов'] == 'ref-иванов' and ids['Петров'] == 'ref-петров'
    assert len(set(ids.values())) == len(ids)


def test_drop_sections_keeps_other_levels():
    lines, dropped = drop_sections(['# A', '## X', 'x', '# B', 'b'], ['X'])
    assert lines == ['# A', '# B', 'b'] and dropped == ['X']


def test_mdbook_includes(tmp_path):
    (tmp_path / 'src').mkdir()
    (tmp_path / 'listings').mkdir()
    (tmp_path / 'listings' / 'main.rs').write_text(
        'use std::io;\n// ANCHOR: here\nfn main() {\n    println!("hi");\n}\n// ANCHOR_END: here\n')
    text = ('```rust\n{{#rustdoc_include ../listings/main.rs:here}}\n```\n\n{{#include ../listings/main.rs:1}}\n'
            '\\{{#include literal.rs}}\n{{#include ../../outside.rs}}\n{{#include missing.rs}}\n')
    out, n, errors = expand_includes(text, tmp_path / 'src', tmp_path)
    assert 'fn main() {\n    println!("hi");\n}' in out and 'ANCHOR' not in out
    assert 'use std::io;' in out and '{{#include literal.rs}}' in out
    assert n == 2 and [e for _, e in errors] == ['outside the repository', 'file not found']


def test_rust_hidden_lines():
    block = ['```rust', '# fn main() {', 'let x = 1;', '#[derive(Debug)]', '## not hidden', '# }', '```']
    assert hide_rust_lines(block) == ['```rust', 'let x = 1;', '#[derive(Debug)]', '# not hidden', '```']
