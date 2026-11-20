<script lang="ts">
  // One card per step. Each button calls a /api/demo/* route and shows the JSON it returns.
  let urn = $state('SCH01');
  let preset = $state('search-x');
  let results = $state<Record<string, unknown>>({});
  let errors = $state<Record<string, string>>({});
  let busy = $state('');

  const presets: Record<string, { label: string, tool: string, arguments: Record<string, string> }> = {
    'search-x': { label: 'search one pupil in school SCH01 (in scope)', tool: 'search', arguments: { query: 'P0004', urn: 'SCH01' } },
    'search-y': { label: 'search spring census in school SCH02 (constraint violated)', tool: 'search', arguments: { query: 'SPR', urn: 'SCH02' } },
    'search-all': { label: 'search spring census with no school (constraint missing)', tool: 'search', arguments: { query: 'SPR' } },
    'get-pii': { label: 'get every pupil name, synthetic_display_names.csv (constraint missing)', tool: 'get', arguments: { path: 'synthetic/synthetic_display_names.csv' } },
    greet: { label: 'greet (in scope)', tool: 'greet', arguments: { name: 'Mandates' } },
  };

  async function run(step: string, path: string, body?: unknown) {
    busy = step;
    delete errors[step];
    try {
      const res = await fetch(`/api/demo/${path}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { 'content-type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail ?? res.statusText);
      results[step] = json;
    } catch (e) {
      errors[step] = String(e);
    } finally {
      busy = '';
    }
  }

  const mandate = $derived(results.mandate as { status_idx: number } | undefined);
  const call = $derived(results.call as { status: number, response: { decision: { decision: string, reason_code: string } } } | undefined);
  const explain = (step: string) => (results[step] as { explanation?: string } | undefined)?.explanation;
</script>

{#snippet card(step: string, title: string)}
  <h2 class="govuk-heading-m">{title}</h2>
  {#if explain(step)}<div class="govuk-inset-text">{explain(step)}</div>{/if}
  {#if errors[step]}<p class="govuk-error-message">{errors[step]}</p>{/if}
  {#if results[step]}<pre class="demo-json">{JSON.stringify(results[step], null, 2)}</pre>{/if}
{/snippet}

<button class="govuk-button govuk-button--secondary" disabled={busy !== ''} onclick={() => run('issuer', 'issuer')}>0. Show the issuer key</button>
{@render card('issuer', 'Step 0 - The issuer key')}

<div class="govuk-form-group">
  <label class="govuk-label" for="urn">School (URN) the mandate is scoped to</label>
  <select class="govuk-select" id="urn" bind:value={urn}>
    <option>SCH01</option>
    <option>SCH02</option>
  </select>
</div>
<button class="govuk-button" disabled={busy !== ''} onclick={() => run('mandate', 'mandate', { urn })}>1. Issue mandate</button>
{@render card('mandate', 'Step 1 - Issue a mandate')}

<button class="govuk-button govuk-button--secondary" disabled={busy !== ''} onclick={() => run('trust', 'trust')}>2. Show trusted list and status list</button>
{#if mandate}
  <button class="govuk-button govuk-button--warning" disabled={busy !== ''} onclick={() => run('trust', 'revoke', { idx: mandate.status_idx })}>Revoke this mandate (idx {mandate.status_idx})</button>
{/if}
{@render card('trust', 'Step 2 - Trust and revocation')}

<div class="govuk-form-group">
  <label class="govuk-label" for="preset">Tool call the agent will sign</label>
  <select class="govuk-select" id="preset" bind:value={preset}>
    {#each Object.entries(presets) as [key, p] (key)}
      <option value={key}>{p.label}</option>
    {/each}
  </select>
</div>
<button class="govuk-button" disabled={busy !== '' || !mandate} onclick={() => run('call', 'call', { tool: presets[preset].tool, arguments: presets[preset].arguments })}>3. Sign and send through the gateway</button>
{#if call}
  <p class="govuk-body">
    <strong class="govuk-tag {call.response.decision.decision === 'ALLOW' ? 'govuk-tag--green' : 'govuk-tag--red'}">{call.response.decision.decision}</strong>
    HTTP {call.status} - {call.response.decision.reason_code}
  </p>
{/if}
{@render card('call', 'Step 3 - Gateway verification')}

<style>
  .demo-json {
    background: #f3f2f1;
    padding: 1rem;
    overflow-x: auto;
    font-size: 0.85rem;
    max-height: 30rem;
  }
</style>
