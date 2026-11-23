<script lang="ts">
  // The approval page for one scope request (OpenSpec add-scope-requests). Everything a person reads comes from
  // the issuer's view: the summary is generated from the structured request, and the agent's own reason is shown
  // as plain text under its own label. The page decides nothing; the issuer checks the approver session.
  type Entry = { server: string; tools: string[]; constraints?: Record<string, unknown[]>; audience?: { pupils: string[] } };
  type View = {
    request_id: string;
    status: string;
    user_code: string;
    summary: string;
    expires_at: number;
    principal: string;
    level_4: boolean;
    signed_in_as: string | null;
    can_decide: boolean;
    current?: string;
    requested?: { scope: Entry[]; clearance: number | null; ttl: number };
    agent_id?: string;
    agent_reason?: string;
    held_action?: string | null;
  };

  let { requestId }: { requestId: string } = $props();
  let view = $state<View | null>(null);
  let loadError = $state('');
  let code = $state('');
  let codeError = $state('');
  let decideError = $state('');
  let busy = $state(false);
  let keep = $state<boolean[]>([]);
  let ttl = $state(0);

  const TTL_CHOICES = [300, 900, 1800, 3600, 7200, 14400, 28800, 86400];
  const ttlLabel = (s: number) => (s % 3600 === 0 ? `${s / 3600} hour${s === 3600 ? '' : 's'}` : `${s / 60} minutes`);
  const expires = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  async function load() {
    loadError = '';
    try {
      const res = await fetch(`/api/approve/view/${encodeURIComponent(requestId)}`);
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? res.statusText);
      view = body;
      if (body.requested) {
        keep = body.requested.scope.map(() => true);
        ttl = body.requested.ttl;
      }
    } catch (e) {
      loadError = String(e);
    }
  }

  function narrowed() {
    if (!view?.requested) return null;
    const scope = view.requested.scope.filter((_, i) => keep[i]);
    const same = scope.length === view.requested.scope.length && ttl === view.requested.ttl;
    return same ? null : { scope, clearance: view.requested.clearance, ttl };
  }

  async function decide(decision: 'approve' | 'reject') {
    codeError = '';
    decideError = '';
    if (!code.trim()) {
      codeError = 'Enter the code the agent showed you.';
      return;
    }
    if (decision === 'approve' && view?.requested && !keep.some(Boolean)) {
      decideError = 'Keep at least one grant, or reject the request.';
      return;
    }
    busy = true;
    try {
      const res = await fetch(`/api/approve/decision/${encodeURIComponent(requestId)}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ decision, user_code: code, approved: decision === 'approve' ? narrowed() : null }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? body.error ?? res.statusText);
      await load();
    } catch (e) {
      decideError = String(e).replace(/^Error: /, '');
    } finally {
      busy = false;
    }
  }

  $effect(() => {
    load();
  });
</script>

<h1 class="govuk-heading-l">An agent is asking for more access</h1>

{#if loadError}
  <p class="govuk-error-message">{loadError}</p>
{:else if !view}
  <p class="govuk-body">Loading the request…</p>
{:else}
  <div class="govuk-panel approval-code">
    <p class="govuk-body govuk-!-margin-bottom-1">Check the agent showed you this code</p>
    <p class="govuk-heading-xl govuk-!-margin-bottom-0 approval-code__value">{view.user_code}</p>
  </div>

  <dl class="govuk-summary-list">
    <div class="govuk-summary-list__row">
      <dt class="govuk-summary-list__key">Asking for</dt>
      <dd class="govuk-summary-list__value">{view.summary}</dd>
    </div>
    {#if view.held_action}
      <div class="govuk-summary-list__row">
        <dt class="govuk-summary-list__key">The held call</dt>
        <dd class="govuk-summary-list__value">{view.held_action}</dd>
      </div>
    {/if}
    {#if view.current}
      <div class="govuk-summary-list__row">
        <dt class="govuk-summary-list__key">It can already</dt>
        <dd class="govuk-summary-list__value">{view.current}</dd>
      </div>
    {/if}
    <div class="govuk-summary-list__row">
      <dt class="govuk-summary-list__key">Status</dt>
      <dd class="govuk-summary-list__value"><strong class="govuk-tag">{view.status}</strong>
        {#if view.status === 'pending'} until {expires(view.expires_at)}{/if}</dd>
    </div>
    {#if view.agent_id}
      <div class="govuk-summary-list__row">
        <dt class="govuk-summary-list__key">Agent</dt>
        <dd class="govuk-summary-list__value"><code>{view.agent_id}</code></dd>
      </div>
    {/if}
  </dl>

  {#if view.level_4}
    <div class="govuk-warning-text">
      <span class="govuk-warning-text__icon" aria-hidden="true">!</span>
      <strong class="govuk-warning-text__text">This includes special category data: ethnicity and care status.</strong>
    </div>
  {/if}

  {#if view.agent_reason !== undefined}
    <h2 class="govuk-heading-s">The agent says</h2>
    <div class="govuk-inset-text agent-words">{view.agent_reason}</div>
    <p class="govuk-hint">These are the agent's own words. Decide on what it's asking for above, not on this.</p>
  {/if}

  {#if !view.signed_in_as}
    <div class="govuk-inset-text">
      Only {view.principal} can decide this, signed in with their approver key. Run
      <code>uv run python -m gateway.cli approver-login --principal {view.principal} --approver-key &lt;your key&gt;
      --request {view.request_id}</code> and open the link it prints.
    </div>
  {:else if view.signed_in_as !== view.principal}
    <p class="govuk-error-message">You're signed in as {view.signed_in_as}. Only {view.principal} can decide this request.</p>
  {:else if view.can_decide && view.requested}
    <form onsubmit={(e) => e.preventDefault()}>
      <fieldset class="govuk-fieldset">
        <legend class="govuk-fieldset__legend govuk-fieldset__legend--s">Approve less if you want</legend>
        <div class="govuk-checkboxes govuk-checkboxes--small">
          {#each view.requested.scope as entry, i (i)}
            <div class="govuk-checkboxes__item">
              <input class="govuk-checkboxes__input" id={`keep-${i}`} type="checkbox" bind:checked={keep[i]} />
              <label class="govuk-label govuk-checkboxes__label" for={`keep-${i}`}>
                {entry.server}: {entry.tools.join(', ')}
                {#if entry.constraints?.urn} at {entry.constraints.urn.join(', ')}{/if}
                {#if entry.audience} for {entry.audience.pupils.length} pupils{/if}
              </label>
            </div>
          {/each}
        </div>
        <div class="govuk-form-group govuk-!-margin-top-4">
          <label class="govuk-label" for="ttl">For how long</label>
          <select class="govuk-select" id="ttl" bind:value={ttl}>
            {#each TTL_CHOICES.filter((s) => s <= view!.requested!.ttl) as s (s)}
              <option value={s}>{ttlLabel(s)}</option>
            {/each}
          </select>
        </div>
      </fieldset>
      <div class="govuk-form-group" class:govuk-form-group--error={codeError}>
        <label class="govuk-label" for="code">Type the code the agent showed you</label>
        {#if codeError}<p class="govuk-error-message">{codeError}</p>{/if}
        <input class="govuk-input govuk-input--width-10" id="code" autocomplete="off" bind:value={code}
          oninput={() => (codeError = '')} />
      </div>
      {#if decideError}<p class="govuk-error-message">{decideError}</p>{/if}
      <div class="govuk-button-group">
        <button class="govuk-button" disabled={busy} onclick={() => decide('approve')}>Approve</button>
        <button class="govuk-button govuk-button--warning" disabled={busy} onclick={() => decide('reject')}>Reject</button>
      </div>
    </form>
  {:else if view.status !== 'pending'}
    <p class="govuk-body">This request is {view.status}. Nothing more to do here.</p>
  {/if}
{/if}

<style>
  .approval-code { background: #1d70b8; color: #fff; padding: 15px 20px; }
  .approval-code__value { color: #fff; letter-spacing: 0.08em; font-family: monospace; }
  .agent-words { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
