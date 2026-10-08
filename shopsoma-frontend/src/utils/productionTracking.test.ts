import { describe, expect, it } from 'vitest';
import {
  addWorkingDays,
  calculateWorkingDaysLeft,
  formatProductionDuration,
  formatWorkingDaysLeft,
  isWorkingDay,
} from './productionTracking';

describe('productionTracking utility', () => {
  it('correctly identifies working days (Mon-Fri) and weekends (Sat-Sun)', () => {
    // 2026-10-05 = Monday, 2026-10-09 = Friday, 2026-10-10 = Saturday, 2026-10-11 = Sunday
    expect(isWorkingDay(new Date('2026-10-05T12:00:00Z'))).toBe(true);
    expect(isWorkingDay(new Date('2026-10-09T12:00:00Z'))).toBe(true);
    expect(isWorkingDay(new Date('2026-10-10T12:00:00Z'))).toBe(false);
    expect(isWorkingDay(new Date('2026-10-11T12:00:00Z'))).toBe(false);
  });

  it('adds working days skipping weekend days', () => {
    const monday = new Date('2026-10-05T10:00:00Z');
    const plus5 = addWorkingDays(monday, 5);
    // Skips Oct 10 (Sat) and Oct 11 (Sun) -> Oct 12 (Mon)
    expect(plus5.toISOString().slice(0, 10)).toBe('2026-10-12');

    const friday = new Date('2026-10-09T10:00:00Z');
    const plus1 = addWorkingDays(friday, 1);
    expect(plus1.toISOString().slice(0, 10)).toBe('2026-10-12');
  });

  it('calculates working days left accurately and excludes weekends', () => {
    const dueDate = new Date('2026-10-12T10:00:00Z'); // Monday

    // Mon Oct 5 -> 5 working days left
    expect(calculateWorkingDaysLeft(new Date('2026-10-05T10:00:00Z'), dueDate)).toBe(5);
    // Fri Oct 9 -> 1 working day left
    expect(calculateWorkingDaysLeft(new Date('2026-10-09T10:00:00Z'), dueDate)).toBe(1);
    // Sat Oct 10 -> 1 working day left (weekend does not decrement)
    expect(calculateWorkingDaysLeft(new Date('2026-10-10T10:00:00Z'), dueDate)).toBe(1);
    // Sun Oct 11 -> 1 working day left
    expect(calculateWorkingDaysLeft(new Date('2026-10-11T10:00:00Z'), dueDate)).toBe(1);
    // Mon Oct 12 -> 0 working days left (Due today)
    expect(calculateWorkingDaysLeft(new Date('2026-10-12T10:00:00Z'), dueDate)).toBe(0);
    // Tue Oct 13 -> -1 working day (1 day overdue)
    expect(calculateWorkingDaysLeft(new Date('2026-10-13T10:00:00Z'), dueDate)).toBe(-1);
  });

  it('formats working days left with proper tone and labels', () => {
    expect(formatWorkingDaysLeft({ working_days_left: 5 })).toEqual({
      text: '5 working days left',
      tone: 'normal',
    });
    expect(formatWorkingDaysLeft({ working_days_left: 1 })).toEqual({
      text: '1 working day left',
      tone: 'due-soon',
    });
    expect(formatWorkingDaysLeft({ working_days_left: 0 })).toEqual({
      text: 'Due today (0 working days left)',
      tone: 'due-soon',
    });
    expect(formatWorkingDaysLeft({ working_days_left: -2 })).toEqual({
      text: 'Overdue by 2 working days',
      tone: 'overdue',
    });
    expect(formatWorkingDaysLeft({ working_days_left: -1 })).toEqual({
      text: 'Overdue by 1 working day',
      tone: 'overdue',
    });
    expect(formatWorkingDaysLeft({ is_production_completed: true, working_days_left: 3 })).toEqual({
      text: 'Production completed',
      tone: 'completed',
    });
    expect(formatWorkingDaysLeft({ ready_for_pickup_at: '2026-10-06T10:00:00Z' })).toEqual({
      text: 'Production completed',
      tone: 'completed',
    });
    expect(formatWorkingDaysLeft({})).toEqual({
      text: 'Timeline not configured',
      tone: 'unavailable',
    });
    expect(
      formatWorkingDaysLeft(
        { production_due_date: '2026-10-12T10:00:00Z' },
        new Date('2026-10-05T10:00:00Z')
      )
    ).toEqual({
      text: '5 working days left',
      tone: 'normal',
    });
  });

  it('formats configured production duration gracefully', () => {
    expect(formatProductionDuration('5-7 business days', 7)).toBe('5-7 business days');
    expect(formatProductionDuration(null, 10)).toBe('10 working days');
    expect(formatProductionDuration(undefined, 1)).toBe('1 working day');
    expect(formatProductionDuration('', null)).toBeNull();
    expect(formatProductionDuration(null, null)).toBeNull();
  });
});
