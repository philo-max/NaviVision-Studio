/**
 * NaviVision Studio - 脚本编辑器语法高亮
 * 把源码转换为带 token 类名的 HTML (HDevelop 4GL 与 Python 两种语言)，
 * 由 code_editor.js 渲染在透明文本框下方的高亮层里。
 */

const SyntaxHighlighter = (() => {
  const HDEV_KEYWORDS = new Set([
    'if', 'elseif', 'else', 'endif', 'for', 'endfor', 'while', 'endwhile', 'repeat', 'until',
    'break', 'continue', 'return', 'stop', 'exit', 'to', 'by', 'and', 'or', 'not', 'xor',
  ]);
  const HDEV_CONSTANTS = new Set(['true', 'false']);
  const PYTHON_KEYWORDS = new Set([
    'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
    'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not',
    'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
  ]);
  const PYTHON_CONSTANTS = new Set(['True', 'False', 'None']);

  const NUMBER = String.raw`\d+(?:\.\d+)?(?:[eE][+-]?\d+)?`;
  const WORD = String.raw`[A-Za-z_][A-Za-z0-9_]*`;
  const HDEV_TOKENS = new RegExp(
    String.raw`(?<string>'(?:[^'\\]|\\.)*'?|"(?:[^"\\]|\\.)*"?)|(?<number>\b${NUMBER}\b)|` +
    String.raw`(?<assign>:=)|(?<word>${WORD})(?:(?=\s*\((?<call>))|)`, 'g');
  const PYTHON_TOKENS = new RegExp(
    String.raw`(?<string>"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?)|` +
    String.raw`(?<comment>#[^\n]*)|(?<number>\b${NUMBER}\b)|(?<word>${WORD})(?:(?=\s*\((?<call>))|)`, 'g');

  const escapeHtml = (text) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const wrap = (cls, text) => `<span class="tok-${cls}">${escapeHtml(text)}</span>`;

  function classify(groups, keywords, constants) {
    if (groups.string !== undefined) return 'string';
    if (groups.comment !== undefined) return 'comment';
    if (groups.number !== undefined) return 'number';
    if (groups.assign !== undefined) return 'operator';
    if (groups.word === undefined) return null;
    if (keywords.has(groups.word)) return 'keyword';
    if (constants.has(groups.word)) return 'constant';
    return groups.call !== undefined ? 'function' : null;
  }

  function highlightWith(text, pattern, keywords, constants) {
    pattern.lastIndex = 0;
    let out = '';
    let last = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      if (match[0] === '') {
        pattern.lastIndex++;
        continue;
      }
      out += escapeHtml(text.slice(last, match.index));
      const cls = classify(match.groups, keywords, constants);
      out += cls ? wrap(cls, match[0]) : escapeHtml(match[0]);
      last = match.index + match[0].length;
    }
    return out + escapeHtml(text.slice(last));
  }

  function highlightHDev(text) {
    return text.split('\n').map((line) => {
      const trimmed = line.trimStart();
      if (trimmed.startsWith('*') || trimmed.startsWith('//')) return wrap('comment', line);
      return highlightWith(line, HDEV_TOKENS, HDEV_KEYWORDS, HDEV_CONSTANTS);
    }).join('\n');
  }

  function highlightPython(text) {
    return highlightWith(text, PYTHON_TOKENS, PYTHON_KEYWORDS, PYTHON_CONSTANTS);
  }

  /** 返回带 token 类名的 HTML；末尾补一个换行，使高亮层与文本框的末行高度一致 */
  function highlight(text, lang) {
    const html = lang === 'python' ? highlightPython(text) : highlightHDev(text);
    return html + '\n';
  }

  return { highlight };
})();

window.SyntaxHighlighter = SyntaxHighlighter;
