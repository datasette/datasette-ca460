<script lang="ts">
  import { onMount } from 'svelte';
  import {
    dcConfig, dcSearch, dcDocument, dcProject,
    dcResolveUrl, dcImport,
  } from './api';
  import DCDocumentCard from './DCDocumentCard.svelte';
  import DCDocumentPreview from './DCDocumentPreview.svelte';

  interface Props {
    database: string;
    pageTypeModel: string;
    parserModel: string;
    onJobStarted: (syncJobId: string) => void;
  }

  let { database, pageTypeModel, parserModel, onJobStarted }: Props = $props();

  // Config
  let authenticated = $state(false);

  // Input / mode
  let query = $state('');
  type Mode = 'idle' | 'search' | 'project' | 'document';
  let mode: Mode = $state('idle');

  // Results
  let results: any[] = $state([]);
  let resultCount = $state(0);
  let currentPage = $state(1);
  let loading = $state(false);
  let error: string | null = $state(null);

  // Project context
  let projectMeta: any = $state(null);

  // Preview
  let previewDoc: any = $state(null);

  // Selection
  let selectedIds: Set<number> = $state(new Set());

  // Import
  let importing = $state(false);

  onMount(async () => {
    try {
      const { data } = await dcConfig(database);
      if (data) authenticated = (data as any).authenticated;
    } catch {}
  });

  function isDocumentCloudUrl(text: string): boolean {
    return text.includes('documentcloud.org');
  }

  function isBareNumber(text: string): boolean {
    return /^\d+$/.test(text.trim());
  }

  async function handleSubmit(e: Event) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    error = null;
    previewDoc = null;
    currentPage = 1;

    if (isDocumentCloudUrl(q)) {
      await resolveUrl(q);
    } else if (isBareNumber(q)) {
      await loadProject(parseInt(q, 10));
    } else {
      await searchDocs(q, 1);
    }
  }

  async function resolveUrl(url: string) {
    loading = true;
    try {
      const { data, error: err } = await dcResolveUrl(database, url);
      if (err || !data) { error = 'Unrecognised DocumentCloud URL'; return; }
      const d = data as any;
      if (d.type === 'document') {
        await showDocument(d.id);
      } else if (d.type === 'project') {
        await loadProject(d.id);
      }
    } catch (e: any) {
      error = e.message || 'Failed to resolve URL';
    } finally {
      loading = false;
    }
  }

  async function showDocument(docId: number) {
    loading = true;
    mode = 'document';
    try {
      const { data } = await dcDocument(database, docId);
      if (!data) { error = 'Document not found'; return; }
      previewDoc = data;
      results = [];
    } catch (e: any) {
      error = e.message || 'Failed to load document';
    } finally {
      loading = false;
    }
  }

  async function searchDocs(q: string, page: number) {
    loading = true;
    mode = 'search';
    projectMeta = null;
    try {
      const { data } = await dcSearch(database, q, page);
      const d = data as any;
      results = d?.results || [];
      resultCount = d?.count || 0;
      currentPage = page;
    } catch (e: any) {
      error = e.message || 'Search failed';
    } finally {
      loading = false;
    }
  }

  async function loadProject(projectId: number) {
    loading = true;
    mode = 'project';
    try {
      const { data } = await dcProject(database, projectId);
      const d = data as any;
      projectMeta = d?.project;
      results = d?.documents?.results || [];
      resultCount = d?.documents?.count || 0;
      currentPage = 1;
    } catch (e: any) {
      error = e.message || 'Failed to load project';
    } finally {
      loading = false;
    }
  }

  async function loadPage(page: number) {
    if (mode === 'search') {
      await searchDocs(query.trim(), page);
    } else if (mode === 'project' && projectMeta) {
      loading = true;
      try {
        const { data } = await dcProject(database, projectMeta.id, page);
        const d = data as any;
        results = d?.documents?.results || [];
        currentPage = page;
      } catch {} finally { loading = false; }
    }
  }

  function toggleSelection(docId: number) {
    const next = new Set(selectedIds);
    if (next.has(docId)) next.delete(docId);
    else next.add(docId);
    selectedIds = next;
  }

  function handlePreview(doc: any) {
    previewDoc = doc;
  }

  function handlePreviewBack() {
    previewDoc = null;
  }

  function handlePreviewImport(docId: number) {
    const next = new Set(selectedIds);
    next.add(docId);
    selectedIds = next;
    previewDoc = null;
  }

  function selectAll() {
    const next = new Set(selectedIds);
    for (const doc of results) next.add(doc.id);
    selectedIds = next;
  }

  function clearSelection() {
    selectedIds = new Set();
  }

  async function handleImport() {
    if (selectedIds.size === 0) return;
    importing = true;
    error = null;
    try {
      const { data, error: err } = await dcImport(database, {
        document_ids: Array.from(selectedIds),
        page_type_model: pageTypeModel,
        parser_model: parserModel,
      });
      if (err || !data) { error = 'Import failed'; return; }
      const d = data as any;
      onJobStarted(d.sync_job_id);
    } catch (e: any) {
      error = e.message || 'Import failed';
    } finally {
      importing = false;
    }
  }

  let totalPages = $derived(Math.max(1, Math.ceil(resultCount / 25)));
  let hasNext = $derived(currentPage < totalPages);
  let hasPrev = $derived(currentPage > 1);
