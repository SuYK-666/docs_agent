import { X } from 'lucide-react'
import { createContext, useContext, useEffect, useId, useMemo } from 'react'
import { createPortal } from 'react-dom'

type DialogContextValue = {
  open: boolean
  onOpenChange: (open: boolean) => void
  titleId: string
  descriptionId: string
}

const DialogContext = createContext<DialogContextValue | null>(null)

function useDialogContext() {
  const context = useContext(DialogContext)
  if (!context) {
    throw new Error('Dialog components must be used inside <Dialog>.')
  }
  return context
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ')
}

interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: React.ReactNode
}

function Dialog({ open, onOpenChange, children }: DialogProps) {
  const titleId = useId()
  const descriptionId = useId()

  const value = useMemo(
    () => ({
      open,
      onOpenChange,
      titleId,
      descriptionId,
    }),
    [descriptionId, onOpenChange, open, titleId],
  )

  return <DialogContext.Provider value={value}>{children}</DialogContext.Provider>
}

interface DialogPortalProps {
  children: React.ReactNode
}

function DialogPortal({ children }: DialogPortalProps) {
  const { open } = useDialogContext()

  if (!open || typeof document === 'undefined') return null
  return createPortal(children, document.body)
}

interface DialogOverlayProps {
  className?: string
}

function DialogOverlay({ className }: DialogOverlayProps) {
  const { onOpenChange } = useDialogContext()

  return (
    <div
      className={cn('fixed inset-0 z-50 bg-black/70 backdrop-blur-sm', className)}
      onClick={() => onOpenChange(false)}
      aria-hidden="true"
    />
  )
}

interface DialogContentProps {
  className?: string
  children: React.ReactNode
}

function DialogContent({ className, children }: DialogContentProps) {
  const { descriptionId, onOpenChange, open, titleId } = useDialogContext()

  useEffect(() => {
    if (!open) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onOpenChange(false)
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onOpenChange, open])

  return (
    <DialogPortal>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <DialogOverlay />
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={descriptionId}
          className={cn(
            'relative z-50 w-full max-w-xl rounded-[1.75rem] border border-white/10 bg-[#091220]/95 p-6 text-white shadow-[0_30px_100px_rgba(2,6,23,0.65)] backdrop-blur-2xl',
            className,
          )}
        >
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white/70 transition hover:bg-white/10 hover:text-white"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
          {children}
        </div>
      </div>
    </DialogPortal>
  )
}

interface DialogHeaderProps {
  className?: string
  children: React.ReactNode
}

function DialogHeader({ className, children }: DialogHeaderProps) {
  return <div className={cn('flex flex-col gap-2', className)}>{children}</div>
}

interface DialogTitleProps {
  className?: string
  children: React.ReactNode
}

function DialogTitle({ className, children }: DialogTitleProps) {
  const { titleId } = useDialogContext()
  return (
    <h2 id={titleId} className={cn('text-2xl font-semibold tracking-tight text-white', className)}>
      {children}
    </h2>
  )
}

interface DialogDescriptionProps {
  className?: string
  children: React.ReactNode
}

function DialogDescription({ className, children }: DialogDescriptionProps) {
  const { descriptionId } = useDialogContext()
  return (
    <p id={descriptionId} className={cn('text-sm leading-6 text-white/65', className)}>
      {children}
    </p>
  )
}

interface DialogFooterProps {
  className?: string
  children: React.ReactNode
}

function DialogFooter({ className, children }: DialogFooterProps) {
  return <div className={cn('mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end', className)}>{children}</div>
}

export { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogOverlay, DialogPortal, DialogTitle }
