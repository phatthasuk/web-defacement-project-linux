import { apiFetch } from './client';
import { CheckResult } from '../types/checkResult';

export async function listTargetChecks(targetId: string, includeHistory = false): Promise<CheckResult[]> {
  return apiFetch<CheckResult[]>(`/targets/${targetId}/checks${includeHistory ? '?include_history=true' : ''}`);
}

export async function acknowledgeCheck(checkId: string): Promise<CheckResult> {
  return apiFetch<CheckResult>(`/checks/${checkId}/ack`, {
    method: 'POST',
  });
}

export async function confirmDefacedCheck(checkId: string): Promise<CheckResult> {
  return apiFetch<CheckResult>(`/checks/${checkId}/confirm-defaced`, {
    method: 'POST',
  });
}

export async function getCheck(checkId: string): Promise<CheckResult> {
  return apiFetch<CheckResult>(`/checks/${checkId}`);
}
