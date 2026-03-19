<script lang="ts">
  interface Props {
    doc: any;
    selected: boolean;
    onToggle: (id: number) => void;
    onPreview: (doc: any) => void;
  }

  let { doc, selected, onToggle, onPreview }: Props = $props();

  function thumbnailUrl(doc: any): string {
    if (!doc.asset_url || !doc.slug) return '';
    return `${doc.asset_url}documents/${doc.id}/pages/${doc.slug}-p1-small.gif`;
  }
</script>

<div class="card" class:card-selected={selected}>
  <label class="card-checkbox">
    <input
      type="checkbox"
      checked={selected}
      onchange={() => onToggle(doc.id)}
    />
  </label>

  <button class="card-body" onclick={() => onPreview(doc)}>
    <div class="thumb">
      {#if thumbnailUrl(doc)}
        <img src={thumbnailUrl(doc)} alt="" loading="lazy" />
      {:else}
        <div class="thumb-placeholder">?</div>
      {/if}
    </div>
    <div class="meta">
      <div class="title">{doc.title || `Document ${doc.id}`}</div>
      <div class="details">
        {#if doc.page_count}<span>{doc.page_count} pages</span>{/if}
        {#if doc.source}<span class="source">{doc.source}</span>{/if}
      </div>
    </div>
  </button>
</div>

<style>
  .card {
    display: flex;
    align-items: flex-start;
    gap: 0.5em;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 0.5em;
    transition: border-color 0.15s;
  }
  .card:hover { border-color: #94a3b8; }
  .card-selected { border-color: #0066cc; background: #f0f7ff; }

  .card-checkbox { flex-shrink: 0; padding-top: 0.15em; }
  .card-checkbox input { cursor: pointer; }

  .card-body {
    display: flex;
    gap: 0.6em;
    flex: 1;
    background: none;
    border: none;
    padding: 0;
    text-align: left;
    cursor: pointer;
    font: inherit;
    color: inherit;
  }

  .thumb { width: 48px; height: 62px; flex-shrink: 0; border-radius: 3px; overflow: hidden; background: #f1f5f9; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; }
  .thumb-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: #94a3b8; font-size: 1.2em; }

  .meta { flex: 1; min-width: 0; }
  .title { font-size: 0.85em; font-weight: 600; color: #1e293b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .details { font-size: 0.75em; color: #64748b; display: flex; gap: 0.5em; margin-top: 0.15em; }
  .source { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 150px; }
</style>
