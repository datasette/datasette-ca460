<script lang="ts">
  interface Props {
    doc: any;
    onBack: () => void;
    onImport: (docId: number) => void;
  }

  let { doc, onBack, onImport }: Props = $props();

  function pageUrl(pageNum: number, size = 'small'): string {
    if (!doc.asset_url || !doc.slug) return '';
    return `${doc.asset_url}documents/${doc.id}/pages/${doc.slug}-p${pageNum}-${size}.gif`;
  }

  let pages = $derived(
    Array.from({ length: doc.page_count || 0 }, (_, i) => i + 1)
  );
</script>

<div class="preview">
  <div class="preview-header">
    <button class="back-btn" onclick={onBack}>&larr; Back</button>
    <button class="btn-primary" onclick={() => onImport(doc.id)}>Import this document</button>
  </div>

  <h3 class="preview-title">{doc.title || `Document ${doc.id}`}</h3>

  {#if doc.source}
    <div class="preview-meta">Source: {doc.source}</div>
  {/if}
  {#if doc.description}
    <p class="preview-desc">{doc.description}</p>
  {/if}
  <div class="preview-meta">{doc.page_count || 0} pages</div>

  {#if pages.length > 0}
    <div class="page-grid">
      {#each pages as p}
        <div class="page-thumb">
          <img src={pageUrl(p)} alt="Page {p}" loading="lazy" />
          <span class="page-label">{p}</span>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .preview { padding: 0; }
  .preview-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75em; }
  .back-btn { background: none; border: none; cursor: pointer; color: #0066cc; font-size: 0.9em; padding: 0; }
  .back-btn:hover { text-decoration: underline; }
  .btn-primary { padding: 0.5em 1em; background: #0066cc; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85em; }
  .btn-primary:hover { background: #0052a3; }

  .preview-title { margin: 0 0 0.25em; font-size: 1em; }
  .preview-meta { font-size: 0.8em; color: #64748b; margin-bottom: 0.25em; }
  .preview-desc { font-size: 0.85em; color: #475569; margin: 0.5em 0; }

  .page-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
    gap: 0.5em;
    margin-top: 0.75em;
    max-height: 280px;
    overflow-y: auto;
  }
  .page-thumb {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.2em;
  }
  .page-thumb img {
    width: 100%;
    border-radius: 3px;
    border: 1px solid #e2e8f0;
  }
  .page-label { font-size: 0.7em; color: #94a3b8; }
</style>
