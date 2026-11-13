// Build DOM nodes instead of injecting model output as HTML.
function inline(parent, text) {
  const tokens = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))/g;
  let position = 0;
  for (const match of text.matchAll(tokens)) {
    parent.append(document.createTextNode(text.slice(position, match.index)));
    const token = match[0];
    let element;
    if (token.startsWith("`")) {
      element = document.createElement("code");
      element.textContent = token.slice(1, -1);
    } else if (token.startsWith("**")) {
      element = document.createElement("strong");
      element.textContent = token.slice(2, -2);
    } else {
      const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      element = document.createElement("a");
      element.textContent = link[1];
      element.href = link[2];
      element.target = "_blank";
      element.rel = "noopener noreferrer";
    }
    parent.append(element);
    position = match.index + token.length;
  }
  parent.append(document.createTextNode(text.slice(position)));
}

function cells(line) { return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(cell => cell.trim()); }
function separator(line) { return line && cells(line).every(cell => /^:?-{3,}:?$/.test(cell)); }
function startsBlock(lines, i) { return /^(#{1,3}\s|```|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i]) || (lines[i].includes("|") && separator(lines[i + 1])); }

export function renderMarkdown(text) {
  const fragment = document.createDocumentFragment();
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    if (!lines[i].trim() || /^\s*---+\s*$/.test(lines[i])) { i++; continue; }
    if (lines[i].startsWith("```")) {
      const code = document.createElement("code");
      const pre = document.createElement("pre");
      const content = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) content.push(lines[i++]);
      code.textContent = content.join("\n");
      pre.append(code);
      fragment.append(pre);
      if (i < lines.length) i++;
      continue;
    }
    if (lines[i].includes("|") && separator(lines[i + 1])) {
      const wrapper = document.createElement("div");
      wrapper.className = "table-scroll";
      const table = document.createElement("table");
      const head = document.createElement("thead");
      const header = document.createElement("tr");
      for (const value of cells(lines[i])) { const th = document.createElement("th"); th.scope = "col"; inline(th, value); header.append(th); }
      head.append(header);
      table.append(head);
      const body = document.createElement("tbody");
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        const row = document.createElement("tr");
        for (const value of cells(lines[i++])) { const td = document.createElement("td"); inline(td, value); row.append(td); }
        body.append(row);
      }
      table.append(body);
      wrapper.append(table);
      fragment.append(wrapper);
      continue;
    }
    const heading = lines[i].match(/^(#{1,3})\s+(.+)$/);
    if (heading) { const h = document.createElement(`h${heading[1].length + 1}`); inline(h, heading[2]); fragment.append(h); i++; continue; }
    const list = lines[i].match(/^\s*([-*]|\d+\.)\s+(.+)$/);
    if (list) {
      const ordered = /\d/.test(list[1]);
      const element = document.createElement(ordered ? "ol" : "ul");
      const pattern = ordered ? /^\s*\d+\.\s+(.+)$/ : /^\s*[-*]\s+(.+)$/;
      let item;
      while (i < lines.length && (item = lines[i].match(pattern))) { const li = document.createElement("li"); inline(li, item[1]); element.append(li); i++; }
      fragment.append(element);
      continue;
    }
    const paragraph = document.createElement("p");
    const content = [lines[i++]];
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) content.push(lines[i++]);
    inline(paragraph, content.join("\n"));
    fragment.append(paragraph);
  }
  return fragment;
}
