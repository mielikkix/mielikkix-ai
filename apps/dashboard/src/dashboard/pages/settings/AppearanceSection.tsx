import { UseMutationResult } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { MessageCircle } from 'lucide-react'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { Input } from '../../../shared/components/Input'
import { PlanGate } from '../../../shared/components/PlanGate'
import { PRESET_COLORS } from './types'

interface Props {
  customBrandingAllowed: boolean
  color: string
  setColor: (color: string) => void
  isValidColor: boolean
  colorMut: UseMutationResult<unknown, unknown, string>
}

export function AppearanceSection({ customBrandingAllowed, color, setColor, isValidColor, colorMut }: Props) {
  return (
    <Card title="Widget Appearance">
      <div className="space-y-4">
        {!customBrandingAllowed && (
          <PlanGate feature="custom_branding">
            <span />
          </PlanGate>
        )}
        <div className={clsx(!customBrandingAllowed && 'pointer-events-none opacity-40')}>
          <div>
            <label className="block text-base font-medium text-slate-700 mb-2">Widget color</label>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Preset widget colors">
              {PRESET_COLORS.map((swatch) => {
                const active = color.toLowerCase() === swatch.toLowerCase()
                return (
                  <button
                    key={swatch}
                    type="button"
                    onClick={() => setColor(swatch)}
                    aria-label={`Use ${swatch}`}
                    aria-pressed={active}
                    className={clsx(
                      'h-8 w-8 rounded-full border-2 transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-500',
                      active ? 'border-slate-900 scale-110' : 'border-transparent hover:scale-105'
                    )}
                    style={{ backgroundColor: swatch }}
                  />
                )
              })}
            </div>
          </div>

          <div className="flex items-end gap-4 mt-4">
            <div>
              <label htmlFor="custom-widget-color" className="block text-base font-medium text-slate-700 mb-1">
                Custom color
              </label>
              <input
                id="custom-widget-color"
                type="color"
                value={isValidColor ? color : '#ff6b00'}
                onChange={(e) => setColor(e.target.value)}
                aria-label="Pick a custom widget color"
                className="h-10 w-14 cursor-pointer rounded-lg border border-slate-300"
              />
            </div>

            <Input
              label="Hex value"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              placeholder="#ff6b00"
              error={!isValidColor ? 'Enter a valid hex color, e.g. #ff6b00' : undefined}
              className="w-32"
            />

            <div className="flex flex-col items-center gap-1 pb-1">
              <span className="text-sm text-slate-500">Preview</span>
              <div
                className="flex h-10 w-10 items-center justify-center rounded-full text-white shadow-sm"
                style={{ backgroundColor: isValidColor ? color : '#e2e8f0' }}
              >
                <MessageCircle size={18} />
              </div>
            </div>
          </div>

          <Button
            className="mt-4"
            loading={colorMut.isPending}
            disabled={!isValidColor}
            onClick={() => colorMut.mutate(color)}
          >
            Save appearance
          </Button>
        </div>
        {colorMut.isSuccess && <p className="text-base text-green-600">Widget color saved!</p>}
        {colorMut.isError && (
          <p className="text-base text-red-600">
            {(colorMut.error as any)?.response?.data?.detail ?? 'Could not save widget color.'}
          </p>
        )}
      </div>
    </Card>
  )
}
