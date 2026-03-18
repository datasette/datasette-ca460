<script lang="ts">
  import { onMount } from 'svelte';
  import DevBadge from './DevBadge.svelte';
  import { documents as fetchDocuments } from './api';
  import { getDatabaseFromUrl } from './utils';

  const database = getDatabaseFromUrl();

  interface Document {
    id: number;
    source: string;
    page_count: number;
    title: string | null;
    filer_name: string | null;
    period_from: string | null;
    period_through: string | null;
    pages_classified: number;
    pages_parsed: number;
    model_count: number;
  }

  let documents: Document[] = $state([]);
  let loading = $state(true);

  onMount(() => {
    loadDocuments();
  });

  async function loadDocuments() {
    loading = true;
    try {
      const { data } = await fetchDocuments(database);
      if (data) {
        documents = data.documents;
      }
    } catch (error) {
      console.error('Error loading documents:', error);
    } finally {
      loading = false;
    }
  }

  function friendlyDate(d: string): string {
    const date = new Date(d + 'T00:00:00');
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function periodLabel(doc: Document): string | null {
    if (!doc.period_from || !doc.period_through) return null;
    return `${friendlyDate(doc.period_from)} \u2013 ${friendlyDate(doc.period_through)}`;
  }

  function getStatus(doc: Document): { label: string; cls: string } {
    if (doc.pages_parsed > 0 && doc.pages_parsed >= doc.pages_classified) {
      return { label: 'Complete', cls: 'status-complete' };
    }
    if (doc.pages_classified > 0 || doc.pages_parsed > 0) {
      return { label: 'In Progress', cls: 'status-in-progress' };
    }
    return { label: 'Pending', cls: 'status-pending' };
  }
</script>

<main>
  <h1>CA Form 460 <DevBadge /></h1>
  <p>California Form 460 campaign finance documents in <strong>{database}</strong>.</p>

  <nav class="ca460-nav">
    <a href="/{database}/-/ca460/sync" class="nav-link">Sync / Upload</a>
  </nav>

  {#if loading}
    <div class="loading">Loading documents...</div>
  {:else if documents.length === 0}
    <div class="empty">
      <p>No documents yet. <a href="/{database}/-/ca460/sync">Upload a PDF or sync from DocumentCloud</a> to get started.</p>
    </div>
  {:else}
    <table class="documents-table">
      <thead>
        <tr>
          <th>Filer</th>
          <th>Period</th>
          <th>Document</th>
          <th>Source</th>
          <th>Pages</th>
          <th>Parsed</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {#each documents as doc}
          {@const status = getStatus(doc)}
          <tr>
            <td>
              {#if doc.filer_name}
                <a href="/{database}/-/ca460/document/{doc.id}" class="doc-link">{doc.filer_name}</a>
              {:else}
                <span class="muted">&mdash;</span>
              {/if}
            </td>
            <td class="nowrap">
              {#if periodLabel(doc)}
                {periodLabel(doc)}
              {:else}
                <span class="muted">&mdash;</span>
              {/if}
            </td>
            <td>
              <a href="/{database}/-/ca460/document/{doc.id}" class="doc-link secondary">
                {doc.title || `Document ${doc.id}`}
              </a>
            </td>
            <td><span class="source-badge source-{doc.source}">{doc.source}</span></td>
            <td class="num">{doc.page_count}</td>
            <td class="num">{doc.pages_parsed} / {doc.page_count}</td>
            <td><span class="status-badge {status.cls}">{status.label}</span></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</main>

<style>
  .ca460-nav {
    margin: 1em 0;
  }

  .nav-link {
    display: inline-block;
    padding: 0.5em 1em;
    background: #0066cc;
    color: white !important;
    text-decoration: none;
    border-radius: 4px;
  }

  .nav-link:hover {
    background: #0052a3;
    color: white !important;
  }

  .loading {
    text-align: center;
    padding: 2em;
    color: #666;
  }

  .empty {
    padding: 2em;
    text-align: center;
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 4px;
  }

  .empty a {
    color: #0066cc;
  }

  .documents-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 1em;
  }

  .documents-table th,
  .documents-table td {
    padding: 0.6em 0.8em;
    text-align: left;
    border-bottom: 1px solid #dee2e6;
  }

  .documents-table th {
    background: #f8f9fa;
    font-weight: 600;
    font-size: 0.9em;
    color: #555;
  }

  .documents-table tbody tr:hover {
    background: #f8f9fa;
  }

  .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .doc-link {
    color: #0066cc;
    text-decoration: none;
    font-weight: 500;
  }

  .doc-link:hover {
    text-decoration: underline;
  }

  .doc-link.secondary {
    color: #64748b;
    font-weight: normal;
    font-size: 0.9em;
  }

  .nowrap { white-space: nowrap; }
  .muted { color: #94a3b8; }

  .source-badge {
    display: inline-block;
    padding: 0.15em 0.5em;
    border-radius: 3px;
    font-size: 0.8em;
  }

  .source-upload {
    background: #e7f3ff;
    color: #004085;
  }

  .source-documentcloud {
    background: #f0e6ff;
    color: #4a1d8e;
  }

  .status-badge {
    display: inline-block;
    padding: 0.2em 0.6em;
    border-radius: 3px;
    font-size: 0.85em;
    font-weight: 500;
  }

  .status-complete {
    background: #d4edda;
    color: #155724;
  }

  .status-in-progress {
    background: #fff3cd;
    color: #856404;
  }

  .status-pending {
    background: #e9ecef;
    color: #6c757d;
  }
</style>
