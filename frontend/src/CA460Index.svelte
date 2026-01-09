<script lang="ts">
  import { onMount } from 'svelte';
  import DevBadge from './DevBadge.svelte';
  import { documents as fetchDocuments } from './api';

  const database = 'tmp';

  interface Document {
    id: number;
    page_count: number;
    title: string | null;
    model_count: number;
  }

  interface ParsedPage {
    page_number: number;
    page_type: string;
    parsed_data: Record<string, unknown>;
    timing: Record<string, unknown>;
    created_at: string;
  }

  interface DocumentData {
    document: {
      id: number;
      page_count: number;
      title: string;
    };
    models: Record<string, ParsedPage[]>;
  }

  let documents: Document[] = $state([]);
  let selectedDocumentId: string = $state('');
  let documentData: DocumentData | null = $state(null);
  let loading = $state(false);
  let loadingDocuments = $state(true);

  // Diff navigation state per model
  let diffElements: Record<string, { element: HTMLElement; id: string }[]> = $state({});
  let currentDiffIndex: Record<string, number> = $state({});

  onMount(() => {
    loadDocuments();
  });

  async function loadDocuments() {
    loadingDocuments = true;
    try {
      const { data } = await fetchDocuments(database);
      if (data) {
        documents = data.documents;
      }
    } catch (error) {
      console.error('Error loading documents:', error);
    } finally {
      loadingDocuments = false;
    }
  }

  async function loadDocumentParsed(documentId: string) {
    if (!documentId) {
      documentData = null;
      return;
    }

    loading = true;
    diffElements = {};
    currentDiffIndex = {};

    try {
      const response = await fetch(`/${database}/-/ca460/api/document/${documentId}/parsed`);
      const data = await response.json();

      if (data.error) {
        console.error(data.error);
        documentData = null;
        return;
      }

      documentData = data;

      // Initialize diff tracking for each model
      const modelNames = Object.keys(data.models);
      for (const modelName of modelNames) {
        diffElements[modelName] = [];
        currentDiffIndex[modelName] = -1;
      }
    } catch (error) {
      console.error('Error loading document:', error);
      documentData = null;
    } finally {
      loading = false;
    }
  }

  function handleDocumentChange(e: Event) {
    const target = e.target as HTMLSelectElement;
    selectedDocumentId = target.value;
    loadDocumentParsed(selectedDocumentId);
  }

  function formatPageType(pageType: string): string {
    return pageType
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  }

  function formatFieldName(name: string): string {
    return name
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  }

  function formatValue(value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  function checkDiff(
    fieldKey: string,
    fieldValue: unknown,
    currentModel: string,
    pageNumber: number,
    pageType: string
  ): boolean {
    if (!documentData || Object.keys(documentData.models).length < 2) return false;

    for (const otherModel of Object.keys(documentData.models)) {
      if (otherModel === currentModel) continue;

      const otherPages = documentData.models[otherModel] || [];
      const otherPage = otherPages.find(
        p => p.page_number === pageNumber && p.page_type === pageType
      );

      if (!otherPage) return true;

      const otherValue = otherPage.parsed_data?.[fieldKey];
      if (JSON.stringify(fieldValue) !== JSON.stringify(otherValue)) {
        return true;
      }
    }

    return false;
  }

  function checkLineItemDiff(
    itemIndex: number,
    fieldKey: string,
    fieldValue: unknown,
    currentModel: string,
    pageNumber: number,
    pageType: string
  ): boolean {
    if (!documentData || Object.keys(documentData.models).length < 2) return false;

    for (const otherModel of Object.keys(documentData.models)) {
      if (otherModel === currentModel) continue;

      const otherPages = documentData.models[otherModel] || [];
      const otherPage = otherPages.find(
        p => p.page_number === pageNumber && p.page_type === pageType
      );

      if (!otherPage || !otherPage.parsed_data?.line_items) return true;

      const lineItems = otherPage.parsed_data.line_items as Record<string, unknown>[];
      const otherItem = lineItems[itemIndex];
      if (!otherItem) return true;

      const otherValue = otherItem[fieldKey];
      if (JSON.stringify(fieldValue) !== JSON.stringify(otherValue)) {
        return true;
      }
    }

    return false;
  }

  function registerDiff(modelName: string, element: HTMLElement, id: string) {
    if (!diffElements[modelName]) {
      diffElements[modelName] = [];
    }
    diffElements[modelName].push({ element, id });
  }

  // Svelte action for registering diff elements
  function registerDiffElement(node: HTMLElement, params: { modelName: string; diffId: string; hasDiff: boolean }) {
    if (params.hasDiff) {
      registerDiff(params.modelName, node, params.diffId);
    }
    return {
      destroy() {
        // Cleanup if needed
      }
    };
  }

  function getDiffCount(modelName: string): number {
    return diffElements[modelName]?.length || 0;
  }

  function navigateDiff(modelName: string, direction: number) {
    const diffs = diffElements[modelName] || [];
    if (diffs.length === 0) return;

    // Remove current highlight from all panels
    for (const model of Object.keys(diffElements)) {
      const currentIdx = currentDiffIndex[model];
      if (currentIdx >= 0 && diffElements[model][currentIdx]) {
        diffElements[model][currentIdx].element.classList.remove('current-diff');
      }
    }

    // Calculate new index
    let newIndex = (currentDiffIndex[modelName] ?? -1) + direction;
    if (newIndex < 0) newIndex = diffs.length - 1;
    if (newIndex >= diffs.length) newIndex = 0;

    currentDiffIndex[modelName] = newIndex;

    const currentDiff = diffs[newIndex];
    const diffId = currentDiff.id;

    // Highlight and scroll in current panel
    currentDiff.element.classList.add('current-diff');
    scrollToElement(modelName, currentDiff.element);

    // Find and scroll to matching diff in other panels
    for (const otherModel of Object.keys(diffElements)) {
      if (otherModel === modelName) continue;

      const otherDiffs = diffElements[otherModel];
      const matchingIdx = otherDiffs.findIndex(d => d.id === diffId);

      if (matchingIdx >= 0) {
        currentDiffIndex[otherModel] = matchingIdx;
        otherDiffs[matchingIdx].element.classList.add('current-diff');
        scrollToElement(otherModel, otherDiffs[matchingIdx].element);
      }
    }
  }

  function scrollToElement(modelName: string, element: HTMLElement) {
    const contentId = `content-${modelName.replace(/[^a-zA-Z0-9]/g, '_')}`;
    const content = document.getElementById(contentId);
    if (!content) return;

    const elementRect = element.getBoundingClientRect();
    const contentRect = content.getBoundingClientRect();

    const scrollTop = element.offsetTop - content.offsetTop - (contentRect.height / 2) + (elementRect.height / 2);
    content.scrollTo({ top: scrollTop, behavior: 'smooth' });
  }

  function getRegularFields(data: Record<string, unknown>): [string, unknown][] {
    return Object.entries(data).filter(([key]) => key !== 'line_items');
  }

  function getLineItems(data: Record<string, unknown>): Record<string, unknown>[] | null {
    const items = data.line_items;
    if (Array.isArray(items)) return items;
    return null;
  }

  function getNonEmptyFields(item: Record<string, unknown>): [string, unknown][] {
    return Object.entries(item).filter(([, value]) => 
      value !== null && value !== undefined && value !== ''
    );
  }
</script>

<main>
  <h1>CA Form 460 <DevBadge /></h1>
  <p>California Form 460 campaign finance document parsing for <strong>{database}</strong>.</p>

  <nav class="ca460-nav">
    <a href="/{database}/-/ca460/sync" class="nav-link">Sync Documents</a>
  </nav>

  <section class="document-selector">
    <h2>Compare Model Parsing</h2>
    <p>Select a document to compare how different models parsed it.</p>

    <div class="form-group">
      <label for="document-select">Document:</label>
      <select id="document-select" onchange={handleDocumentChange} value={selectedDocumentId}>
        {#if loadingDocuments}
          <option value="">Loading documents...</option>
        {:else if documents.length === 0}
          <option value="">No documents found</option>
        {:else}
          <option value="">Select a document...</option>
          {#each documents as doc}
            <option value={doc.id}>
              {doc.title || 'Document ' + doc.id} - {doc.page_count} pages ({doc.model_count} model{doc.model_count !== 1 ? 's' : ''})
            </option>
          {/each}
        {/if}
      </select>
    </div>
  </section>

  {#if selectedDocumentId}
    <section class="comparison-container">
      <h2>
        {#if documentData}
          Comparison: {documentData.document.title}
        {:else}
          Document Comparison
        {/if}
      </h2>

      {#if loading}
        <div class="loading">Loading parsed data...</div>
      {:else if documentData}
        {#if Object.keys(documentData.models).length === 1}
          <div class="message-info">
            <p>This document has only been parsed by one model. Add more models to compare.</p>
          </div>
        {/if}

        <div class="diff-container">
          {#each Object.entries(documentData.models) as [modelName, pages]}
            <div class="model-panel" data-model={modelName}>
              <div class="model-panel-header">
                <span class="model-name">{modelName}</span>
                <div class="diff-nav">
                  {#if getDiffCount(modelName) > 0}
                    <span class="diff-count">{getDiffCount(modelName)} diff{getDiffCount(modelName) !== 1 ? 's' : ''}</span>
                    <button class="diff-nav-btn" onclick={() => navigateDiff(modelName, -1)} title="Previous difference">↑</button>
                    <span>{(currentDiffIndex[modelName] ?? -1) + 1}/{getDiffCount(modelName)}</span>
                    <button class="diff-nav-btn" onclick={() => navigateDiff(modelName, 1)} title="Next difference">↓</button>
                  {:else}
                    <span class="diff-count no-diffs">No diffs</span>
                  {/if}
                </div>
              </div>

              <div class="model-panel-content" id={`content-${modelName.replace(/[^a-zA-Z0-9]/g, '_')}`}>
                {#each pages as page}
                  <div class="page-section" data-page-number={page.page_number} data-page-type={page.page_type}>
                    <div class="page-header">
                      Page {page.page_number}: {formatPageType(page.page_type)}
                    </div>

                    {#each getRegularFields(page.parsed_data || {}) as [key, value]}
                      {@const hasDiff = checkDiff(key, value, modelName, page.page_number, page.page_type)}
                      {@const diffId = `page${page.page_number}_${page.page_type}_field_${key}`}
                      <div
                        class="field-row"
                        class:diff-highlight={hasDiff}
                        data-diff-id={diffId}
                        use:registerDiffElement={{ modelName, diffId, hasDiff }}
                      >
                        <span class="field-name">{formatFieldName(key)}</span>
                        <span class="field-value">{formatValue(value)}</span>
                      </div>
                    {/each}

                    {#if getLineItems(page.parsed_data || {})}
                      {@const lineItems = getLineItems(page.parsed_data || {})!}
                      <div class="line-items-section">
                        <div class="field-name" style="margin-top: 0.5em; margin-bottom: 0.5em;">
                          Line Items ({lineItems?.length}):
                        </div>
                        {#each lineItems as item, index}
                          <div class="line-item">
                            <div class="line-item-header">Item {index + 1}</div>
                            {#each getNonEmptyFields(item) as [key, value]}
                              {@const hasDiff = checkLineItemDiff(index, key, value, modelName, page.page_number, page.page_type)}
                              {@const diffId = `page${page.page_number}_${page.page_type}_lineitem_${index}_field_${key}`}
                              <div
                                class="field-row"
                                class:diff-highlight={hasDiff}
                                data-diff-id={diffId}
                                use:registerDiffElement={{ modelName, diffId, hasDiff }}
                              >
                                <span class="field-name">{formatFieldName(key)}</span>
                                <span class="field-value">{formatValue(value)}</span>
                              </div>
                            {/each}
                          </div>
                        {/each}
                      </div>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>
  {/if}
</main>

<style>
  .ca460-nav {
    margin: 1.5em 0;
    padding: 1em;
    background: #f8f9fa;
    border-radius: 4px;
  }

  .nav-link {
    display: inline-block;
    padding: 0.5em 1em;
    background: #0066cc;
    color: white !important;
    text-decoration: none;
    border-radius: 4px;
    margin-right: 0.5em;
  }

  .nav-link:hover {
    background: #0052a3;
    color: white !important;
  }

  .document-selector {
    margin: 2em 0;
  }

  .form-group {
    margin-bottom: 1em;
  }

  .form-group label {
    display: block;
    font-weight: bold;
    margin-bottom: 0.25em;
  }

  .form-group select {
    width: 100%;
    max-width: 600px;
    padding: 0.5em;
    font-size: 1em;
  }

  .comparison-container {
    margin-top: 2em;
  }

  .message-info {
    padding: 1em;
    background: #e7f3ff;
    border: 1px solid #b3d7ff;
    color: #004085;
    border-radius: 4px;
    margin-bottom: 1em;
  }

  .diff-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 1em;
  }

  .model-panel {
    border: 1px solid #dee2e6;
    border-radius: 4px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .model-panel-header {
    padding: 0.75em 1em;
    background: #f8f9fa;
    border-bottom: 1px solid #dee2e6;
    font-weight: bold;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5em;
  }

  .model-panel-header .model-name {
    flex: 1;
  }

  .diff-nav {
    display: flex;
    align-items: center;
    gap: 0.5em;
    font-size: 0.85em;
    font-weight: normal;
  }

  .diff-count {
    color: #856404;
    background: #fff3cd;
    padding: 0.25em 0.5em;
    border-radius: 3px;
  }

  .diff-count.no-diffs {
    color: #155724;
    background: #d4edda;
  }

  .diff-nav-btn {
    padding: 0.25em 0.5em;
    background: #e9ecef;
    border: 1px solid #dee2e6;
    border-radius: 3px;
    cursor: pointer;
    font-size: 1em;
    line-height: 1;
  }

  .diff-nav-btn:hover:not(:disabled) {
    background: #dee2e6;
  }

  .diff-nav-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .model-panel-content {
    padding: 1em;
    max-height: 600px;
    overflow-y: auto;
    font-family: monospace;
    font-size: 0.85em;
    background: #fefefe;
    flex: 1;
  }

  .page-section {
    margin-bottom: 1.5em;
    padding-bottom: 1em;
    border-bottom: 1px solid #eee;
  }

  .page-section:last-child {
    border-bottom: none;
    margin-bottom: 0;
  }

  .page-header {
    font-weight: bold;
    color: #333;
    margin-bottom: 0.5em;
    background: #f0f0f0;
    padding: 0.25em 0.5em;
    border-radius: 2px;
  }

  .field-row {
    display: flex;
    padding: 0.15em 0;
    border-bottom: 1px dotted #eee;
  }

  .field-row:last-child {
    border-bottom: none;
  }

  .field-name {
    flex: 0 0 40%;
    color: #666;
    font-size: 0.9em;
  }

  .field-value {
    flex: 1;
    word-break: break-word;
  }

  .field-row.diff-highlight {
    background: #fff3cd;
    margin: 0 -0.5em;
    padding: 0.15em 0.5em;
    border-radius: 2px;
  }

  :global(.field-row.diff-highlight.current-diff) {
    background: #ffc107;
    outline: 2px solid #e0a800;
  }

  .line-items-section {
    margin-top: 0.5em;
  }

  .line-item {
    margin-bottom: 0.75em;
    padding: 0.5em;
    background: #f9f9f9;
    border-radius: 4px;
    border-left: 3px solid #0066cc;
  }

  .line-item-header {
    font-weight: bold;
    color: #0066cc;
    margin-bottom: 0.25em;
  }

  .loading {
    text-align: center;
    padding: 2em;
    color: #666;
  }
</style>
