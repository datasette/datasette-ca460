<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import DevBadge from './DevBadge.svelte';
  import { loadPageData } from './pageData';
  import { models, sync, syncEvents, uploadPdf, processDocument } from './api';

  const { database } = loadPageData<{ database: string }>();

  interface SyncEvent {
    type: string;
    message: string;
    created_at: string;
  }

  interface SyncJob {
    status: string;
    error: string | null;
    started_at: string;
    completed_at: string | null;
  }

  type SourceTab = 'upload' | 'documentcloud';

  let activeTab: SourceTab = $state('upload');

  // Form state - shared
  let pageTypeModel = $state('');
  let parserModel = $state('');
  let availableModels: string[] = $state([]);
  let loadingModels = $state(true);

  // Form state - DocumentCloud
  let projectId = $state('');

  // Form state - Upload
  let selectedFile: File | null = $state(null);
  let dragging = $state(false);
  let uploading = $state(false);

  // Sync job state (DocumentCloud only)
  let syncJobId: string | null = $state(null);
  let jobStatus: SyncJob | null = $state(null);
  let events: SyncEvent[] = $state([]);
  let pollInterval: ReturnType<typeof setInterval> | null = null;

  // Message state
  let message = $state('');
  let messageType: 'success' | 'error' | '' = $state('');

  let submitting = $state(false);

  onMount(async () => {
    await loadModels();
  });

  onDestroy(() => {
    if (pollInterval) clearInterval(pollInterval);
  });

  async function loadModels() {
    loadingModels = true;
    try {
      const { data, error, response } = await models(database);
      if (error || !response.ok) {
        message = 'Failed to load available models';
        messageType = 'error';
        return;
      }
      const responseData = data as any;
      availableModels = responseData.models || [];
      if (availableModels.length > 0) {
        pageTypeModel = availableModels[0];
        parserModel = availableModels[0];
      }
    } catch (e) {
      message = 'Failed to load available models';
      messageType = 'error';
    } finally {
      loadingModels = false;
    }
  }

  // --- Upload ---

  function handleDragOver(e: DragEvent) { e.preventDefault(); dragging = true; }
  function handleDragLeave(e: DragEvent) { e.preventDefault(); dragging = false; }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    const file = e.dataTransfer?.files?.[0];
    if (file && (file.type === 'application/pdf' || file.name.endsWith('.pdf'))) {
      selectedFile = file;
      message = '';
      messageType = '';
    } else {
      message = 'Please drop a PDF file';
      messageType = 'error';
    }
  }

  function handleFileInput(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files?.[0]) {
      selectedFile = input.files[0];
      message = '';
      messageType = '';
    }
  }

  function clearFile() { selectedFile = null; }

  async function handleUpload() {
    if (!selectedFile) return;

    uploading = true;
    message = '';
    messageType = '';

    try {
      // Upload
      const { data, error } = await uploadPdf(database, selectedFile);
      if (error || !data) {
        message = (error as any)?.error || 'Failed to upload file';
        messageType = 'error';
        return;
      }

      // Start processing
      const { data: processData, error: processError } = await processDocument(database, {
        document_id: data.document_id,
        page_type_model: pageTypeModel,
        parser_model: parserModel,
      });

      if (processError || !processData) {
        message = `Uploaded but failed to start processing`;
        messageType = 'error';
        return;
      }

      // Redirect to document page with sync job
      const jobId = (processData as any).sync_job_id;
      window.location.href = `/${database}/-/ca460/document/${data.document_id}?sync_job_id=${jobId}`;
    } catch (e) {
      console.error('Error uploading:', e);
      message = 'Failed to upload file';
      messageType = 'error';
    } finally {
      uploading = false;
    }
  }

  // --- DocumentCloud ---

  async function handleDocumentCloudSync(e: Event) {
    e.preventDefault();
    if (!projectId) {
      message = 'Please provide a DocumentCloud project ID';
      messageType = 'error';
      return;
    }

    const projectIdNum = parseInt(projectId, 10);
    if (isNaN(projectIdNum)) {
      message = 'Project ID must be a number';
      messageType = 'error';
      return;
    }

    submitting = true;
    message = '';
    messageType = '';

    try {
      const { data, error } = await sync(database, {
        project_id: projectIdNum,
        page_type_model: pageTypeModel,
        parser_model: parserModel,
      });

      if (error) {
        message = error || 'Failed to start sync job';
        messageType = 'error';
        return;
      }

      syncJobId = data.sync_job_id;
      message = `Sync job started for project ${projectIdNum}`;
      messageType = 'success';
      events = [];
      jobStatus = null;
      startPolling();
    } catch (e) {
      message = 'Failed to start sync job';
      messageType = 'error';
    } finally {
      submitting = false;
    }
  }

  // --- Polling (DocumentCloud only) ---

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
      }
    } catch (e) { /* ignore */ }
  }

  function getStatusClass(s: string) {
    return s === 'running' ? 'status-running' : s === 'completed' ? 'status-completed' : s === 'failed' ? 'status-failed' : '';
  }
  function getEventClass(t: string) {
    return t === 'warning' ? 'event-warning' : t === 'error' ? 'event-error' : t === 'success' ? 'event-success' : 'event-info';
  }
  function formatFileSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  let eventsContainer: HTMLElement | null = $state(null);
  $effect(() => {
    if (eventsContainer && events.length > 0) eventsContainer.scrollTop = eventsContainer.scrollHeight;
  });
