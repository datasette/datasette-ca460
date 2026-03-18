<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { models as fetchModels, uploadPdf, processDocument, sync, syncEvents } from './api';

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
  let selectedFile: File | null = $state(null);
  let dragging = $state(false);
  let uploading = $state(false);

  // DocumentCloud
  let projectId = $state('');
  let submitting = $state(false);
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

  // --- Upload ---

  function handleDragOver(e: DragEvent) { e.preventDefault(); dragging = true; }
  function handleDragLeave(e: DragEvent) { e.preventDefault(); dragging = false; }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    const file = e.dataTransfer?.files?.[0];
    if (file && (file.type === 'application/pdf' || file.name.endsWith('.pdf'))) {
      selectedFile = file; error = null;
    } else {
      error = 'Please drop a PDF file';
    }
  }

  function handleFileInput(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files?.[0]) { selectedFile = input.files[0]; error = null; }
  }

  function clearFile() { selectedFile = null; error = null; }

  function formatFileSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  async function handleUpload() {
    if (!selectedFile) return;
    uploading = true;
    error = null;

    try {
      const { data, error: uploadErr } = await uploadPdf(database, selectedFile);
      if (uploadErr || !data) { error = (uploadErr as any)?.error || 'Upload failed'; return; }

      const { data: processData, error: processErr } = await processDocument(database, {
        document_id: data.document_id,
        page_type_model: pageTypeModel,
        parser_model: parserModel,
      });

      if (processErr || !processData) { error = 'Uploaded but failed to start processing'; return; }

      const jobId = (processData as any).sync_job_id;
      window.location.href = `/${database}/-/ca460/document/${data.document_id}?sync_job_id=${jobId}`;
    } catch (e) {
      error = 'Upload failed';
    } finally {
      uploading = false;
    }
  }

  // --- DocumentCloud ---

  async function handleSync(e: Event) {
    e.preventDefault();
    if (!projectId) { error = 'Enter a project ID'; return; }
    const pid = parseInt(projectId, 10);
    if (isNaN(pid)) { error = 'Project ID must be a number'; return; }

    submitting = true;
    error = null;
    syncJobId = null;
    syncStatus = null;
    syncEvents_ = [];

    try {
      const { data, error: syncErr } = await sync(database, {
        project_id: pid,
        page_type_model: pageTypeModel,
        parser_model: parserModel,
      });

      if (syncErr || !data) { error = (syncErr as any) || 'Failed to start sync'; return; }

      syncJobId = data.sync_job_id;
      syncStatus = 'running';
      startPolling();
    } catch (e) {
      error = 'Failed to start sync';
    } finally {
      submitting = false;
    }
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
      <button class="tab" class:active={activeTab === 'upload'} onclick={() => activeTab = 'upload'}>Upload PDF</button>
      <button class="tab" class:active={activeTab === 'documentcloud'} onclick={() => activeTab = 'documentcloud'}>DocumentCloud</button>
    </div>

    {#if error}
      <div class="error-msg">{error}</div>
    {/if}

    {#if activeTab === 'upload'}
      <div
        class="drop-zone"
        class:drop-zone-active={dragging}
        class:drop-zone-has-file={selectedFile !== null}
        role="button"
        tabindex="0"
        ondragover={handleDragOver}
        ondragleave={handleDragLeave}
        ondrop={handleDrop}
        onclick={() => document.getElementById('upload-file-input')?.click()}
        onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') document.getElementById('upload-file-input')?.click(); }}
      >
        <input type="file" id="upload-file-input" accept=".pdf,application/pdf" onchange={handleFileInput} hidden />
        {#if selectedFile}
          <div class="file-info">
            <strong>{selectedFile.name}</strong>
            <span class="file-size">{formatFileSize(selectedFile.size)}</span>
          </div>
        {:else}
          <p class="drop-prompt">Drop a PDF here or click to select</p>
        {/if}
      </div>

      {#if selectedFile}
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
          <button class="btn-primary" onclick={handleUpload} disabled={uploading || loadingModels}>
            {uploading ? 'Uploading...' : 'Upload & Process'}
          </button>
          <button class="btn-secondary" onclick={clearFile} disabled={uploading}>Clear</button>
        </div>
      {/if}

    {:else}
      <form onsubmit={handleSync}>
        <div class="form-field">
          <label for="dc-project-id">Project ID:</label>
          <input type="text" id="dc-project-id" placeholder="e.g., 123456" bind:value={projectId} required />
        </div>

        <div class="model-row">
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

        <div class="actions">
          <button type="submit" class="btn-primary" disabled={submitting || loadingModels}>
            {submitting ? 'Starting...' : 'Sync Project'}
          </button>
        </div>
      </form>

      {#if syncJobId}
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
  dialog { border: none; border-radius: 12px; padding: 0; max-width: 540px; width: 90vw; box-shadow: 0 20px 60px rgba(0,0,0,0.2); }
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

  .drop-zone { border: 2px dashed #cbd5e1; border-radius: 8px; padding: 2em; text-align: center; cursor: pointer; transition: all 0.15s; }
  .drop-zone:hover { border-color: #94a3b8; background: #f8fafc; }
  .drop-zone-active { border-color: #0066cc; background: #e8f0fe; }
  .drop-zone-has-file { border-style: solid; border-color: #059669; background: #f0fdf4; }
  .drop-prompt { margin: 0; color: #94a3b8; }
  .file-info { display: flex; flex-direction: column; gap: 0.2em; }
  .file-size { font-size: 0.85em; color: #64748b; }

  .form-field { margin-bottom: 1em; }
  .form-field label { display: block; font-size: 0.85em; color: #64748b; margin-bottom: 0.25em; }
  .form-field input { width: 100%; padding: 0.5em; font-size: 0.9em; border: 1px solid #d1d5db; border-radius: 4px; box-sizing: border-box; }

  .model-row { display: flex; gap: 1em; margin-top: 1.25em; }
  .model-field { flex: 1; }
  .model-field label { display: block; font-size: 0.8em; color: #64748b; margin-bottom: 0.25em; }
  .model-field select { width: 100%; padding: 0.35em 0.5em; font-size: 0.85em; border: 1px solid #d1d5db; border-radius: 4px; }

  .actions { display: flex; gap: 0.5em; margin-top: 1.25em; }
  .btn-primary { padding: 0.6em 1.2em; background: #0066cc; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9em; }
  .btn-primary:hover:not(:disabled) { background: #0052a3; }
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn-secondary { padding: 0.6em 1.2em; background: #f1f5f9; color: #475569; border: 1px solid #d1d5db; border-radius: 6px; cursor: pointer; font-size: 0.9em; }
  .btn-secondary:hover:not(:disabled) { background: #e2e8f0; }

  .sync-progress { margin-top: 1.25em; border-top: 1px solid #e2e8f0; padding-top: 1em; }
  .sync-status { display: flex; align-items: center; gap: 0.5em; margin-bottom: 0.5em; font-size: 0.9em; }
  .badge { padding: 0.15em 0.5em; border-radius: 3px; font-size: 0.85em; font-weight: 600; }
  .badge-running { background: #fef3c7; color: #92400e; }
  .badge-completed { background: #d1fae5; color: #065f46; }
  .badge-failed { background: #fee2e2; color: #991b1b; }
  .events-log { max-height: 150px; overflow-y: auto; font-family: monospace; font-size: 0.78em; line-height: 1.6; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 0.5em; }
  .event-info { color: #475569; }
  .event-warning { color: #92400e; }
  .event-error { color: #991b1b; font-weight: 600; }
  .event-success { color: #065f46; font-weight: 600; }
  .sync-done { margin-top: 0.75em; font-size: 0.9em; color: #065f46; }
  .btn-link { background: none; border: none; color: #0066cc; cursor: pointer; text-decoration: underline; font-size: inherit; padding: 0; }
</style>
