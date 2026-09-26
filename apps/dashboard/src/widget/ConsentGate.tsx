import { widgetStrings } from './i18n'

interface Props {
  lang: string
  primaryColor: string
  /** The business's own privacy policy (public-settings); omitted when unset. */
  privacyPolicyUrl?: string | null
  mielikkixPrivacyUrl: string
  onAgree: () => void
  onCancel: () => void
}

// Shown instead of the chat when the business has "Ask visitors to agree
// before chatting" on (require_chat_consent). Nothing is sent or stored
// until the visitor clicks "I agree"; both buttons get equal weight so
// declining is as easy as agreeing.
export function ConsentGate({ lang, primaryColor, privacyPolicyUrl, mielikkixPrivacyUrl, onAgree, onCancel }: Props) {
  const strings = widgetStrings(lang)
  return (
    <div className="flex flex-col flex-1 min-h-0 overflow-y-auto px-5 py-5" role="dialog" aria-labelledby="mlx-consent-title">
      <p id="mlx-consent-title" className="text-sm font-semibold text-gray-900 mb-3">
        {strings.consentTitle}
      </p>
      <ul className="list-disc pl-5 space-y-2 text-[13px] leading-snug text-gray-600">
        {strings.consentPoints.map((point) => (
          <li key={point}>{point}</li>
        ))}
        <li>
          {strings.consentPrivacyIntro}{' '}
          {privacyPolicyUrl && (
            <>
              <a href={privacyPolicyUrl} target="_blank" rel="noopener noreferrer" className="underline text-gray-800">
                {strings.privacyLink}
              </a>
              {' · '}
            </>
          )}
          <a href={mielikkixPrivacyUrl} target="_blank" rel="noopener noreferrer" className="underline text-gray-800">
            {strings.mielikkixPrivacyLink}
          </a>
        </li>
      </ul>
      <div className="mt-auto pt-5 grid grid-cols-2 gap-3">
        <button
          onClick={onCancel}
          className="rounded-full border-2 px-4 py-2 text-sm font-medium"
          style={{ borderColor: primaryColor, color: primaryColor }}
        >
          {strings.consentCancel}
        </button>
        <button
          onClick={onAgree}
          className="rounded-full border-2 px-4 py-2 text-sm font-medium text-white"
          style={{ borderColor: primaryColor, backgroundColor: primaryColor }}
        >
          {strings.consentAgree}
        </button>
      </div>
    </div>
  )
}
