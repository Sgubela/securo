import { useTranslation } from 'react-i18next'
import { FlaskConical } from 'lucide-react'
import { useFeatureFlags } from '@/hooks/use-feature-flags'

export function DemoBanner() {
  const { t } = useTranslation()
  const { demoMode } = useFeatureFlags()
  if (!demoMode) return null
  return (
    <div className="fixed top-0 left-0 right-0 z-[70] flex h-7 items-center justify-center gap-2 bg-amber-500 px-4 text-[12px] font-medium text-amber-950">
      <FlaskConical size={14} className="shrink-0" />
      <span>{t('demo.banner')}</span>
    </div>
  )
}
