import SystemSettingsModal from '@/components/SystemSettingsModal'

interface SystemSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function SystemSettingsDialog(props: SystemSettingsDialogProps) {
  return <SystemSettingsModal {...props} />
}
