import { useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PriceInput from '../PriceInput';

function TestWrapper({ initialValue = '' }: { initialValue?: string }) {
  const [val, setVal] = useState(initialValue);
  return (
    <div>
      <PriceInput
        placeholder="0.00"
        value={val}
        onChange={setVal}
        data-testid="price-input"
      />
      <div data-testid="raw-value">{val}</div>
    </div>
  );
}

describe('PriceInput component', () => {
  it('renders empty when value is empty', () => {
    render(<TestWrapper initialValue="" />);
    const input = screen.getByTestId('price-input') as HTMLInputElement;
    expect(input.value).toBe('');
    expect(screen.getByTestId('raw-value').textContent).toBe('');
  });

  it('renders pre-filled value with commas in input but raw in state', () => {
    render(<TestWrapper initialValue="50000" />);
    const input = screen.getByTestId('price-input') as HTMLInputElement;
    expect(input.value).toBe('50,000');
    expect(screen.getByTestId('raw-value').textContent).toBe('50000');
  });

  it('formats commas as user types and updates state with raw unformatted value', () => {
    render(<TestWrapper initialValue="" />);
    const input = screen.getByTestId('price-input') as HTMLInputElement;

    // Type '5000'
    fireEvent.change(input, { target: { value: '5000' } });
    expect(input.value).toBe('5,000');
    expect(screen.getByTestId('raw-value').textContent).toBe('5000');

    // Type '50000'
    fireEvent.change(input, { target: { value: '5,0000' } });
    expect(input.value).toBe('50,000');
    expect(screen.getByTestId('raw-value').textContent).toBe('50000');

    // Type '500000'
    fireEvent.change(input, { target: { value: '50,0000' } });
    expect(input.value).toBe('500,000');
    expect(screen.getByTestId('raw-value').textContent).toBe('500000');
  });

  it('handles typing decimals correctly', () => {
    render(<TestWrapper initialValue="5000" />);
    const input = screen.getByTestId('price-input') as HTMLInputElement;

    // Type decimal point
    fireEvent.change(input, { target: { value: '5,000.' } });
    expect(input.value).toBe('5,000.');
    expect(screen.getByTestId('raw-value').textContent).toBe('5000.');

    // Type decimal digits
    fireEvent.change(input, { target: { value: '5,000.5' } });
    expect(input.value).toBe('5,000.5');
    expect(screen.getByTestId('raw-value').textContent).toBe('5000.5');

    fireEvent.change(input, { target: { value: '5,000.50' } });
    expect(input.value).toBe('5,000.50');
    expect(screen.getByTestId('raw-value').textContent).toBe('5000.50');
  });

  it('strips non-numeric characters and extra decimals', () => {
    render(<TestWrapper initialValue="" />);
    const input = screen.getByTestId('price-input') as HTMLInputElement;

    fireEvent.change(input, { target: { value: '₦50,000' } });
    expect(input.value).toBe('50,000');
    expect(screen.getByTestId('raw-value').textContent).toBe('50000');

    fireEvent.change(input, { target: { value: '$1000.50.99' } });
    expect(input.value).toBe('1,000.50');
    expect(screen.getByTestId('raw-value').textContent).toBe('1000.50');
  });

  it('calls onChange with raw value when typed', () => {
    const handleChange = vi.fn();
    render(<PriceInput value="10000" onChange={handleChange} />);
    const input = screen.getByRole('textbox') as HTMLInputElement;

    fireEvent.change(input, { target: { value: '10,0005' } });
    expect(handleChange).toHaveBeenCalledWith('100005');
  });
});
