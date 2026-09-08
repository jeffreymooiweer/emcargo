/** Updates survive route changes and process restarts. These tests exercise the
 * observed server states, preserving settings, and the setup gate rather than
 * snapshotting presentation or assuming a working Docker socket. */
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import UpdatePanel from './UpdatePanel';

const { success, translate } = vi.hoisted(() => ({ success: vi.fn(), translate: (key: string, params?: Record<string, unknown>) => params?.error ? `${key}: ${params.error}` : key }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate }) }));
vi.mock('../toast/ToastProvider', () => ({ useToast: () => ({ success }) }));
vi.mock('../api/client', () => ({ api: {
  updateCapability: vi.fn(), updateStatus: vi.fn(), updateState: vi.fn(), instanceSettings: vi.fn(),
  updateCheckNow: vi.fn(), updateApply: vi.fn(), saveInstanceSettings: vi.fn(),
} }));
const ability = { available: true, apply_enabled: true, socket: true, container: 'local', image: 'emcargo:2.1.1', reason: null };
const release = { enabled: true, reachable: true, current: '2.1.1', latest: '2.2.0', update_available: true };
const instance = { update_check_enabled: true, organisation_name: 'Example' };
async function setup() {
  let view!: ReturnType<typeof render>;
  await act(async () => { view = render(<UpdatePanel />); });
  return view;
}
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks();
  vi.mocked(api.updateCapability).mockResolvedValue(ability);
  vi.mocked(api.updateStatus).mockResolvedValue(release);
  vi.mocked(api.updateCheckNow).mockResolvedValue(release);
  vi.mocked(api.updateState).mockResolvedValue({ current: '2.1.1', state: null });
  vi.mocked(api.instanceSettings).mockResolvedValue(instance as any);
});
afterEach(() => vi.useRealTimers());

it('keeps an unreachable release check distinct from an up-to-date installation', async () => {
  vi.mocked(api.updateStatus).mockResolvedValue({ enabled: true, reachable: false, current: '2.1.1' });
  await setup();
  expect(screen.getByRole('status')).toHaveTextContent('settings.updateUnreachable');
  expect(screen.queryByText('settings.updateUpToDate')).not.toBeInTheDocument();
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'settings.updateCheckNow' })));
  expect(screen.getByRole('button', { name: 'settings.updateApplyNow' })).toBeEnabled();
});

it('explains the installation prerequisite and prevents an impossible apply', async () => {
  vi.mocked(api.updateCapability).mockResolvedValue({ ...ability, available: false, apply_enabled: false, reason: 'switch_off' });
  await setup();
  expect(screen.getByRole('button', { name: 'settings.updateApplyNow' })).toBeDisabled();
  expect(screen.getByText('settings.updateReasonSwitchOff')).toBeInTheDocument();
  expect(api.updateApply).not.toHaveBeenCalled();
});

it('changes only the update switch against the latest organisation settings', async () => {
  await setup();
  const latest = { ...instance, organisation_name: 'New name', external_url: 'https://example.invalid' };
  vi.mocked(api.instanceSettings).mockResolvedValue(latest as any);
  vi.mocked(api.saveInstanceSettings).mockResolvedValue({ ...latest, update_check_enabled: false } as any);
  await act(async () => fireEvent.click(screen.getByRole('switch')));
  expect(api.saveInstanceSettings).toHaveBeenCalledWith({ ...latest, update_check_enabled: false });
  expect(screen.getByRole('button', { name: 'settings.updateCheckNow' })).toBeDisabled();
});

it('resumes an active update and stops observing when the administrator leaves', async () => {
  vi.mocked(api.updateState).mockResolvedValue({ current: '2.1.1', state: { phase: 'handed_over', to: '2.2.0' } });
  const view = await setup();
  expect(screen.getByRole('status')).toHaveTextContent('settings.updatePhaseRestarting');
  await act(async () => { await vi.advanceTimersByTimeAsync(1600); });
  expect(api.updateState).toHaveBeenCalledTimes(2);
  view.unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(api.updateState).toHaveBeenCalledTimes(2);
});

it('keeps a failed update visible and permits a deliberate retry', async () => {
  vi.mocked(api.updateState).mockResolvedValueOnce({ current: '2.1.1', state: { phase: 'pulling', to: '2.2.0' } })
    .mockResolvedValue({ current: '2.1.1', state: { phase: 'failed', error: 'Registry unavailable' } });
  await setup();
  await act(async () => { await vi.advanceTimersByTimeAsync(1600); });
  expect(screen.getByRole('alert')).toHaveTextContent('Registry unavailable');
  expect(screen.getByRole('button', { name: 'settings.updateApplyNow' })).toBeEnabled();
});

it('requires confirmation and prevents repeated apply clicks during the request', async () => {
  vi.mocked(api.updateApply).mockImplementation(() => new Promise(() => {}));
  await setup();
  fireEvent.click(screen.getByRole('button', { name: 'settings.updateApplyNow' }));
  expect(api.updateApply).not.toHaveBeenCalled();
  const confirmation = within(screen.getByRole('alertdialog')).getByRole('button', { name: 'settings.updateApplyNow' });
  fireEvent.click(confirmation);
  expect(api.updateApply).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'settings.updateApplyNow' })).toBeDisabled();
});
