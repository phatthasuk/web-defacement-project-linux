import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { TargetStatusBadge } from './TargetStatusBadge';
import { TargetStatus } from '../types/target';

describe('TargetStatusBadge', () => {
  const statuses: TargetStatus[] = [
    'Never Checked',
    'Checking',
    'OK',
    'Changed',
    'Failed',
    'Acknowledged',
    'Availability Issue',
    'Defaced',
  ];

  statuses.forEach((status) => {
    it(`renders the correct label for status: ${status}`, () => {
      render(<TargetStatusBadge status={status} />);
      expect(screen.getByText(status)).toBeInTheDocument();
    });
  });
});
