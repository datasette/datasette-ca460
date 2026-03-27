<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { models as fetchModels, processDocument, syncEvents } from './api';
  import DocumentCloudBrowser from './DocumentCloudBrowser.svelte';

  import { ensureFilePickerLoaded } from './datasette-files';

  interface Props {
    database: string;
    open: boolean;
    onclose: () => void;
  }

  let { database, open = $bindable(), onclose }: Props = $props();

  let dialogEl: HTMLDialogElement | null = $state(null);

  type Tab = 'upload' | 'documentcloud';
  let activeTab: Tab = $state('upload');

  // Shared
  let pageTypeModel = $state('');
  let parserModel = $state('');
  let availableModels: string[] = $state([]);
  let loadingModels = $state(true);
  let error: string | null = $state(null);

  // Upload
  let selectedFileId: string | null = $state(null);
  let selectedFileName: string | null = $state(null);
  let processing = $state(false);

  // DocumentCloud sync progress (shared between DC browser import and legacy)
  let syncJobId: string | null = $state(null);
  let syncStatus: string | null = $state(null);
  let syncEvents_: { type: string; message: string }[] = $state([]);
  let pollInterval: ReturnType<typeof setInterval> | null = null;

  let eventsEl: HTMLElement | null = $state(null);
  $effect(() => { if (eventsEl && syncEvents_.length > 0) eventsEl.scrollTop = eventsEl.scrollHeight; });

  onMount(() => { loadModels(); });
  onDestroy(() => { if (pollInterval) clearInterval(pollInterval); });

  $effect(() => {
    if (!dialogEl) return;
    if (open && !dialogEl.open) dialogEl.showModal();
    else if (!open && dialogEl.open) dialogEl.close();
  });

  async function loadModels() {
    loadingModels = true;
    try {
      const { data, error: err, response } = await fetchModels(database);
      if (err || !response.ok) return;
      const d = data as any;
      availableModels = d.models || [];
      if (availableModels.length > 0) {
        pageTypeModel = availableModels[0];
        parserModel = availableModels[0];
      }
    } catch (e) { /* ignore */ }
    finally { loadingModels = false; }
  }

  // --- File picker ---

  function openFilePicker() {
    ensureFilePickerLoaded();
    const picker = document.createElement('datasette-file-picker');
    picker.addEventListener('file-selected', (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail && detail.fileId) {
        selectedFileId = detail.fileId;
        selectedFileName = detail.fileId;
        error = null;
      }
    });
    document.body.appendChild(picker);
  }

  function clearFile() { selectedFileId = null; selectedFileName = null; error = null; }

  async function handleProcess() {
    if (!selectedFileId) return;
    processing = true;
    error = null;

    try {
      const { data, error: processErr } = await processDocument(database, {
        file_id: selectedFileId,
        page_type_model: pageTypeModel,
        parser_model: parserModel,
      });

      if (processErr || !data) { error = (processErr as any)?.error || 'Processing failed'; return; }

      const d = data as any;
      window.location.href = `/${database}/-/ca460/document/${d.document_id}?sync_job_id=${d.sync_job_id}`;
    } catch (e) {
      error = 'Processing failed';
    } finally {
      processing = false;
    }
  }

  // --- DocumentCloud import job tracking ---

  function handleDcJobStarted(jobId: string) {
    syncJobId = jobId;
    syncStatus = 'running';
    startPolling();
  }

  function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollSyncEvents();
    pollInterval = setInterval(pollSyncEvents, 1000);
  }

  async function pollSyncEvents() {
    if (!syncJobId) return;
    try {
      const { data, error: err, response } = await syncEvents(database, syncJobId);
      if (err || !response.ok) return;
      const d = data as any;
      syncStatus = d.job.status;
      syncEvents_ = d.events;
      if (d.job.status === 'completed' || d.job.status === 'failed') {
        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
      }
    } catch (e) { /* ignore */ }
  }

  // --- Dialog ---

  function handleDialogClose() { open = false; onclose(); }
  function handleBackdropClick(e: MouseEvent) { if (e.target === dialogEl) handleDialogClose(); }
</script>

