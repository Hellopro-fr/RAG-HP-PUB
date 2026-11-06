// Minimal shadcn/ui-style primitives (copied-source pattern, Tailwind + cva).
import { cva, type VariantProps } from 'class-variance-authority';
import { clsx, type ClassValue } from 'clsx';
import type { ComponentProps } from 'react';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-400',
  {
    variants: {
      variant: {
        default: 'bg-slate-900 text-white hover:bg-slate-700',
        outline: 'border border-slate-300 bg-white hover:bg-slate-50',
        destructive: 'bg-red-600 text-white hover:bg-red-500',
        ghost: 'hover:bg-slate-100',
      },
      size: { default: 'h-9 px-4', sm: 'h-8 px-3 text-xs' },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export function Button({
  className,
  variant,
  size,
  ...props
}: ComponentProps<'button'> & VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export function Card({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div className={cn('rounded-lg border border-slate-200 bg-white shadow-sm', className)} {...props} />
  );
}

const badgeVariants = cva('inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium', {
  variants: {
    tone: {
      neutral: 'bg-slate-100 text-slate-700',
      warn: 'bg-amber-100 text-amber-800',
      danger: 'bg-red-100 text-red-800',
      info: 'bg-sky-100 text-sky-800',
      ok: 'bg-emerald-100 text-emerald-800',
    },
  },
  defaultVariants: { tone: 'neutral' },
});

export function Badge({
  className,
  tone,
  ...props
}: ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export function Input({ className, ...props }: ComponentProps<'input'>) {
  return (
    <input
      className={cn(
        'h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm focus-visible:outline-2 focus-visible:outline-slate-400',
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <textarea
      className={cn(
        'min-h-16 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-slate-400',
        className,
      )}
      {...props}
    />
  );
}
