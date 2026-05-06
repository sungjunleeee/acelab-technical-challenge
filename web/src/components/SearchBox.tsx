// Search box with rotating example placeholders, a shuffle button, and
// a strip of clickable example briefs underneath. Optimized for users who
// don't yet know what kind of brief produces good results.

import { Shuffle, Sparkles, ArrowRight } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { EXAMPLE_BRIEFS, pickRandomExample } from '../lib/examples'
import { Button } from './ui'

type Props = {
  onSubmit: (brief: string) => void
  busy?: boolean
}

const ROTATION_MS = 4000

export function SearchBox({ onSubmit, busy }: Props) {
  const [value, setValue] = useState('')
  const [placeholder, setPlaceholder] = useState(EXAMPLE_BRIEFS[0].brief)
  const taRef = useRef<HTMLTextAreaElement | null>(null)

  // Rotate the placeholder when the user hasn't typed.
  useEffect(() => {
    if (value.length > 0) return
    const id = setInterval(() => {
      setPlaceholder((curr) => pickRandomExample(curr).brief)
    }, ROTATION_MS)
    return () => clearInterval(id)
  }, [value])

  function handleShuffle() {
    setPlaceholder((curr) => pickRandomExample(curr).brief)
  }

  function handleUseExample(brief: string) {
    setValue(brief)
    taRef.current?.focus()
  }

  function handleSubmit() {
    const trimmed = value.trim()
    if (!trimmed || busy) return
    onSubmit(trimmed)
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <div className="rounded-2xl border border-zinc-200 bg-white shadow-sm transition focus-within:border-zinc-400 focus-within:shadow-md">
        <textarea
          ref={taRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              handleSubmit()
            }
          }}
          placeholder={placeholder}
          rows={3}
          className="w-full resize-none rounded-2xl bg-transparent px-5 py-4 text-base text-zinc-900 placeholder:text-zinc-400 focus:outline-none"
        />
        <div className="flex items-center justify-between border-t border-zinc-100 px-3 py-2">
          <button
            onClick={handleShuffle}
            disabled={value.length > 0}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
            title="Shuffle placeholder"
          >
            <Shuffle className="h-3.5 w-3.5" />
            shuffle
          </button>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <span className="hidden sm:inline">⌘ + Enter to search</span>
            <Button onClick={handleSubmit} disabled={!value.trim() || busy}>
              {busy ? 'Searching…' : 'Search'}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
        <Sparkles className="h-3.5 w-3.5" />
        <span className="mr-1">Try:</span>
        {EXAMPLE_BRIEFS.slice(0, 5).map((ex) => (
          <button
            key={ex.label}
            onClick={() => handleUseExample(ex.brief)}
            className="cursor-pointer rounded-full border border-zinc-200 bg-white px-3 py-1 transition hover:border-zinc-400 hover:text-zinc-800"
          >
            {ex.label}
          </button>
        ))}
      </div>
    </div>
  )
}
