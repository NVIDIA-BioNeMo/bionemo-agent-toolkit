// Select only a saved machine. Power, provisioning and access changes stay in chat.
export async function connectSavedCompute({targetId, session, current, tool, render, accept}) {
  const pending = value => ({...value, state:'connecting', transport:'unverified',
    gpu:'', checked_at:null, checks:{}});
  // Connecting changes compute selection only; it must not depend on editor lifetime.
  if (!current()) return;
  const before = await tool('get_compute_status', {session_id:session});
  if (!current()) return;
  render({...pending(before), detail:'Connecting to the selected machine…'});
  const selected = await tool('select_compute', {target_id:targetId, session_id:session,
    expected_revision:before.selection.revision});
  if (!current()) return;
  // Never display cached Ready evidence as the result of this connection attempt.
  render({...pending(selected), detail:'Checking the connection…'});
  let connection = await tool('inspect_compute_target', {target_id:targetId});
  if (!current()) return;
  if (!connection.connected && selected.kind === 'brev') {
    render({...pending(selected), detail:'Refreshing Brev access. A new server key is remembered; changed keys are rejected.'});
    await tool('refresh_selected_compute_access', {session_id:session,expected_revision:selected.selection.revision});
    if (!current()) return;
    connection = await tool('inspect_compute_target', {target_id:targetId});
  }
  if (!current()) return;
  if (connection.connected) render({...pending(selected), state:'checking', transport:'reachable',
    detail:'Connected. Checking GPU, RFD4 runtime and model weights…'});
  // Record a live check even when the probe failed, so later status polls cannot
  // resurrect a previous Ready result. The backend retains all existing gates.
  const checked = await tool('check_compute', {session_id:session});
  if (!current()) return;
  accept(checked);
  return checked;
}