</script>

<main>
  <h1>CA Form 460 Sync <DevBadge /></h1>
  <p>Import California Form 460 campaign finance documents into <strong>{database}</strong>.</p>

  <nav class="ca460-nav">
    <a href="/{database}/-/ca460" class="nav-link">&larr; All Documents</a>
  </nav>

  {#if message}
    <div class="message-{messageType}">{message}</div>
  {/if}

  {#if syncJobId && jobStatus}
    <div class="progress">
      <h2>Sync Progress</h2>
      <div class="job-status {getStatusClass(jobStatus.status)}">Status: {jobStatus.status}</div>
      <div class="events-container" bind:this={eventsContainer}>
        {#each events as event}
          <div class="event {getEventClass(event.type)}">{event.message}</div>
        {/each}
        {#if jobStatus.status === 'failed' && jobStatus.error}
          <div class="event event-error">Error: {jobStatus.error}</div>
        {/if}
      </div>
    </div>
  {/if}

  <div class="tabs">
    <button class="tab" class:tab-active={activeTab === 'upload'} onclick={() => activeTab = 'upload'}>Upload PDF</button>
    <button class="tab" class:tab-active={activeTab === 'documentcloud'} onclick={() => activeTab = 'documentcloud'}>DocumentCloud</button>
  </div>

  <div class="tab-content">
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
        onclick={() => document.getElementById('file-input')?.click()}
        onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') document.getElementById('file-input')?.click(); }}
      >
        <input type="file" id="file-input" accept=".pdf,application/pdf" onchange={handleFileInput} hidden />
        {#if selectedFile}
          <div class="file-info">
            <span class="file-icon">&#128196;</span>
            <div>
              <strong>{selectedFile.name}</strong>
              <span class="file-size">{formatFileSize(selectedFile.size)}</span>
            </div>
          </div>
        {:else}
          <div class="drop-zone-prompt">
            <span class="drop-icon">&#128194;</span>
            <p>Drag and drop a PDF here, or click to select</p>
          </div>
        {/if}
      </div>

      {#if selectedFile}
        <div class="model-selectors">
          <div class="form-group">
            <label for="upload_page_type_model">Page Type Model:</label>
            <select id="upload_page_type_model" bind:value={pageTypeModel} disabled={loadingModels}>
              {#if loadingModels}
                <option value="">Loading...</option>
              {:else}
                {#each availableModels as model}
                  <option value={model}>{model}</option>
                {/each}
              {/if}
            </select>
          </div>
          <div class="form-group">
            <label for="upload_parser_model">Parser Model:</label>
            <select id="upload_parser_model" bind:value={parserModel} disabled={loadingModels}>
              {#if loadingModels}
                <option value="">Loading...</option>
              {:else}
                {#each availableModels as model}
                  <option value={model}>{model}</option>
                {/each}
              {/if}
            </select>
          </div>
        </div>

        <div class="upload-actions">
          <button class="btn-primary" onclick={handleUpload} disabled={uploading || loadingModels}>
            {uploading ? 'Uploading...' : 'Upload & Process'}
          </button>
          <button class="btn-secondary" onclick={clearFile} disabled={uploading}>Clear</button>
        </div>
      {/if}

    {:else}
      <form onsubmit={handleDocumentCloudSync}>
        <div class="form-group">
          <label for="project_id">DocumentCloud Project ID:</label>
          <input type="text" id="project_id" required placeholder="e.g., 123456" bind:value={projectId} />
        </div>

        <div class="model-selectors">
          <div class="form-group">
            <label for="page_type_model">Page Type Model:</label>
            <select id="page_type_model" bind:value={pageTypeModel} disabled={loadingModels}>
              {#if loadingModels}
                <option value="">Loading...</option>
              {:else}
                {#each availableModels as model}
                  <option value={model}>{model}</option>
                {/each}
              {/if}
            </select>
          </div>
          <div class="form-group">
            <label for="parser_model">Parser Model:</label>
            <select id="parser_model" bind:value={parserModel} disabled={loadingModels}>
              {#if loadingModels}
                <option value="">Loading...</option>
              {:else}
                {#each availableModels as model}
                  <option value={model}>{model}</option>
                {/each}
              {/if}
            </select>
          </div>
        </div>

        <button type="submit" class="btn-primary" disabled={submitting || loadingModels}>
          {submitting ? 'Starting Sync...' : 'Sync Project'}
        </button>
      </form>
    {/if}
  </div>
</main>

<style>
  .ca460-nav { margin: 1em 0; }
  .nav-link { display: inline-block; padding: 0.5em 1em; background: #6c757d; color: white !important; text-decoration: none; border-radius: 4px; }
  .nav-link:hover { background: #5a6268; }

  .tabs { display: flex; border-bottom: 2px solid #dee2e6; margin-top: 1.5em; }
  .tab { padding: 0.6em 1.2em; background: none; border: 2px solid transparent; border-bottom: none; border-radius: 4px 4px 0 0; cursor: pointer; font-size: 1em; color: #666; margin-bottom: -2px; }
  .tab:hover { color: #333; background: #f8f9fa; }
  .tab-active { color: #333; border-color: #dee2e6; background: white; font-weight: bold; }
  .tab-content { padding: 1.5em 0; }

  .drop-zone { border: 2px dashed #ccc; border-radius: 8px; padding: 2em; text-align: center; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
  .drop-zone:hover { border-color: #999; background: #fafafa; }
  .drop-zone-active { border-color: #0066cc; background: #e8f0fe; }
  .drop-zone-has-file { border-style: solid; border-color: #28a745; background: #f0f9f2; }
  .drop-zone-prompt { color: #888; }
  .drop-zone-prompt p { margin: 0.5em 0 0; }
  .drop-icon { font-size: 2em; }
  .file-info { display: flex; align-items: center; justify-content: center; gap: 0.75em; }
  .file-icon { font-size: 2em; }
  .file-size { display: block; color: #666; font-size: 0.9em; }

  .model-selectors { display: flex; gap: 1em; margin-top: 1em; }
  .model-selectors .form-group { flex: 1; }

  .upload-actions { display: flex; gap: 0.5em; margin-top: 1em; }

  .btn-primary { padding: 0.75em 1.5em; font-size: 1em; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; }
  .btn-primary:hover:not(:disabled) { background: #0052a3; }
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn-secondary { padding: 0.75em 1.5em; font-size: 1em; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer; }
  .btn-secondary:hover:not(:disabled) { background: #5a6268; }
  .btn-secondary:disabled { opacity: 0.6; cursor: not-allowed; }

  .form-group { margin-bottom: 1em; }
  .form-group label { display: block; font-weight: bold; margin-bottom: 0.25em; }
  .form-group input, .form-group select { width: 100%; max-width: 400px; padding: 0.5em; font-size: 1em; }

  .message-success { padding: 1em; background: #d4edda; border: 1px solid #c3e6cb; color: #155724; border-radius: 4px; margin-bottom: 1em; }
  .message-error { padding: 1em; background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; border-radius: 4px; margin-bottom: 1em; }

  .progress { margin-top: 2em; padding: 1em; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }
  .job-status { padding: 0.5em 1em; margin-bottom: 1em; border-radius: 4px; font-weight: bold; }
  .status-running { background: #fff3cd; color: #856404; }
  .status-completed { background: #d4edda; color: #155724; }
  .status-failed { background: #f8d7da; color: #721c24; }
  .events-container { max-height: 400px; overflow-y: auto; border: 1px solid #dee2e6; border-radius: 4px; padding: 0.5em; background: white; }
  .event { padding: 0.25em 0; font-family: monospace; font-size: 0.9em; }
  .event-info { color: #333; }
  .event-warning { color: #856404; }
  .event-error { color: #721c24; font-weight: bold; }
  .event-success { color: #155724; font-weight: bold; }
</style>
