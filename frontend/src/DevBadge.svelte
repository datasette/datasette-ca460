<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  let hmrStatus: 'init' | 'connected' | 'disconnected' | 'error' = $state('init');
  let viteUrl = $state('');

  onMount(() => {
    if (import.meta.hot) {
      // HMR is available - we're in dev mode
      // Get the Vite server URL from the current script location
      viteUrl = `${location.protocol}//${import.meta.env.DEV ? new URL(import.meta.url).host : ''}`;
      
      // If HMR is available and the module loaded, the connection is already established
      // The ws:connect event only fires on reconnection, not initial connection
      hmrStatus = 'connected';
      
      // Listen for HMR connection events
      import.meta.hot.on('vite:ws:connect', () => {
        hmrStatus = 'connected';
      });

      import.meta.hot.on('vite:ws:disconnect', () => {
        hmrStatus = 'disconnected';
      });

      // Also handle error states
      import.meta.hot.on('vite:error', () => {
        hmrStatus = 'error';
      });
    }
  });
</script>

{#if import.meta.env.DEV}
  <span 
    class="dev-badge {hmrStatus}"
    title={viteUrl ? `Vite: ${viteUrl}` : 'Vite HMR'}
  >
    DEV
  </span>
{/if}

<style>
  .dev-badge {
    display: inline-block;
    padding: 0.1em 0.5em;
    font-size: 0.5em;
    font-weight: bold;
    border-radius: 4px;
    text-transform: uppercase;
    margin-left: 0.5em;
    vertical-align: middle;
    cursor: pointer;
  }

  .init {
    background: #6b7280;
    color: white;
  }

  .connected {
    background: #10b981;
    color: white;
  }

  .disconnected {
    background: #f59e0b;
    color: white;
  }

  .error {
    background: #ef4444;
    color: white;
  }
</style>
