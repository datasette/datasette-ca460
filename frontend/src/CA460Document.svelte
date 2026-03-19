<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import DevBadge from './DevBadge.svelte';
  import CopyTableButton from './CopyTableButton.svelte';
  import { documentParsed, syncEvents } from './api';
  import { loadPageData } from './pageData';

  const pageData = loadPageData<{ database: string; document_id: number }>();
  const database = pageData.database;
  const documentId = String(pageData.document_id);

  interface PageInfo {
    page_id: number;
    page_number: number;
    has_image: boolean;
    classification_model: string | null;
    page_type: string | null;
  }

  interface ParsedPage {
    page_number: number;
    page_type: string;
    parsed_data: Record<string, unknown>;
    timing: Record<string, unknown>;
    created_at: string;
  }

  interface DocumentData {
    document: { id: number; source: string; page_count: number; title: string; has_pdf: boolean; pdf_filename: string | null };
    pages: PageInfo[];
    models: Record<string, ParsedPage[]>;
  }

  interface SyncEvent { type: string; message: string; created_at: string; }
  interface SyncJob { status: string; error: string | null; started_at: string; completed_at: string | null; }

  let documentData: DocumentData | null = $state(null);
  let loading = $state(true);
  let selectedModel = $state('');

  let syncJobId: string | null = $state(null);
  let jobStatus: SyncJob | null = $state(null);
  let events: SyncEvent[] = $state([]);
  let pollInterval: ReturnType<typeof setInterval> | null = null;

  let eventsContainer: HTMLElement | null = $state(null);
  $effect(() => { if (eventsContainer && events.length > 0) eventsContainer.scrollTop = eventsContainer.scrollHeight; });

  $effect(() => {
    if (!documentData) return;
    const filing = filingTitle();
    if (filing) {
      document.title = `${filing.name} ${filing.period} | datasette-ca460`;
    } else {
      document.title = `${documentData.document.title} | datasette-ca460`;
    }
  });

  onMount(() => {
    const params = new URLSearchParams(window.location.search);
    syncJobId = params.get('sync_job_id');
    if (syncJobId) startPolling();
    loadDocument();
  });

  onDestroy(() => { if (pollInterval) clearInterval(pollInterval); });

  async function loadDocument() {
    loading = true;
    try {
      const { data, error, response } = await documentParsed(database, documentId);
      if (error || !response.ok) { documentData = null; return; }
      const d = data as any;
      if (d.error) { documentData = null; return; }
      documentData = d;
      const modelNames = Object.keys(d.models);
      if (modelNames.length > 0 && !selectedModel) selectedModel = modelNames[0];
    } catch (e) { documentData = null; }
    finally { loading = false; }
  }

  function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollEvents();
    pollInterval = setInterval(pollEvents, 1000);
  }
  async function pollEvents() {
    if (!syncJobId) return;
    try {
      const { data, error, response } = await syncEvents(database, syncJobId);
      if (error || !response.ok) return;
      const d = data as any;
      jobStatus = d.job;
      events = d.events;
      if (d.job.status === 'completed' || d.job.status === 'failed') {
        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
        if (d.job.status === 'completed') await loadDocument();
      }
    } catch (e) { /* ignore */ }
  }

  // Helpers
  function pageUrl(pn: number) { return `/${database}/-/ca460/document/${documentId}/page/${pn}`; }
  function imageUrl(pn: number) { return `/${database}/-/ca460/api/document/${documentId}/page/${pn}/image`; }
  function pdfUrl() { return `/${database}/-/ca460/api/document/${documentId}/pdf`; }

  function pageTypeLabel(pt: string): string { return pt.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); }
  function pageTypeColor(pt: string | null): string {
    const colors: Record<string, string> = {
      'cover-page-part-1': '#6366f1', 'cover-page-part-2': '#818cf8', 'summary-page': '#059669',
      'schedule-a': '#d97706', 'schedule-b-part-1': '#b45309', 'schedule-b-part-2': '#92400e',
      'schedule-c': '#0891b2', 'schedule-d': '#7c3aed', 'schedule-e': '#db2777',
      'schedule-f': '#e11d48', 'schedule-g': '#84cc16', 'schedule-h': '#f59e0b',
      'schedule-i': '#14b8a6', 'unknown': '#9ca3af',
    };
    return pt ? colors[pt] || '#6b7280' : '#d1d5db';
  }

  function currentModelPages(): ParsedPage[] { return documentData?.models[selectedModel] || []; }
  function pagesByType(): Record<string, ParsedPage[]> {
    const grouped: Record<string, ParsedPage[]> = {};
    for (const page of currentModelPages()) {
      if (!grouped[page.page_type]) grouped[page.page_type] = [];
      grouped[page.page_type].push(page);
    }
    return grouped;
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
  function getMetaFields(data: Record<string, unknown>): [string, unknown][] {
    return Object.entries(data).filter(([k]) => k !== 'line_items' && k !== 'subtotal');
  }
  function typeHasLineItems(pages: ParsedPage[]): boolean { return pages.some(p => hasLineItems(p)); }
  function mergedLineItems(pages: ParsedPage[]): { page_number: number; item: Record<string, unknown> }[] {
    const result: { page_number: number; item: Record<string, unknown> }[] = [];
    for (const page of pages) for (const item of getLineItems(page)) result.push({ page_number: page.page_number, item });
    return result;
  }
  function mergedColumns(rows: { item: Record<string, unknown> }[]): string[] {
    const allKeys = new Set<string>();
    for (const r of rows) for (const k of Object.keys(r.item)) allKeys.add(k);
    return Array.from(allKeys);
  }
  function formatFieldName(name: string): string { return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); }
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
  function isCurrencyField(key: string): boolean { return /amount|balance|total|cash|contributions|expenditures|payments|loans|debt|line_\d/.test(key); }
  function colDisplayValue(key: string, v: unknown): string { return isCurrencyField(key) ? formatCurrency(v) : formatValue(v); }
  function colHeaderName(key: string): string { return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); }

  const TYPE_ORDER = [
    'cover-page-part-1', 'cover-page-part-2', 'summary-page',
    'schedule-a', 'schedule-b-part-1', 'schedule-b-part-2',
    'schedule-c', 'schedule-d', 'schedule-e', 'schedule-f',
    'schedule-g', 'schedule-h', 'schedule-i', 'unknown'
  ];
  function sortedPageTypes(types: string[]): string[] {
    return types.sort((a, b) => (TYPE_ORDER.indexOf(a) === -1 ? 999 : TYPE_ORDER.indexOf(a)) - (TYPE_ORDER.indexOf(b) === -1 ? 999 : TYPE_ORDER.indexOf(b)));
  }

  const PAGE_SIZE = 20;
  let tablePageMap: Record<string, number> = $state({});

  function tablePage(key: string): number { return tablePageMap[key] || 0; }
  function setTablePage(key: string, p: number) { tablePageMap[key] = p; }
  function totalTablePages(totalRows: number): number { return Math.ceil(totalRows / PAGE_SIZE); }
  function paginatedRows<T>(rows: T[], key: string): T[] {
    const p = tablePage(key);
    return rows.slice(p * PAGE_SIZE, (p + 1) * PAGE_SIZE);
  }

  function getStatusClass(s: string) { return s === 'running' ? 'status-running' : s === 'completed' ? 'status-completed' : s === 'failed' ? 'status-failed' : ''; }
  function getEventClass(t: string) { return t === 'warning' ? 'event-warning' : t === 'error' ? 'event-error' : t === 'success' ? 'event-success' : 'event-info'; }

  // Thumbnail tooltip action
  const thumbCache = new Map<number, string>();

  function pageThumbTooltip(node: HTMLElement, pn: number) {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tooltip = () => document.getElementById('page-thumb-tooltip')!;

    function show() {
      timer = setTimeout(async () => {
        const tt = tooltip();
        const rect = node.getBoundingClientRect();
        tt.style.left = `${rect.left + rect.width / 2}px`;
        tt.style.top = `${rect.top - 8}px`;

        if (thumbCache.has(pn)) {
          tt.innerHTML = `<img src="${thumbCache.get(pn)}" />`;
        } else {
          tt.innerHTML = '<span class="thumb-loading">Loading...</span>';
          try {
            const resp = await fetch(imageUrl(pn));
            if (resp.ok) {
              const blob = await resp.blob();
              const url = URL.createObjectURL(blob);
              thumbCache.set(pn, url);
              tt.innerHTML = `<img src="${url}" />`;
            } else { tt.innerHTML = ''; return; }
          } catch { tt.innerHTML = ''; return; }
        }
        tt.classList.add('visible');
      }, 100);
    }

    function hide() {
      if (timer) { clearTimeout(timer); timer = null; }
      tooltip().classList.remove('visible');
    }

    node.addEventListener('mouseenter', show);
    node.addEventListener('mouseleave', hide);
    return {
      destroy() { node.removeEventListener('mouseenter', show); node.removeEventListener('mouseleave', hide); hide(); }
    };
  }

  function friendlyDate(d: string): string {
    const date = new Date(d + 'T00:00:00');
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function filingTitle(): { name: string; period: string } | null {
    const pages = currentModelPages();
    const source = pages.find(p => p.page_type === 'cover-page-part-1') || pages.find(p => p.page_type === 'summary-page');
    if (!source) return null;
    const d = source.parsed_data;
    const name = (d.committee_name as string) || null;
    const from = (d.statement_covers_period_from as string) || null;
    const through = (d.statement_covers_period_through as string) || null;
    if (!name || !from || !through) return null;
    return { name, period: `${friendlyDate(from)} \u2013 ${friendlyDate(through)}` };
  }

  interface SummaryStats {
    page_number: number;
    beginning_cash: number;
    total_receipts: number;
    total_expenditures: number;
    ending_cash: number;
    cash_change: number;
  }

  function summaryStats(): SummaryStats | null {
    const pages = currentModelPages();
    const summary = pages.find(p => p.page_type === 'summary-page');
    if (!summary) return null;
    const d = summary.parsed_data;
    const beginning = Number(d.line_12_beginning_cash_balance) || 0;
    const receipts = Number(d.line_5_total_contributions_received_col_a) || 0;
    const expenditures = Number(d.line_11_total_expenditures_col_a) || 0;
    const ending = Number(d.line_16_ending_cash_balance) || 0;
    if (!beginning && !receipts && !expenditures && !ending) return null;
    return {
      page_number: summary.page_number,
      beginning_cash: beginning,
      total_receipts: receipts,
      total_expenditures: expenditures,
      ending_cash: ending,
      cash_change: ending - beginning,
    };
  }

  function summaryFieldUrl(pageNum: number, field: string): string {
    return pageUrl(pageNum) + `?hl=${encodeURIComponent(field)}`;
  }
</script>

<main>
  <nav class="breadcrumb">
    <a href="/{database}/-/ca460">Documents</a>
    <span class="sep">/</span>
    {#if documentData}
      <span>{documentData.document.title}</span>
    {:else}
      <span>Document {documentId}</span>
    {/if}
    <DevBadge />
  </nav>

  {#if syncJobId && jobStatus}
    <div class="progress-bar">
      <div class="progress-header">
        <span class="progress-label">Processing</span>
        <span class="job-badge {getStatusClass(jobStatus.status)}">{jobStatus.status}</span>
      </div>
      <div class="events-log" bind:this={eventsContainer}>
        {#each events as event}
          <div class="event {getEventClass(event.type)}">{event.message}</div>
        {/each}
        {#if jobStatus.status === 'failed' && jobStatus.error}
          <div class="event event-error">{jobStatus.error}</div>
        {/if}
      </div>
    </div>
  {/if}

  {#if loading}
    <div class="loading">Loading...</div>
  {:else if !documentData}
    <div class="empty-state">Document not found.</div>
  {:else}
    <div class="doc-header">
      {#if filingTitle()}
        <h1>{filingTitle()!.name} <span class="title-period">{filingTitle()!.period}</span></h1>
      {:else}
        <h1>{documentData.document.title}</h1>
      {/if}
      <div class="doc-meta">
        <span class="meta-chip">{documentData.document.page_count} pages</span>
        <span class="meta-chip source-{documentData.document.source}">{documentData.document.source}</span>
        {#if documentData.document.has_pdf}
          <a href={pdfUrl()} target="_blank" class="meta-chip pdf-link">View PDF</a>
        {/if}
        {#if Object.keys(documentData.models).length > 0}
          <div class="model-selector">
            <label for="model-select">Model:</label>
            <select id="model-select" bind:value={selectedModel}>
              {#each Object.keys(documentData.models) as model}
                <option value={model}>{model}</option>
              {/each}
            </select>
          </div>
        {/if}
      </div>
    </div>

    <!-- Summary stats -->
    {#if summaryStats()}
      {#each [summaryStats()!] as stats}
        <div class="stats-cards">
          <a class="stat-card" href={summaryFieldUrl(stats.page_number, 'line_12_beginning_cash_balance')}>
            <span class="stat-label">Cash on Hand - Start</span>
            <span class="stat-value">{formatCurrency(stats.beginning_cash)}</span>
          </a>
          <a class="stat-card" href={summaryFieldUrl(stats.page_number, 'line_5_total_contributions_received_col_a')}>
            <span class="stat-label">Receipts</span>
            <span class="stat-value positive">{formatCurrency(stats.total_receipts)}</span>
          </a>
          <a class="stat-card" href={summaryFieldUrl(stats.page_number, 'line_11_total_expenditures_col_a')}>
            <span class="stat-label">Expenditures</span>
            <span class="stat-value negative">{formatCurrency(stats.total_expenditures)}</span>
          </a>
          <a class="stat-card" href={summaryFieldUrl(stats.page_number, 'line_16_ending_cash_balance')}>
            <span class="stat-label">Cash on Hand - End</span>
            <span class="stat-value">{formatCurrency(stats.ending_cash)}</span>
            {#if stats.cash_change !== 0}
              <span class="stat-change" class:change-up={stats.cash_change > 0} class:change-down={stats.cash_change < 0}>
                {stats.cash_change > 0 ? '\u2191' : '\u2193'} {formatCurrency(Math.abs(stats.cash_change))}
              </span>
            {/if}
          </a>
        </div>
      {/each}
    {/if}

    <!-- Page Map -->
    <section class="section page-map-section">
      <h2 class="section-title" style="justify-content: center; border-left: none;">Page Map</h2>
      <div class="page-grid">
        {#each documentData.pages as page}
          {@const pt = page.page_type}
          <a href={pageUrl(page.page_number)} class="page-chip" style="background: {pageTypeColor(pt)}20; border-color: {pageTypeColor(pt)}"
            title="Page {page.page_number}: {pt ? pageTypeLabel(pt) : 'Unclassified'}"
            use:pageThumbTooltip={page.page_number}>
            {page.page_number}
          </a>
        {/each}
      </div>
      <div class="legend">
        {#each TYPE_ORDER.filter(t => documentData?.pages.some(p => p.page_type === t)) as pt}
          <span class="legend-item">
            <span class="legend-dot" style="background: {pageTypeColor(pt)}"></span>
            {pageTypeLabel(pt)}
          </span>
        {/each}
      </div>
    </section>

    <!-- Sections by page type -->
    {#if Object.keys(documentData.models).length === 0}
      <div class="empty-state">No parsed data yet.</div>
    {:else}
      <!-- Table sections first (Schedule A, E, etc.) -->
      {#each sortedPageTypes(Object.keys(pagesByType())).filter(t => typeHasLineItems(pagesByType()[t])) as pageType}
        {#each [pagesByType()[pageType]] as pages}
          <!-- Table sections (Schedule A, E, etc.) stay open -->
          <section class="section">
            <h2 class="section-title" style="border-left-color: {pageTypeColor(pageType)}">
              {pageTypeLabel(pageType)}
              <span class="section-count">{pages.length} page{pages.length !== 1 ? 's' : ''}</span>
            </h2>
            {#each [mergedLineItems(pages)] as rows}
              {#each [mergedColumns(rows)] as cols}
                <div class="table-toolbar">
                  <span class="table-info">{rows.length} items</span>
                  <CopyTableButton columns={cols} rows={rows.map(r => r.item)} />
                </div>
                <div class="table-wrapper">
                  <table class="data-table">
                    <thead>
                      <tr>
                        <th>Page</th>
                        {#each cols as col}
                          <th class:num-col={isCurrencyField(col)}>{colHeaderName(col)}</th>
                        {/each}
                      </tr>
                    </thead>
                    <tbody>
                      {#each paginatedRows(rows, pageType) as row}
                        <tr>
                          <td class="page-cell"><a href={pageUrl(row.page_number)} class="page-link">p.{row.page_number}</a></td>
                          {#each cols as col}
                            <td class:num-col={isCurrencyField(col)}>{colDisplayValue(col, row.item[col])}</td>
                          {/each}
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
                {#if rows.length > PAGE_SIZE}
                  <div class="pagination">
                    <button disabled={tablePage(pageType) === 0} onclick={() => setTablePage(pageType, tablePage(pageType) - 1)}>&larr; Prev</button>
                    <span>{tablePage(pageType) * PAGE_SIZE + 1}&ndash;{Math.min((tablePage(pageType) + 1) * PAGE_SIZE, rows.length)} of {rows.length}</span>
                    <button disabled={tablePage(pageType) >= totalTablePages(rows.length) - 1} onclick={() => setTablePage(pageType, tablePage(pageType) + 1)}>Next &rarr;</button>
                  </div>
                {/if}
              {/each}
            {/each}
          </section>
        {/each}
      {/each}
      <!-- Non-table sections collapsed -->
      {#each sortedPageTypes(Object.keys(pagesByType())).filter(t => !typeHasLineItems(pagesByType()[t])) as pageType}
        {#each [pagesByType()[pageType]] as pages}
          <section class="section">
            <details>
              <summary class="section-title" style="border-left-color: {pageTypeColor(pageType)}">
                {pageTypeLabel(pageType)}
                <span class="section-count">{pages.length} page{pages.length !== 1 ? 's' : ''}</span>
              </summary>
              {#each pages as page}
                <div class="parsed-card">
                  <div class="parsed-card-header">
                    <a href={pageUrl(page.page_number)} class="page-link">Page {page.page_number}</a>
                  </div>
                  {#if getMetaFields(page.parsed_data || {}).length > 0}
                    <div class="meta-grid">
                      {#each getMetaFields(page.parsed_data || {}) as [key, value]}
                        <div class="meta-field">
                          <span class="meta-label">{formatFieldName(key)}</span>
                          <span class="meta-value" class:currency={isCurrencyField(key)}>{colDisplayValue(key, value)}</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              {/each}
            </details>
          </section>
        {/each}
      {/each}
    {/if}
  {/if}
</main>
<div id="page-thumb-tooltip" class="thumb-tooltip"></div>

<style>
  main { max-width: 100%; }

  .breadcrumb { display: flex; align-items: center; gap: 0.4em; font-size: 0.9em; color: #64748b; margin-bottom: 1em; }
  .breadcrumb a { color: #0066cc; text-decoration: none; }
  .breadcrumb a:hover { text-decoration: underline; }
  .breadcrumb .sep { color: #cbd5e1; }

  .doc-header { margin-bottom: 1em; }
  .doc-header h1 { margin: 0 0 0.75em; font-size: 1.5em; }
  .title-period { font-weight: normal; color: #64748b; font-size: 0.7em; }
  .doc-meta { display: flex; align-items: center; gap: 0.75em; flex-wrap: wrap; }
  .meta-chip { display: inline-block; padding: 0.25em 0.7em; background: #f1f5f9; border-radius: 4px; font-size: 0.85em; color: #475569; }
  .source-upload { background: #e0f2fe; color: #0369a1; }
  .source-documentcloud { background: #f0e6ff; color: #4a1d8e; }
  .pdf-link { background: #fef2f2; color: #dc2626; text-decoration: none; font-weight: 500; }
  .pdf-link:hover { background: #fee2e2; }
  .model-selector { display: flex; align-items: center; gap: 0.4em; margin-left: auto; }
  .model-selector label { font-size: 0.85em; color: #64748b; }
  .model-selector select { padding: 0.35em 0.6em; font-size: 0.85em; border: 1px solid #d1d5db; border-radius: 4px; }

  .loading, .empty-state { text-align: center; padding: 4em; color: #94a3b8; font-size: 1.1em; }

  /* Summary stat cards */
  .stats-cards {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75em;
    margin-bottom: 1.5em;
  }
  @media (max-width: 800px) { .stats-cards { grid-template-columns: repeat(2, 1fr); } }
  .stat-card {
    display: flex; flex-direction: column; gap: 0.25em;
    padding: 1em 1.25em;
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
    text-decoration: none; color: inherit; transition: border-color 0.15s, box-shadow 0.15s;
  }
  .stat-card:hover { border-color: #94a3b8; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  .stat-label { font-size: 0.8em; color: #64748b; }
  .stat-value { font-size: 1.3em; font-weight: 700; font-variant-numeric: tabular-nums; font-family: monospace; color: #1e293b; }
  .stat-value.positive { color: #0066cc; }
  .stat-value.negative { color: #dc2626; }
  .stat-change { font-size: 0.8em; font-family: monospace; }
  .change-up { color: #059669; }
  .change-down { color: #dc2626; }

  /* Progress */
  .progress-bar { margin-bottom: 2em; padding: 1em 1.25em; background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; }
  .progress-header { display: flex; align-items: center; gap: 0.5em; margin-bottom: 0.5em; }
  .progress-label { font-weight: 600; font-size: 0.9em; }
  .job-badge { padding: 0.15em 0.5em; border-radius: 3px; font-size: 0.8em; font-weight: 600; }
  .status-running { background: #fef3c7; color: #92400e; }
  .status-completed { background: #d1fae5; color: #065f46; }
  .status-failed { background: #fee2e2; color: #991b1b; }
  .events-log { max-height: 150px; overflow-y: auto; font-family: monospace; font-size: 0.8em; line-height: 1.6; }
  .event-info { color: #475569; }
  .event-warning { color: #92400e; }
  .event-error { color: #991b1b; font-weight: 600; }
  .event-success { color: #065f46; font-weight: 600; }

  /* Sections */
  .section { margin-bottom: 1.5em; }
  .section-title {
    font-size: 1.05em; margin: 0 0 0.75em;
    padding: 0.4em 0 0.4em 0.75em;
    border-left: 4px solid #e2e8f0;
    display: flex; align-items: center; gap: 0.5em;
    cursor: default;
  }
  details .section-title { cursor: pointer; }
  details .section-title::-webkit-details-marker { display: none; }
  details .section-title::before { content: '\25B6'; font-size: 0.6em; color: #94a3b8; transition: transform 0.15s; }
  details[open] .section-title::before { transform: rotate(90deg); }
  .section-count { font-size: 0.75em; color: #94a3b8; font-weight: normal; }

  /* Page grid */
  .page-grid { display: flex; flex-wrap: wrap; gap: 0.35em; justify-content: center; }
  .page-chip {
    display: flex; align-items: center; justify-content: center;
    width: 2.4em; height: 2.4em;
    border: 2px solid; border-radius: 6px;
    text-decoration: none; color: #1e293b;
    font-size: 0.85em; font-weight: 700;
    transition: box-shadow 0.1s, transform 0.1s;
  }
  .page-chip:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); transform: scale(1.1); }

  .legend { display: flex; flex-wrap: wrap; gap: 1em; margin-top: 0.75em; font-size: 0.82em; color: #64748b; justify-content: center; }
  .legend-item { display: flex; align-items: center; gap: 0.35em; }
  .legend-dot { width: 10px; height: 10px; border-radius: 2px; }

  /* Parsed cards */
  .parsed-card { margin-bottom: 1em; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
  .parsed-card-header { padding: 0.75em 1em; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
  .page-link { background: none; border: none; color: #0066cc; text-decoration: none; font-weight: 600; font-size: 0.9em; }
  .page-link:hover { text-decoration: underline; }

  .meta-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 0; padding: 0.75em 1em;
  }
  .meta-field { display: flex; justify-content: space-between; padding: 0.4em 0.75em; border-bottom: 1px solid #f1f5f9; gap: 1em; }
  .meta-label { color: #64748b; font-size: 0.85em; }
  .meta-value { font-size: 0.85em; font-weight: 500; }
  .meta-value.currency { font-variant-numeric: tabular-nums; font-family: monospace; }

  /* Tables */
  .table-wrapper { overflow-x: auto; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.84em; }
  .data-table th { padding: 0.6em 0.75em; background: #f8fafc; border-bottom: 2px solid #e2e8f0; text-align: left; font-weight: 600; color: #475569; white-space: nowrap; }
  .data-table td { padding: 0.5em 0.75em; border-bottom: 1px solid #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 250px; }
  .data-table tbody tr:hover { background: #f8fafc; }
  .data-table .num-col { text-align: right; font-variant-numeric: tabular-nums; font-family: monospace; }
  .page-cell { white-space: nowrap; }
  .table-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 1em; margin-bottom: 0.5em; }
  .table-info { color: #64748b; font-size: 0.85em; }

  .pagination {
    display: flex; align-items: center; justify-content: center; gap: 1em;
    padding: 0.75em; font-size: 0.85em; color: #475569;
  }
  .pagination button {
    padding: 0.3em 0.8em; background: #f1f5f9; border: 1px solid #d1d5db;
    border-radius: 4px; cursor: pointer; font-size: 1em; color: #475569;
  }
  .pagination button:hover:not(:disabled) { background: #e2e8f0; }
  .pagination button:disabled { opacity: 0.4; cursor: default; }

  /* Thumbnail tooltip */
  :global(.thumb-tooltip) {
    position: fixed; transform: translate(-50%, -100%);
    pointer-events: none; z-index: 100; opacity: 0; transition: opacity 0.15s;
    background: white; border: 1px solid #d1d5db; border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.15); padding: 4px; max-width: 200px;
  }
  :global(.thumb-tooltip.visible) { opacity: 1; }
  :global(.thumb-tooltip img) { display: block; width: 100%; height: auto; border-radius: 4px; }
  :global(.thumb-loading) { display: block; padding: 1em 1.5em; color: #94a3b8; font-size: 0.8em; }
</style>