<dialog bind:this={dialogEl} onclose={handleDialogClose} onclick={handleBackdropClick}>
  <div class="dialog-content">
    <div class="dialog-header">
      <h2>Import Documents</h2>
      <button class="close-btn" onclick={handleDialogClose}>&times;</button>
    </div>

    <div class="tabs">
      <button class="tab" class:active={activeTab === 'upload'} onclick={() => activeTab = 'upload'}>Pick File</button>
      <button class="tab" class:active={activeTab === 'documentcloud'} onclick={() => activeTab = 'documentcloud'}>DocumentCloud</button>
    </div>

    {#if activeTab === 'upload'}
      {#if error}
        <div class="error-msg">{error}</div>
      {/if}

      {#if !selectedFileId}
        <div class="picker-container">
          <button class="btn-primary" onclick={openFilePicker}>Select or upload a PDF</button>
        </div>
      {:else}
        <div class="selected-file">
          <div class="file-info">
            <strong>{selectedFileName}</strong>
            <span class="file-id">{selectedFileId}</span>
          </div>
          <button class="btn-secondary btn-sm" onclick={clearFile}>Change</button>
        </div>

        <div class="model-row">
          <div class="model-field">
            <label for="upload-ptm">Classifier:</label>
            <select id="upload-ptm" bind:value={pageTypeModel} disabled={loadingModels}>
              {#each availableModels as m}<option value={m}>{m}</option>{/each}
            </select>
          </div>
          <div class="model-field">
            <label for="upload-pm">Parser:</label>
            <select id="upload-pm" bind:value={parserModel} disabled={loadingModels}>
              {#each availableModels as m}<option value={m}>{m}</option>{/each}
            </select>
          </div>
        </div>

        <div class="actions">
          <button class="btn-primary" onclick={handleProcess} disabled={processing || loadingModels}>
            {processing ? 'Processing...' : 'Process Document'}
          </button>
          <button class="btn-secondary" onclick={clearFile} disabled={processing}>Clear</button>
        </div>
      {/if}

    {:else}
      {#if !syncJobId}
        <div class="model-row dc-models">
          <div class="model-field">
            <label for="dc-ptm">Classifier:</label>
            <select id="dc-ptm" bind:value={pageTypeModel} disabled={loadingModels}>
              {#each availableModels as m}<option value={m}>{m}</option>{/each}
            </select>
          </div>
          <div class="model-field">
            <label for="dc-pm">Parser:</label>
            <select id="dc-pm" bind:value={parserModel} disabled={loadingModels}>
              {#each availableModels as m}<option value={m}>{m}</option>{/each}
            </select>
          </div>
        </div>

        <DocumentCloudBrowser
          {database}
          {pageTypeModel}
          {parserModel}
          onJobStarted={handleDcJobStarted}
        />
      {:else}
        <div class="sync-progress">
          <div class="sync-status">
            <span>Status:</span>
            <span class="badge badge-{syncStatus}">{syncStatus}</span>
          </div>
          <div class="events-log" bind:this={eventsEl}>
            {#each syncEvents_ as evt}
              <div class="event event-{evt.type}">{evt.message}</div>
            {/each}
          </div>
          {#if syncStatus === 'completed'}
            <div class="sync-done">
              Sync complete. <button class="btn-link" onclick={() => { handleDialogClose(); window.location.reload(); }}>Refresh to see documents</button>
            </div>
          {/if}
        </div>
      {/if}
    {/if}
  </div>
</dialog>

<style>
  dialog { border: none; border-radius: 12px; padding: 0; max-width: 720px; width: 90vw; box-shadow: 0 20px 60px rgba(0,0,0,0.2); }
  dialog::backdrop { background: rgba(0,0,0,0.4); }

  .dialog-content { padding: 1.5em; }
  .dialog-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1em; }
  .dialog-header h2 { margin: 0; font-size: 1.15em; }
  .close-btn { background: none; border: none; font-size: 1.5em; cursor: pointer; color: #94a3b8; padding: 0 0.2em; line-height: 1; }
  .close-btn:hover { color: #475569; }

  .tabs { display: flex; gap: 0; border-bottom: 2px solid #e2e8f0; margin-bottom: 1.25em; }
  .tab { padding: 0.5em 1em; background: none; border: 2px solid transparent; border-bottom: none; border-radius: 4px 4px 0 0; cursor: pointer; font-size: 0.9em; color: #64748b; margin-bottom: -2px; }
  .tab:hover { color: #334155; background: #f8fafc; }
  .tab.active { color: #334155; border-color: #e2e8f0; background: white; font-weight: 600; }

  .error-msg { padding: 0.6em 0.8em; background: #fee2e2; color: #991b1b; border-radius: 6px; margin-bottom: 1em; font-size: 0.9em; }

  .picker-container { margin-top: 0.5em; }
  .picker-hint { color: #64748b; font-size: 0.9em; margin: 0 0 0.75em 0; }

  .selected-file { display: flex; align-items: center; justify-content: space-between; padding: 0.75em 1em; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; }
  .file-info { display: flex; flex-direction: column; gap: 0.1em; }
  .file-id { font-size: 0.8em; color: #64748b; font-family: monospace; }

  .model-row { display: flex; gap: 1em; margin-top: 1.25em; }
  .dc-models { margin-top: 0; margin-bottom: 1em; }
  .model-field { flex: 1; }
  .model-field label { display: block; font-size: 0.8em; color: #64748b; margin-bottom: 0.25em; }
  .model-field select { width: 100%; padding: 0.35em 0.5em; font-size: 0.85em; border: 1px solid #d1d5db; border-radius: 4px; }

  .actions { display: flex; gap: 0.5em; margin-top: 1.25em; }
  .btn-primary { padding: 0.6em 1.2em; background: #0066cc; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9em; }
  .btn-primary:hover:not(:disabled) { background: #0052a3; }
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn-secondary { padding: 0.6em 1.2em; background: #f1f5f9; color: #475569; border: 1px solid #d1d5db; border-radius: 6px; cursor: pointer; font-size: 0.9em; }
  .btn-secondary:hover:not(:disabled) { background: #e2e8f0; }
  .btn-sm { padding: 0.3em 0.7em; font-size: 0.82em; }

  .sync-progress { margin-top: 0.5em; }
  .sync-status { display: flex; align-items: center; gap: 0.5em; margin-bottom: 0.5em; font-size: 0.9em; }
  .badge { padding: 0.15em 0.5em; border-radius: 3px; font-size: 0.85em; font-weight: 600; }
  .badge-running { background: #fef3c7; color: #92400e; }
  .badge-completed { background: #d1fae5; color: #065f46; }
  .badge-failed { background: #fee2e2; color: #991b1b; }
  .events-log { max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.78em; line-height: 1.6; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 0.5em; }
  .event-info { color: #475569; }
  .event-warning { color: #92400e; }
  .event-error { color: #991b1b; font-weight: 600; }
  .event-success { color: #065f46; font-weight: 600; }
  .sync-done { margin-top: 0.75em; font-size: 0.9em; color: #065f46; }
  .btn-link { background: none; border: none; color: #0066cc; cursor: pointer; text-decoration: underline; font-size: inherit; padding: 0; }
</style>
