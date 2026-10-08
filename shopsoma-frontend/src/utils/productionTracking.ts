/**
 * Production tracking and platform working-day calendar calculations.
 *
 * Rules:
 * - Working days are Monday through Friday (0 = Sun, 6 = Sat).
 * - Non-working days (weekends) are excluded from the countdown.
 * - Completed items (marked ready) display completed status rather than an active countdown.
 * - Countdown is informational and does not block vendor readiness actions.
 */

export function isWorkingDay(date: Date): boolean {
  const day = date.getDay();
  return day !== 0 && day !== 6;
}

export function addWorkingDays(start: Date, days: number): Date {
  const cur = new Date(start.getTime());
  if (days <= 0) return cur;

  let added = 0;
  while (added < days) {
    cur.setDate(cur.getDate() + 1);
    if (isWorkingDay(cur)) {
      added += 1;
    }
  }
  return cur;
}

export function calculateWorkingDaysLeft(asOf: Date, dueDate: Date): number {
  const start = new Date(asOf.getFullYear(), asOf.getMonth(), asOf.getDate());
  const due = new Date(dueDate.getFullYear(), dueDate.getMonth(), dueDate.getDate());

  if (start.getTime() === due.getTime()) {
    return 0;
  }

  if (start.getTime() < due.getTime()) {
    const cur = new Date(start.getTime());
    let count = 0;
    while (cur.getTime() < due.getTime()) {
      cur.setDate(cur.getDate() + 1);
      if (isWorkingDay(cur)) {
        count += 1;
      }
    }
    return count;
  } else {
    const cur = new Date(due.getTime());
    let count = 0;
    while (cur.getTime() < start.getTime()) {
      cur.setDate(cur.getDate() + 1);
      if (isWorkingDay(cur)) {
        count += 1;
      }
    }
    return -count;
  }
}

export interface WorkingDaysStatus {
  text: string;
  tone: 'completed' | 'normal' | 'due-soon' | 'overdue' | 'unavailable';
}

export function formatWorkingDaysLeft(
  item: {
    working_days_left?: number | null;
    production_due_date?: string | null;
    is_production_completed?: boolean | null;
    is_production_overdue?: boolean | null;
    ready_for_pickup_at?: string | null;
  },
  asOf: Date = new Date()
): WorkingDaysStatus {
  if (item.is_production_completed || !!item.ready_for_pickup_at) {
    return {
      text: 'Production completed',
      tone: 'completed',
    };
  }

  let daysLeft = item.working_days_left;
  if ((daysLeft === undefined || daysLeft === null) && item.production_due_date) {
    const due = new Date(item.production_due_date);
    if (!Number.isNaN(due.getTime())) {
      daysLeft = calculateWorkingDaysLeft(asOf, due);
    }
  }

  if (daysLeft === undefined || daysLeft === null) {
    return {
      text: 'Timeline not configured',
      tone: 'unavailable',
    };
  }

  if (daysLeft > 1) {
    return {
      text: `${daysLeft} working days left`,
      tone: 'normal',
    };
  }

  if (daysLeft === 1) {
    return {
      text: '1 working day left',
      tone: 'due-soon',
    };
  }

  if (daysLeft === 0) {
    return {
      text: 'Due today (0 working days left)',
      tone: 'due-soon',
    };
  }

  const overdue = Math.abs(daysLeft);
  return {
    text: `Overdue by ${overdue} working ${overdue === 1 ? 'day' : 'days'}`,
    tone: 'overdue',
  };
}

export function formatProductionDuration(
  duration?: string | null,
  days?: number | null
): string | null {
  if (duration && duration.trim()) {
    return duration.trim();
  }
  if (days !== undefined && days !== null && days > 0) {
    return `${days} working ${days === 1 ? 'day' : 'days'}`;
  }
  return null;
}
