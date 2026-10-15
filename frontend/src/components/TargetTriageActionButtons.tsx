import type { TargetTriageActions } from '../hooks/useTargetTriageActions';

interface TargetTriageActionButtonsProps {
  actions: TargetTriageActions;
  className?: string;
}

export function TargetTriageActionButtons({ actions, className = '' }: TargetTriageActionButtonsProps) {
  const disabled = actions.isChecking || actions.isPending;
  const title = actions.isChecking ? 'Cannot triage while check is in progress' : undefined;

  return (
    <div className={`flex w-full flex-col gap-2 sm:w-auto sm:flex-row ${className}`}>
      {actions.canApproveBaseline && (
        <button
          type="button"
          onClick={actions.handleApproveBaseline}
          disabled={disabled}
          title={title}
          className="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-lg bg-gradient-to-r from-emerald-500 to-teal-600 px-4 text-sm font-semibold text-white shadow-md shadow-emerald-950/20 transition-all hover:from-emerald-400 hover:to-teal-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {actions.approveIsPending ? 'Approving...' : 'Approve as Baseline'}
        </button>
      )}
      {actions.canAcknowledge && (
        <button
          type="button"
          onClick={actions.handleAcknowledge}
          disabled={disabled}
          title={title}
          className="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-lg bg-gradient-to-r from-indigo-500 to-purple-600 px-4 text-sm font-semibold text-white shadow-md shadow-indigo-950/20 transition-all hover:from-indigo-400 hover:to-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {actions.acknowledgeIsPending ? 'Acknowledging...' : 'Acknowledge Change'}
        </button>
      )}
      {actions.canConfirmDefacement && (
        <button
          type="button"
          onClick={actions.handleConfirmDefacement}
          disabled={disabled}
          title={title}
          className="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-lg bg-gradient-to-r from-rose-600 to-red-700 px-4 text-sm font-semibold text-white shadow-md shadow-rose-950/30 transition-all hover:from-rose-500 hover:to-red-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {actions.confirmIsPending ? 'Confirming...' : 'Confirm Defacement'}
        </button>
      )}
    </div>
  );
}
