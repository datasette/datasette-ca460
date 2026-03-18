<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import DevBadge from './DevBadge.svelte';
  import CopyTableButton from './CopyTableButton.svelte';
  import { documentParsed } from './api';
  import { getDatabaseFromUrl, getDocumentIdFromUrl, getPageNumberFromUrl } from './utils';

  const database = getDatabaseFromUrl();
  const documentId = getDocumentIdFromUrl();
  const pageNumber = getPageNumberFromUrl();

  interface ParsedPage {
    page_number: number;
    page_type: string;
    parsed_data: Record<string, unknown>;
    timing: Record<string, unknown>;
    created_at: string;
  }

  interface PageInfo {
    page_id: number;
    page_number: number;
    has_image: boolean;
    classification_model: string | null;
    page_type: string | null;
  }

  interface DocumentData {
    document: { id: number; source: string; page_count: number; title: string };
    pages: PageInfo[];
    models: Record<string, ParsedPage[]>;
  }

  let documentData: DocumentData | null = $state(null);
  let loading = $state(true);
  let selectedModel = $state('');

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'ArrowLeft' && pageNumber > 1) {
      window.location.href = pageUrl(pageNumber - 1);
    } else if (e.key === 'ArrowRight' && documentData && pageNumber < documentData.document.page_count) {
      window.location.href = pageUrl(pageNumber + 1);
    }
  }

  onMount(() => {
    loadDocument();
    window.addEventListener('keydown', handleKeydown);
  });

  onDestroy(() => {
    window.removeEventListener('keydown', handleKeydown);
  });

  async function loadDocument() {
    loading = true;
    try {
      const { data, error, response } = await documentParsed(database, documentId);
      if (error || !response.ok) { documentData = null; return; }
      const d = data as any;
      if (d.error) { documentData = null; return; }
      documentData = d;
      const modelNames = Object.keys(d.models);
      if (modelNames.length > 0) selectedModel = modelNames[0];
    } catch (e) { documentData = null; }
    finally { loading = false; }
  }

  function imageUrl(pn: number) {
    return `/${database}/-/ca460/api/document/${documentId}/page/${pn}/image`;
  }
  function pageUrl(pn: number) {
    return `/${database}/-/ca460/document/${documentId}/page/${pn}`;
  }
  function docUrl() {
    return `/${database}/-/ca460/document/${documentId}`;
  }

  function pageInfo(): PageInfo | null {
    return documentData?.pages.find(p => p.page_number === pageNumber) || null;
  }
  function parsed(): ParsedPage | null {
    return (documentData?.models[selectedModel] || []).find(p => p.page_number === pageNumber) || null;
  }
  function pageCount(): number {
    return documentData?.document.page_count || 0;
  }

  function pageTypeLabel(pt: string): string {
    return pt.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }
  function pageTypeColor(pt: string | null): string {
    const colors: Record<string, string> = {
      'cover-page-part-1': '#6366f1', 'cover-page-part-2': '#818cf8',
      'summary-page': '#059669',
      'schedule-a': '#d97706', 'schedule-b-part-1': '#b45309', 'schedule-b-part-2': '#92400e',
      'schedule-c': '#0891b2', 'schedule-d': '#7c3aed', 'schedule-e': '#db2777',
      'schedule-f': '#e11d48', 'schedule-g': '#84cc16', 'schedule-h': '#f59e0b',
      'schedule-i': '#14b8a6', 'unknown': '#9ca3af',
    };
    return pt ? colors[pt] || '#6b7280' : '#d1d5db';
  }
  function formatFieldName(name: string): string {
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }
  function formatValue(v: unknown): string {
    if (v === null || v === undefined) return '\u2014';
    if (typeof v === 'number') return v.toLocaleString('en-US', { minimumFractionDigits: v % 1 === 0 ? 0 : 2, maximumFractionDigits: 2 });
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  }
  function formatCurrency(v: unknown): string {
    if (v === null || v === undefined) return '\u2014';
    const n = Number(v);
    if (isNaN(n)) return String(v);
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function isCurrencyField(key: string): boolean {
    return /amount|balance|total|cash|contributions|expenditures|payments|loans|debt|line_\d/.test(key);
  }
  function colDisplayValue(key: string, v: unknown): string {
    return isCurrencyField(key) ? formatCurrency(v) : formatValue(v);
  }
  function colHeaderName(key: string): string {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }
  function getMetaFields(data: Record<string, unknown>): [string, unknown][] {
    return Object.entries(data).filter(([k]) => k !== 'line_items' && k !== 'subtotal');
  }
  function hasLineItems(page: ParsedPage): boolean {
    return Array.isArray(page.parsed_data?.line_items) && (page.parsed_data.line_items as unknown[]).length > 0;
  }
  function getLineItems(page: ParsedPage): Record<string, unknown>[] {
    return (page.parsed_data?.line_items as Record<string, unknown>[]) || [];
  }
  function lineItemColumns(items: Record<string, unknown>[]): string[] {
    const allKeys = new Set<string>();
    for (const item of items) for (const k of Object.keys(item)) allKeys.add(k);
    return Array.from(allKeys);
  }
</script>

<main>
  {#if loading}
    <div class="loading">Loading...</div>
  {:else if !documentData}
    <div class="empty">Document not found.</div>
  {:else}
    <nav class="breadcrumb">
      <a href="/{database}/-/ca460">Documents</a>
      <span class="sep">/</span>
      <a href={docUrl()}>{documentData.document.title}</a>
      <span class="sep">/</span>
      <span>Page {pageNumber}</span>
      <DevBadge />
    </nav>

    <div class="page-nav-bar">
      <div class="page-nav-left">
        {#if pageNumber > 1}
          <a href={pageUrl(pageNumber - 1)} class="btn-nav">&larr; Page {pageNumber - 1}</a>
        {/if}
      </div>

      <h1>Page {pageNumber} of {pageCount()}</h1>

      <div class="page-nav-right">
        {#if pageNumber < pageCount()}
          <a href={pageUrl(pageNumber + 1)} class="btn-nav">Page {pageNumber + 1} &rarr;</a>
        {/if}
      </div>
    </div>

    {#if Object.keys(documentData.models).length > 1}
      <div class="model-bar">
        <label for="model-select">Model:</label>
        <select id="model-select" bind:value={selectedModel}>
          {#each Object.keys(documentData.models) as model}
            <option value={model}>{model}</option>
          {/each}
        </select>
      </div>
    {/if}

    {@const info = pageInfo()}
    {@const parsedData = parsed()}

    <div class="side-by-side">
      <!-- Left: image -->
      <div class="image-panel">
        <img src={imageUrl(pageNumber)} alt="Page {pageNumber}" />
      </div>

      <!-- Right: parsed data -->
      <div class="data-panel">
        {#if info?.page_type}
          <div class="type-badge" style="background: {pageTypeColor(info.page_type)}">
            {pageTypeLabel(info.page_type)}
          </div>
        {:else}
          <div class="type-badge unclassified">Unclassified</div>
        {/if}

        {#if parsedData}
          {#if getMetaFields(parsedData.parsed_data || {}).length > 0}
            <div class="fields-card">
              {#each getMetaFields(parsedData.parsed_data || {}) as [key, value]}
                <div class="field-row">
                  <span class="field-label">{formatFieldName(key)}</span>
                  <span class="field-value" class:currency={isCurrencyField(key)}>{colDisplayValue(key, value)}</span>
                </div>
              {/each}
            </div>
          {/if}

          {#if hasLineItems(parsedData)}
            {@const items = getLineItems(parsedData)}
            {@const cols = lineItemColumns(items)}
            <div class="table-header">
              <h3>Line Items ({items.length})</h3>
              <CopyTableButton columns={cols} rows={items} />
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead>
                  <tr>
                    <th class="row-num">#</th>
                    {#each cols as col}
                      <th class:num-col={isCurrencyField(col)}>{colHeaderName(col)}</th>
                    {/each}
                  </tr>
                </thead>
                <tbody>
                  {#each items as item, idx}
                    <tr>
                      <td class="row-num">{idx + 1}</td>
                      {#each cols as col}
                        <td class:num-col={isCurrencyField(col)}>{colDisplayValue(col, item[col])}</td>
                      {/each}
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>

            {#if parsedData.parsed_data?.subtotal !== undefined}
              <div class="subtotal">Subtotal: {formatCurrency(parsedData.parsed_data.subtotal)}</div>
            {/if}
          {/if}
        {:else}
          <div class="empty">No parsed data for this page.</div>
        {/if}
      </div>
    </div>

    <!-- Page strip navigator -->
    <div class="page-strip">
      {#each documentData.pages as p}
        <a
          href={pageUrl(p.page_number)}
          class="strip-chip"
          class:strip-active={p.page_number === pageNumber}
          style="border-bottom-color: {pageTypeColor(p.page_type)}"
        >
          {p.page_number}
        </a>
      {/each}
    </div>
  {/if}
</main>

<style>
  main { max-width: 100%; }

  .loading, .empty { text-align: center; padding: 3em; color: #94a3b8; }

  .breadcrumb { display: flex; align-items: center; gap: 0.4em; font-size: 0.9em; color: #64748b; margin-bottom: 1.5em; }
  .breadcrumb a { color: #0066cc; text-decoration: none; }
  .breadcrumb a:hover { text-decoration: underline; }
  .breadcrumb .sep { color: #cbd5e1; }

  .page-nav-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5em; }
  .page-nav-bar h1 { font-size: 1.3em; margin: 0; }
  .page-nav-left, .page-nav-right { min-width: 120px; }
  .page-nav-right { text-align: right; }
  .btn-nav { display: inline-block; padding: 0.5em 1em; background: #f1f5f9; border: 1px solid #d1d5db; border-radius: 4px; color: #475569; text-decoration: none; font-size: 0.85em; }
  .btn-nav:hover { background: #e2e8f0; }

  .model-bar { display: flex; align-items: center; gap: 0.5em; margin-bottom: 1.5em; }
  .model-bar label { font-size: 0.85em; color: #64748b; }
  .model-bar select { padding: 0.3em 0.5em; font-size: 0.85em; border: 1px solid #d1d5db; border-radius: 4px; }

  .side-by-side { display: grid; grid-template-columns: minmax(300px, 1fr) minmax(400px, 1.2fr); gap: 2em; align-items: start; margin-bottom: 2em; }
  @media (max-width: 1000px) { .side-by-side { grid-template-columns: 1fr; } }

  .image-panel { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; background: #f8fafc; position: sticky; top: 1em; }
  .image-panel img { width: 100%; height: auto; display: block; }

  .data-panel { min-width: 0; }
  .type-badge { display: inline-block; padding: 0.35em 0.85em; border-radius: 5px; color: white; font-weight: 600; font-size: 0.9em; margin-bottom: 1.25em; }
  .type-badge.unclassified { background: #9ca3af; }

  .fields-card { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-bottom: 1.5em; }
  .field-row { display: flex; justify-content: space-between; padding: 0.6em 1em; border-bottom: 1px solid #f1f5f9; gap: 1em; }
  .field-row:last-child { border-bottom: none; }
  .field-row:nth-child(even) { background: #fafbfc; }
  .field-label { color: #64748b; font-size: 0.85em; flex-shrink: 0; }
  .field-value { font-size: 0.85em; font-weight: 500; text-align: right; word-break: break-word; }
  .field-value.currency { font-variant-numeric: tabular-nums; font-family: monospace; }

  h3 { font-size: 1em; margin: 0; color: #334155; }
  .table-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75em; }

  .table-scroll { overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 8px; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.82em; }
  .data-table th { padding: 0.6em 0.75em; background: #f8fafc; border-bottom: 2px solid #e2e8f0; text-align: left; font-weight: 600; color: #475569; white-space: nowrap; }
  .data-table td { padding: 0.5em 0.75em; border-bottom: 1px solid #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }
  .data-table tbody tr:hover { background: #f8fafc; }
  .data-table .row-num { color: #94a3b8; font-size: 0.85em; width: 2em; text-align: center; }
  .data-table .num-col { text-align: right; font-variant-numeric: tabular-nums; font-family: monospace; }
  .subtotal { padding: 0.6em 1em; text-align: right; font-weight: 600; font-size: 0.9em; border-top: 2px solid #e2e8f0; background: #f8fafc; border-radius: 0 0 8px 8px; }

  .page-strip { display: flex; flex-wrap: wrap; gap: 0.35em; margin-top: 2em; padding-top: 1.5em; border-top: 1px solid #e2e8f0; }
  .strip-chip {
    display: flex; align-items: center; justify-content: center;
    width: 2.2em; height: 2.2em; border: 1px solid #d1d5db;
    border-bottom: 3px solid; border-radius: 4px; background: white;
    text-decoration: none; color: #475569; font-size: 0.85em; font-weight: 500;
  }
  .strip-chip:hover { background: #f1f5f9; }
  .strip-active { background: #1e293b !important; color: white !important; border-color: #1e293b !important; }
</style>
