<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import DevBadge from './DevBadge.svelte';
  import CopyTableButton from './CopyTableButton.svelte';
  import { documentParsed, syncEvents } from './api';
  import { getDatabaseFromUrl, getDocumentIdFromUrl } from './utils';

  const database = getDatabaseFromUrl();
  const documentId = getDocumentIdFromUrl();

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

  function getStatusClass(s: string) { return s === 'running' ? 'status-running' : s === 'completed' ? 'status-completed' : s === 'failed' ? 'status-failed' : ''; }
  function getEventClass(t: string) { return t === 'warning' ? 'event-warning' : t === 'error' ? 'event-error' : t === 'success' ? 'event-success' : 'event-info'; }

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
    total_receipts: number;
    total_expenditures: number;
    ending_cash: number;
  }

  function summaryStats(): SummaryStats | null {
    const pages = currentModelPages();
    const summary = pages.find(p => p.page_type === 'summary-page');
    if (!summary) return null;
    const d = summary.parsed_data;
    const receipts = d.line_5_total_contributions_received_col_a;
    const expenditures = d.line_11_total_expenditures_col_a;
    const cash = d.line_16_ending_cash_balance;
    if (receipts == null && expenditures == null && cash == null) return null;
    return {
      total_receipts: Number(receipts) || 0,
      total_expenditures: Number(expenditures) || 0,
      ending_cash: Number(cash) || 0,
    };
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
      <div class="stats-bar">
        <div class="stat">
          <span class="stat-label">Total Receipts</span>
          <span class="stat-value positive">{formatCurrency(summaryStats()!.total_receipts)}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Total Expenditures</span>
          <span class="stat-value negative">{formatCurrency(summaryStats()!.total_expenditures)}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Cash on Hand</span>
          <span class="stat-value">{formatCurrency(summaryStats()!.ending_cash)}</span>
        </div>
      </div>
    {/if}

    <!-- Page Map -->
    <section class="section page-map-section">
      <h2 class="section-title" style="justify-content: center; border-left: none;">Page Map</h2>
      <div class="page-grid">
        {#each documentData.pages as page}
          {@const pt = page.page_type}
          <a href={pageUrl(page.page_number)} class="page-chip" style="border-left-color: {pageTypeColor(pt)}"
            title="Page {page.page_number}: {pt ? pageTypeLabel(pt) : 'Unclassified'}">
            <span class="page-num">{page.page_number}</span>
            <span class="page-type-label" style="color: {pageTypeColor(pt)}">{pt ? pageTypeLabel(pt) : '?'}</span>
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
                      {#each rows as row}
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
                <div class="table-summary">
                  {rows.length} items across {pages.length} page{pages.length !== 1 ? 's' : ''}
                </div>
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

  /* Summary stats bar */
  .stats-bar {
    display: flex; gap: 1.5em; flex-wrap: wrap;
    padding: 1em 1.25em; margin-bottom: 1.25em;
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
  }
  .stat { display: flex; flex-direction: column; gap: 0.2em; }
  .stat-label { font-size: 0.8em; color: #64748b; text-transform: uppercase; letter-spacing: 0.03em; }
  .stat-value { font-size: 1.15em; font-weight: 700; font-variant-numeric: tabular-nums; font-family: monospace; color: #1e293b; }
  .stat-value.positive { color: #059669; }
  .stat-value.negative { color: #dc2626; }

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
  .page-grid { display: flex; flex-wrap: wrap; gap: 0.5em; justify-content: center; }
  .page-chip {
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.15em;
    width: 5.5em; height: 4em;
    border: 1px solid #e2e8f0; border-left: 3px solid;
    border-radius: 6px; background: white; text-decoration: none; color: inherit;
    font-size: 0.82em; transition: box-shadow 0.1s;
  }
  .page-chip:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); background: #f8fafc; }
  .page-num { font-weight: 700; font-size: 1.15em; color: #1e293b; }
  .page-type-label { font-size: 0.68em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 4.5em; text-align: center; }

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
  .table-toolbar { display: flex; justify-content: flex-end; margin-bottom: 0.5em; }
  .table-summary { padding: 0.6em 1em; color: #64748b; font-size: 0.85em; }
</style>
