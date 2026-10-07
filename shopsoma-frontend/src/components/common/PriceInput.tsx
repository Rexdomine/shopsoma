import React, { forwardRef, useImperativeHandle, useRef } from 'react';
import { cleanNumberString, formatWithCommas } from '../../utils/pricing';

export interface PriceInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'> {
  /**
   * The unformatted numeric string without commas (e.g. "50000" or "50000.50" or "")
   */
  value: string;
  /**
   * Callback invoked with the clean, unformatted string (no commas)
   */
  onChange: (rawValue: string) => void;
  /**
   * Maximum decimal places allowed (default: 2)
   */
  maxDecimals?: number;
}

/**
 * An accessible text input that formats currency/price numbers with humanized commas as the user types,
 * while ensuring that only clean unformatted numbers are emitted to state, code, and backend storage.
 */
export const PriceInput = forwardRef<HTMLInputElement, PriceInputProps>(
  ({ value, onChange, maxDecimals = 2, className = '', onKeyDown, ...props }, ref) => {
    const inputRef = useRef<HTMLInputElement>(null);
    useImperativeHandle(ref, () => inputRef.current as HTMLInputElement);

    const displayValue = formatWithCommas(value);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const input = e.target;
      const rawTyped = input.value;
      const selectionStart = input.selectionStart ?? rawTyped.length;

      // Count how many non-comma characters were before the cursor
      const nonCommasBefore = rawTyped.slice(0, selectionStart).replace(/,/g, '').length;

      const cleaned = cleanNumberString(rawTyped, maxDecimals);
      onChange(cleaned);

      // Restore cursor position after the DOM updates with the formatted value
      requestAnimationFrame(() => {
        if (!inputRef.current) return;
        const newFormatted = formatWithCommas(cleaned);
        let targetCursor = 0;
        let count = 0;

        for (let i = 0; i < newFormatted.length; i++) {
          if (count >= nonCommasBefore) break;
          if (newFormatted[i] !== ',') {
            count++;
          }
          targetCursor = i + 1;
        }

        inputRef.current.setSelectionRange(targetCursor, targetCursor);
      });
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
      onKeyDown?.(e);
      if (e.defaultPrevented) return;

      const input = inputRef.current;
      if (!input) return;

      // Handle Backspace when cursor is positioned right after a comma (e.g. "50,|000")
      if (e.key === 'Backspace' && input.selectionStart === input.selectionEnd) {
        const pos = input.selectionStart ?? 0;
        if (pos > 0 && input.value[pos - 1] === ',') {
          e.preventDefault();
          const raw = input.value;
          // Delete both the comma and the digit right before it
          const before = raw.slice(0, Math.max(0, pos - 2));
          const after = raw.slice(pos);
          const newRaw = before + after;
          const cleaned = cleanNumberString(newRaw, maxDecimals);
          onChange(cleaned);

          requestAnimationFrame(() => {
            if (!inputRef.current) return;
            const newFormatted = formatWithCommas(cleaned);
            const nonCommasTarget = before.replace(/,/g, '').length;
            let target = 0;
            let count = 0;
            for (let i = 0; i < newFormatted.length; i++) {
              if (count >= nonCommasTarget) break;
              if (newFormatted[i] !== ',') count++;
              target = i + 1;
            }
            inputRef.current.setSelectionRange(target, target);
          });
        }
      }
    };

    return (
      <input
        ref={inputRef}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={displayValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        className={className}
        {...props}
      />
    );
  }
);

PriceInput.displayName = 'PriceInput';

export default PriceInput;
