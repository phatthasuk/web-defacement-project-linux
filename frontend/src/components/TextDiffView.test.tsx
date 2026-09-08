import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { TextDiffView } from './TextDiffView';

describe('TextDiffView', () => {
  it('renders no differences message when texts are identical', () => {
    render(<TextDiffView baselineText="Hello world" currentText="Hello world" />);
    expect(screen.getByText(/No textual differences detected/i)).toBeInTheDocument();
  });

  it('renders added and removed lines correctly', () => {
    const baseline = "Hello\nWorld";
    const current = "Hello\nTypeScript\nWorld";

    render(<TextDiffView baselineText={baseline} currentText={current} />);
    
    expect(screen.getByText(/\+ TypeScript/)).toBeInTheDocument();
    expect(screen.getByText(/Hello/)).toBeInTheDocument();
    expect(screen.getByText(/World/)).toBeInTheDocument();
  });
});
