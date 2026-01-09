<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import DevBadge from './DevBadge.svelte';

  const database = 'tmp';

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

  // Form state
  let projectId = $state('');
  let pageTypeModel = $state('');
  let parserModel = $state('');
  let availableModels: string[] = $state([]);
  let loadingModels = $state(true);

  // Sync job state
  let syncJobId: string | null = $state(null);
  let jobStatus: SyncJob | null = $state(null);
  let events: SyncEvent[] = $state([]);
  let pollInterval: ReturnType<typeof setInterval> | null = null;

  // Message state
  let message = $state('');
  let messageType: 'success' | 'error' | '' = $state('');

  // Submitting state
  let submitting = $state(false);

  onMount(async () => {
    await loadModels();
  });

  onDestroy(() => {
    if (pollInterval) {
      clearInterval(pollInterval);
    }
  });

  async function loadModels() {
    loadingModels = true;
    try {
      const response = await fetch(`/${database}/-/ca460/api/models`);
      const data = await response.json();
      availableModels = data.models || [];
      if (availableModels.length > 0) {
        pageTypeModel = availableModels[0];
        parserModel = availableModels[0];
      }
    } catch (error) {
      console.error('Error loading models:', error);
      message = 'Failed to load available models';
      messageType = 'error';
    } finally {
      loadingModels = false;
    }
  }

  async function handleSubmit(e: Event) {
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
      const response = await fetch(`/${database}/-/ca460/api/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_id: projectIdNum,
          page_type_model: pageTypeModel,
          parser_model: parserModel,
        }),
      });

      const data = await response.json();

      if (data.error) {
        message = data.error;
        messageType = 'error';
        return;
      }

      syncJobId = data.sync_job_id;
      message = `Sync job started for project ${projectIdNum}`;
      messageType = 'success';
      events = [];
      jobStatus = null;

      // Start polling for events
      startPolling();
    } catch (error) {
      console.error('Error starting sync:', error);
      message = 'Failed to start sync job';
      messageType = 'error';
    } finally {
      submitting = false;
    }
  }

  function startPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
    }

    // Poll immediately, then every second
    pollEvents();
    pollInterval = setInterval(pollEvents, 1000);
  }

  async function pollEvents() {
    if (!syncJobId) return;

    try {
      const response = await fetch(`/${database}/-/ca460/sync/${syncJobId}/events`);
      const data = await response.json();

      jobStatus = data.job;
      events = data.events;

      // Stop polling if completed or failed
      if (data.job.status === 'completed' || data.job.status === 'failed') {
        if (pollInterval) {
          clearInterval(pollInterval);
          pollInterval = null;
        }
      }
    } catch (error) {
      console.error('Error polling events:', error);
    }
  }

  function getStatusClass(status: string): string {
    switch (status) {
      case 'running':
        return 'status-running';
      case 'completed':
        return 'status-completed';
      case 'failed':
        return 'status-failed';
      default:
        return '';
    }
  }

  function getEventClass(type: string): string {
    switch (type) {
      case 'info':
        return 'event-info';
      case 'warning':
        return 'event-warning';
      case 'error':
        return 'event-error';
      case 'success':
        return 'event-success';
      default:
        return 'event-info';
    }
  }

  let eventsContainer: HTMLElement | null = $state(null);

  $effect(() => {
    // Auto-scroll to bottom when events change
    if (eventsContainer && events.length > 0) {
      eventsContainer.scrollTop = eventsContainer.scrollHeight;
    }
  });
</script>

<main>
  <h1>CA Form 460 Sync <DevBadge /></h1>
  <p>Sync California Form 460 campaign finance documents from DocumentCloud to <strong>{database}</strong>.</p>

  <nav class="ca460-nav">
    <a href="/{database}/-/ca460" class="nav-link">← Back to CA 460</a>
  </nav>

  {#if message}
    <div class="message-{messageType}">
      {message}
    </div>
  {/if}

  {#if syncJobId && jobStatus}
    <div class="progress">
      <h2>Sync Progress</h2>
      <div class="job-status {getStatusClass(jobStatus.status)}">
        Status: {jobStatus.status}
      </div>
      <div class="events-container" bind:this={eventsContainer}>
        {#each events as event}
          <div class="event {getEventClass(event.type)}">
            {event.message}
          </div>
        {/each}
        {#if jobStatus.status === 'failed' && jobStatus.error}
          <div class="event event-error">
            Error: {jobStatus.error}
          </div>
        {/if}
      </div>
    </div>
  {/if}

  <form onsubmit={handleSubmit}>
    <div class="form-group">
      <label for="project_id">DocumentCloud Project ID:</label>
      <input
        type="text"
        id="project_id"
        name="project_id"
        required
        placeholder="e.g., 123456"
        bind:value={projectId}
      />
    </div>

    <div class="form-group">
      <label for="page_type_model">Page Type Model:</label>
      <select id="page_type_model" name="page_type_model" bind:value={pageTypeModel} disabled={loadingModels}>
        {#if loadingModels}
          <option value="">Loading models...</option>
        {:else}
          {#each availableModels as model}
            <option value={model}>{model}</option>
          {/each}
        {/if}
      </select>
      <small>Model to use for page type prediction</small>
    </div>

    <div class="form-group">
      <label for="parser_model">Parser Model:</label>
      <select id="parser_model" name="parser_model" bind:value={parserModel} disabled={loadingModels}>
        {#if loadingModels}
          <option value="">Loading models...</option>
        {:else}
          {#each availableModels as model}
            <option value={model}>{model}</option>
          {/each}
        {/if}
      </select>
      <small>Model to use for parsing pages</small>
    </div>

    <button type="submit" disabled={submitting || loadingModels}>
      {#if submitting}
        Starting Sync...
      {:else}
        Sync Project
      {/if}
    </button>
  </form>
</main>

<style>
  .ca460-nav {
    margin: 1em 0;
  }

  .nav-link {
    display: inline-block;
    padding: 0.5em 1em;
    background: #6c757d;
    color: white !important;
    text-decoration: none;
    border-radius: 4px;
  }

  .nav-link:hover {
    background: #5a6268;
    color: white !important;
  }

  .form-group {
    margin-bottom: 1em;
  }

  .form-group label {
    display: block;
    font-weight: bold;
    margin-bottom: 0.25em;
  }

  .form-group input,
  .form-group select {
    width: 100%;
    max-width: 400px;
    padding: 0.5em;
    font-size: 1em;
  }

  .form-group small {
    display: block;
    color: #666;
    margin-top: 0.25em;
  }

  button {
    padding: 0.75em 1.5em;
    font-size: 1em;
    background: #0066cc;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }

  button:hover:not(:disabled) {
    background: #0052a3;
  }

  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .message-success {
    padding: 1em;
    background: #d4edda;
    border: 1px solid #c3e6cb;
    color: #155724;
    border-radius: 4px;
    margin-bottom: 1em;
  }

  .message-error {
    padding: 1em;
    background: #f8d7da;
    border: 1px solid #f5c6cb;
    color: #721c24;
    border-radius: 4px;
    margin-bottom: 1em;
  }

  .progress {
    margin-top: 2em;
    padding: 1em;
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 4px;
  }

  .job-status {
    padding: 0.5em 1em;
    margin-bottom: 1em;
    border-radius: 4px;
    font-weight: bold;
  }

  .status-running {
    background: #fff3cd;
    color: #856404;
  }

  .status-completed {
    background: #d4edda;
    color: #155724;
  }

  .status-failed {
    background: #f8d7da;
    color: #721c24;
  }

  .events-container {
    max-height: 400px;
    overflow-y: auto;
    border: 1px solid #dee2e6;
    border-radius: 4px;
    padding: 0.5em;
    background: white;
  }

  .event {
    padding: 0.25em 0;
    font-family: monospace;
    font-size: 0.9em;
  }

  .event-info {
    color: #333;
  }

  .event-warning {
    color: #856404;
  }

  .event-error {
    color: #721c24;
    font-weight: bold;
  }

  .event-success {
    color: #155724;
    font-weight: bold;
  }
</style>