</script>

<div class="browser">
  <form class="search-bar" onsubmit={handleSubmit}>
    <input
      type="text"
      bind:value={query}
      placeholder="Search documents, paste a DocumentCloud URL, or enter a project ID"
    />
    <button type="submit" class="btn-primary" disabled={loading || !query.trim()}>
      {loading ? 'Loading...' : 'Go'}
    </button>
  </form>

  {#if error}
    <div class="error-msg">{error}</div>
  {/if}

  {#if previewDoc}
    <DCDocumentPreview
      doc={previewDoc}
      onBack={handlePreviewBack}
      onImport={handlePreviewImport}
    />
  {:else}
    {#if projectMeta && mode === 'project'}
      <div class="project-header">
        <strong>{projectMeta.title || `Project ${projectMeta.id}`}</strong>
        {#if projectMeta.description}
          <span class="project-desc">{projectMeta.description}</span>
        {/if}
      </div>
    {/if}

    {#if results.length > 0}
      <div class="results-header">
        <span class="result-count">{resultCount} document{resultCount !== 1 ? 's' : ''}</span>
        <div class="bulk-actions">
          <button class="btn-sm" onclick={selectAll}>Select all</button>
          {#if selectedIds.size > 0}
            <button class="btn-sm" onclick={clearSelection}>Clear</button>
          {/if}
        </div>
      </div>

      <div class="results-grid">
        {#each results as doc (doc.id)}
          <DCDocumentCard
            {doc}
            selected={selectedIds.has(doc.id)}
            onToggle={toggleSelection}
            onPreview={handlePreview}
          />
        {/each}
      </div>

      {#if totalPages > 1}
        <div class="pagination">
          <button class="btn-sm" disabled={!hasPrev} onclick={() => loadPage(currentPage - 1)}>Prev</button>
          <span class="page-info">{currentPage} / {totalPages}</span>
          <button class="btn-sm" disabled={!hasNext} onclick={() => loadPage(currentPage + 1)}>Next</button>
        </div>
      {/if}
    {:else if mode !== 'idle' && !loading}
      <p class="empty">No documents found.</p>
    {/if}
  {/if}

  {#if selectedIds.size > 0 && !previewDoc}
    <div class="selection-tray">
      <span>{selectedIds.size} selected</span>
      <button class="btn-primary" onclick={handleImport} disabled={importing}>
        {importing ? 'Importing...' : `Import ${selectedIds.size} document${selectedIds.size > 1 ? 's' : ''}`}
      </button>
    </div>
  {/if}
</div>

<style>
  .browser { display: flex; flex-direction: column; gap: 0.75em; }

  .search-bar { display: flex; gap: 0.5em; }
  .search-bar input {
    flex: 1;
    padding: 0.5em 0.7em;
    font-size: 0.9em;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    box-sizing: border-box;
  }
  .btn-primary { padding: 0.5em 1em; background: #0066cc; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85em; white-space: nowrap; }
  .btn-primary:hover:not(:disabled) { background: #0052a3; }
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

  .error-msg { padding: 0.5em 0.7em; background: #fee2e2; color: #991b1b; border-radius: 6px; font-size: 0.85em; }

  .project-header { margin-bottom: 0.25em; font-size: 0.85em; }
  .project-desc { color: #64748b; margin-left: 0.5em; }

  .results-header { display: flex; justify-content: space-between; align-items: center; font-size: 0.8em; }
  .result-count { color: #64748b; }
  .bulk-actions { display: flex; gap: 0.35em; }

  .btn-sm { padding: 0.25em 0.6em; font-size: 0.8em; background: #f1f5f9; border: 1px solid #d1d5db; border-radius: 4px; cursor: pointer; }
  .btn-sm:hover:not(:disabled) { background: #e2e8f0; }
  .btn-sm:disabled { opacity: 0.5; cursor: not-allowed; }

  .results-grid { display: flex; flex-direction: column; gap: 0.4em; max-height: 340px; overflow-y: auto; }

  .pagination { display: flex; align-items: center; justify-content: center; gap: 0.75em; font-size: 0.8em; }
  .page-info { color: #64748b; }

  .empty { text-align: center; color: #94a3b8; font-size: 0.9em; }

  .selection-tray {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6em 0.75em;
    background: #f0f7ff;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    font-size: 0.85em;
  }
</style>
