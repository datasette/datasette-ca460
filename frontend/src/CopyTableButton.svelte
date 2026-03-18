<script module lang="ts">
  type Format = 'csv' | 'json' | 'markdown';
  let sharedFormat: Format = $state(
    (localStorage.getItem('ca460_copy_format') as Format) || 'csv'
  );
</script>

<script lang="ts">
  interface Props {
    columns: string[];
    rows: Record<string, unknown>[];
    columnLabels?: Record<string, string>;
  }

  let { columns, rows, columnLabels = {} }: Props = $props();

  let menuOpen = $state(false);
  let copied = $state(false);

  function label(col: string): string {
    return columnLabels[col] || col.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  function valStr(v: unknown): string {
    if (v === null || v === undefined) return '';
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  }

  function toCsv(): string {
    const header = columns.map(c => `"${label(c).replace(/"/g, '""')}"`).join(',');
    const body = rows.map(row =>
      columns.map(c => {
        const v = valStr(row[c]);
        return v.includes(',') || v.includes('"') || v.includes('\n')
          ? `"${v.replace(/"/g, '""')}"`
          : v;
      }).join(',')
    ).join('\n');
    return header + '\n' + body;
  }

  function toJson(): string {
    return JSON.stringify(rows.map(row => {
      const obj: Record<string, unknown> = {};
      for (const c of columns) obj[c] = row[c] ?? null;
      return obj;
    }), null, 2);
  }

  function toMarkdown(): string {
    const headers = columns.map(c => label(c));
    const sep = columns.map(() => '---');
    const body = rows.map(row => columns.map(c => valStr(row[c]).replace(/\|/g, '\\|')));
    return [
      '| ' + headers.join(' | ') + ' |',
      '| ' + sep.join(' | ') + ' |',
      ...body.map(r => '| ' + r.join(' | ') + ' |')
    ].join('\n');
  }

  function serialize(fmt: Format): string {
    switch (fmt) {
      case 'csv': return toCsv();
      case 'json': return toJson();
      case 'markdown': return toMarkdown();
    }
  }

  async function copyAs(fmt: Format) {
    sharedFormat = fmt;
    localStorage.setItem('ca460_copy_format', fmt);
    menuOpen = false;
    await navigator.clipboard.writeText(serialize(fmt));
    copied = true;
    setTimeout(() => copied = false, 1500);
  }

  async function copyDefault() {
    await copyAs(sharedFormat);
  }

  function toggleMenu(e: Event) {
    e.stopPropagation();
    menuOpen = !menuOpen;
  }

  function closeMenu() {
    menuOpen = false;
  }

  const FORMAT_LABELS: Record<Format, string> = {
    csv: 'CSV',
    json: 'JSON',
    markdown: 'Markdown',
  };
</script>

<svelte:window onclick={closeMenu} />

<div class="copy-group">
  <button class="copy-btn" onclick={copyDefault}>
    {copied ? 'Copied!' : `Copy as ${FORMAT_LABELS[sharedFormat]}`}
  </button><button class="copy-menu-toggle" onclick={toggleMenu} aria-label="Copy format options">&#9662;</button>
  {#if menuOpen}
    <div class="copy-menu">
      {#each (['csv', 'json', 'markdown'] as Format[]) as fmt}
        <button class="copy-menu-item" class:active={fmt === sharedFormat} onclick={() => copyAs(fmt)}>
          {FORMAT_LABELS[fmt]}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .copy-group {
    position: relative;
    display: inline-flex;
    font-size: 0.8em;
  }
  .copy-btn {
    padding: 0.35em 0.7em;
    background: #f1f5f9;
    border: 1px solid #d1d5db;
    border-right: none;
    border-radius: 4px 0 0 4px;
    cursor: pointer;
    color: #475569;
    font-size: 1em;
    white-space: nowrap;
  }
  .copy-btn:hover { background: #e2e8f0; }
  .copy-menu-toggle {
    padding: 0.35em 0.5em;
    background: #f1f5f9;
    border: 1px solid #d1d5db;
    border-radius: 0 4px 4px 0;
    cursor: pointer;
    color: #475569;
    font-size: 1em;
    line-height: 1;
  }
  .copy-menu-toggle:hover { background: #e2e8f0; }
  .copy-menu {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 2px;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    z-index: 10;
    overflow: hidden;
  }
  .copy-menu-item {
    display: block;
    width: 100%;
    padding: 0.45em 1em;
    border: none;
    background: none;
    cursor: pointer;
    text-align: left;
    font-size: 1em;
    color: #334155;
    white-space: nowrap;
  }
  .copy-menu-item:hover { background: #f1f5f9; }
  .copy-menu-item.active { font-weight: 600; color: #0066cc; }
</style>
